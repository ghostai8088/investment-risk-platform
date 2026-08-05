"""RPT-1 — generate a governed report, and regenerate it byte-identically (REQ-RPT-001 / BR-9).

**The identity claim, stated precisely.** ``regenerate_report`` re-renders from the PINNED snapshot
content and compares a SHA-256 over the rendered bytes with the hash stored at generation time. It
never re-reads the family tables. So the claim proven is the strong one: *the same bound inputs
produce the same artifact*, not merely *the source rows have not changed*.

**Why that distinction is the whole slice.** Re-reading the families would ALSO look
reproducible today, because those result tables are IA append-only. But it would make the
report's reproducibility a property of OTHER tables rather than of the report, and the first
family to gain a correction path would silently change every historical report. Pinning the
rendered values makes I1 and I3 structural rather than inherited.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.runs import resolve_completed_run_of_type
from irp_shared.classification.service import canonical_tenant_id
from irp_shared.report.families import REPORT_FAMILIES, family_for
from irp_shared.report.models import (
    RENDER_FORMAT_HTML,
    REPORT_CODE_RISK_SUMMARY,
    REPORT_VERSION_LABEL_V1,
    ReportGeneration,
)
from irp_shared.snapshot.models import (
    COMPONENT_KIND_GOVERNED_VALUE,
    DatasetSnapshot,
    DatasetSnapshotComponent,
)

#: The renderer's own version. It participates in the identity: a renderer change legitimately
#: changes the bytes, and a report regenerated under a DIFFERENT renderer must not silently claim
#: byte-identity with one produced by the old one. Stored in the pinned content, so the mismatch is
#: visible as data rather than inferred from a hash that simply differs.
RENDERER_VERSION = "rpt-1-html-v1"


class ReportInputError(ValueError):
    """A CLIENT-supplied report input is invalid — the governed 422 pattern.

    A dedicated type, not bare ``ValueError``: the API error map keys on exact type, so a bare
    ``ValueError`` would relabel a genuine server-side bug as a client 422 (the API-2 MRO trap).
    """


class ReportIdentityError(RuntimeError):
    """A regeneration did not reproduce the stored hash. Deliberately NOT a ``ValueError``: this is
    not a bad input, it is the platform failing its own BR-9 reproducibility claim, and it must not
    be catchable by a handler written for client errors."""


@dataclass(frozen=True)
class RenderedReport:
    """The rendered artifact plus the hash taken over exactly the bytes returned."""

    body: str
    content_hash: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def governed_value_content(
    *,
    family_key: str,
    section_title: str,
    model_code: str,
    methodology_ref: str,
    run_id: str,
    values: list[tuple[str, str]],
) -> dict[str, Any]:
    """The pinned content for one family section — the values AND their provenance.

    Values are carried as STRINGS, verbatim from the source rows' Decimal repr. Round-tripping
    them through float for JSON would change the number a governed report shows, which is the one
    thing a governed report may never do.
    """
    return {
        "family": family_key,
        "section_title": section_title,
        "model_code": model_code,
        "methodology_ref": methodology_ref,
        "source_run_id": str(run_id),
        "renderer_version": RENDERER_VERSION,
        "values": [{"metric": m, "value": v} for m, v in values],
    }


def build_report_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    family_runs: dict[str, str],
) -> list[tuple[str, dict[str, Any]]]:
    """Resolve each family's COMPLETED run and read its values — the pinned specs, pre-persist.

    Returns ``[(family_key, content), ...]`` in REGISTRY order, not caller order: the caller's
    dict ordering must not be able to change the report's bytes, or I2 would be provable only for
    callers who happened to iterate the same way.

    **Refusals, all pre-persist (nothing written, no run, no snapshot):**

    - an unknown family key (``family_for`` raises rather than rendering an empty section);
    - a run that is missing, not COMPLETED, of the wrong run_type, or belonging to another
      tenant — delegated to ``resolve_completed_run_of_type``, the shared guard, because PG FK
      checks bypass RLS and a cross-tenant run id would otherwise be durably referenced;
    - a family whose run yields ZERO values. That refusal is the load-bearing one: a report section
      rendering "no data" is indistinguishable from a report section whose family silently returned
      nothing, and a board-facing artifact must not be able to show the second while meaning the
      first.
    """
    if not family_runs:
        raise ReportInputError("a report must bind at least one family run")

    tenant = canonical_tenant_id(acting_tenant)
    unknown = sorted(set(family_runs) - {f.key for f in REPORT_FAMILIES})
    if unknown:
        raise ReportInputError(
            f"unknown report families {unknown} — known: {sorted(f.key for f in REPORT_FAMILIES)}"
        )

    pinned: list[tuple[str, dict[str, Any]]] = []
    for family in REPORT_FAMILIES:  # registry order, never caller order
        run_id = family_runs.get(family.key)
        if run_id is None:
            continue
        run = resolve_completed_run_of_type(
            session,
            str(run_id),
            acting_tenant=tenant,
            run_type=_run_type_for(family.key),
            label=f"{family.key} report input",
            error=ReportInputError,
        )
        values = family.read_values(session, str(run.run_id), tenant)
        if not values:
            raise ReportInputError(
                f"family {family.key!r} run {run_id} yielded ZERO values — refusing rather than "
                "rendering an empty section, which a reader cannot distinguish from 'no risk'"
            )
        pinned.append(
            (
                family.key,
                governed_value_content(
                    family_key=family.key,
                    section_title=family.section_title,
                    model_code=family.model_code,
                    methodology_ref=family.methodology_ref,
                    run_id=str(run.run_id),
                    values=values,
                ),
            )
        )
    return pinned


def _run_type_for(family_key: str) -> str:
    """The run_type each family's results are produced under.

    Declared here rather than inferred: reusing a shipped result table without a run_type filter
    is the exact defect PPF-2 shipped, and ``resolve_completed_run_of_type`` can only enforce what
    it is told.
    """
    from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION
    from irp_shared.liquidity.models import RUN_TYPE_LIQUIDITY
    from irp_shared.perf.events import RUN_TYPE_ROLLING_RISK

    mapping = {
        "concentration": RUN_TYPE_CONCENTRATION,
        "liquidity": RUN_TYPE_LIQUIDITY,
        "rolling_risk": RUN_TYPE_ROLLING_RISK,
    }
    family_for(family_key)  # refuses an unknown key loudly before the lookup below
    return mapping[family_key]


def render_report_html(
    *,
    portfolio_code: str,
    as_of: date,
    sections: list[dict[str, Any]],
) -> RenderedReport:
    """Render the report to print-clean HTML (ratified OQ-RPT-1-2) from PINNED content only.

    Deterministic by construction — no timestamps, no ids that vary per render, no dict iteration
    over unordered input. Anything that varied between two renders of the same snapshot would make
    the identity check meaningless, so ``generated_at`` deliberately does NOT appear in the body:
    it lives on the row, where it belongs, rather than in the bytes the hash covers.
    """
    parts: list[str] = [
        "<!-- rpt-1 -->",
        f"<h1>Risk summary — {escape(portfolio_code)}</h1>",
        f"<p class='as-of'>As of {escape(as_of.isoformat())}</p>",
    ]
    for section in sections:
        parts.append(f"<section data-family='{escape(str(section['family']))}'>")
        parts.append(f"<h2>{escape(str(section['section_title']))}</h2>")
        parts.append(
            "<p class='provenance'>"
            f"model <code>{escape(str(section['model_code']))}</code> · "
            f"run <code>{escape(str(section['source_run_id']))}</code> · "
            f"methodology <code>{escape(str(section['methodology_ref']))}</code>"
            "</p>"
        )
        parts.append("<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>")
        for item in section["values"]:
            parts.append(
                f"<tr><td>{escape(str(item['metric']))}</td>"
                f"<td class='mono'>{escape(str(item['value']))}</td></tr>"
            )
        parts.append("</tbody></table>")
        parts.append("</section>")
    body = "\n".join(parts)
    return RenderedReport(body=body, content_hash=_sha256(body))


def _pinned_sections(
    session: Session, *, snapshot_id: str, acting_tenant: str
) -> list[dict[str, Any]]:
    """The report's sections, read from PINNED component content only — never from the families."""
    tenant = canonical_tenant_id(acting_tenant)
    snapshot = session.execute(
        select(DatasetSnapshot).where(
            DatasetSnapshot.id == str(snapshot_id), DatasetSnapshot.tenant_id == tenant
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise ReportInputError(f"snapshot {snapshot_id} is not visible to {acting_tenant}")
    comps = (
        session.execute(
            select(DatasetSnapshotComponent)
            .where(
                DatasetSnapshotComponent.snapshot_id == str(snapshot_id),
                DatasetSnapshotComponent.component_kind == COMPONENT_KIND_GOVERNED_VALUE,
            )
            .order_by(DatasetSnapshotComponent.target_entity_id)
        )
        .scalars()
        .all()
    )
    if not comps:
        raise ReportInputError(
            f"snapshot {snapshot_id} pins no GOVERNED_VALUE components — it is not a report input"
        )
    sections = [json.loads(c.captured_content) for c in comps]
    order = {f.key: i for i, f in enumerate(REPORT_FAMILIES)}
    sections.sort(key=lambda s: order.get(str(s["family"]), len(order)))
    return sections


def regenerate_report(
    session: Session, *, report_id: str, acting_tenant: str, portfolio_code: str
) -> RenderedReport:
    """Re-render a stored report from its pinned snapshot and REFUSE on any hash divergence.

    This is BR-9's proof, executed rather than asserted. It reads only pinned content, so a
    divergence means the RENDERER changed — which is exactly what a reader needs to be told, loudly,
    rather than served a silently different artifact under the same report id.
    """
    tenant = canonical_tenant_id(acting_tenant)
    row = session.execute(
        select(ReportGeneration).where(
            ReportGeneration.id == str(report_id), ReportGeneration.tenant_id == tenant
        )
    ).scalar_one_or_none()
    if row is None:
        raise ReportInputError(f"report {report_id} is not visible to {acting_tenant}")

    sections = _pinned_sections(
        session, snapshot_id=str(row.input_snapshot_id), acting_tenant=tenant
    )
    rendered = render_report_html(
        portfolio_code=portfolio_code, as_of=row.as_of_date, sections=sections
    )
    if rendered.content_hash != row.content_hash:
        raise ReportIdentityError(
            f"report {report_id} did not regenerate identically: stored "
            f"{row.content_hash} != regenerated {rendered.content_hash}. The pinned inputs are "
            "immutable, so this is a RENDERER change, not an input change."
        )
    return rendered


def stored_report_hash(session: Session, *, report_id: str, acting_tenant: str) -> str:
    """The stored hash, for a caller that wants to compare without re-rendering."""
    tenant = canonical_tenant_id(acting_tenant)
    row = session.execute(
        select(ReportGeneration).where(
            ReportGeneration.id == str(report_id), ReportGeneration.tenant_id == tenant
        )
    ).scalar_one_or_none()
    if row is None:
        raise ReportInputError(f"report {report_id} is not visible to {acting_tenant}")
    return str(row.content_hash)


__all__ = [
    "RENDERER_VERSION",
    "RENDER_FORMAT_HTML",
    "REPORT_CODE_RISK_SUMMARY",
    "REPORT_VERSION_LABEL_V1",
    "RenderedReport",
    "ReportIdentityError",
    "ReportInputError",
    "build_report_snapshot",
    "governed_value_content",
    "regenerate_report",
    "render_report_html",
    "stored_report_hash",
]
