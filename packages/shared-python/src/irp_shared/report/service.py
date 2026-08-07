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
from datetime import UTC, date, datetime
from html import escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import RunStatus
from irp_shared.calc.runs import resolve_completed_run_of_type
from irp_shared.calc.service import create_run, update_run_status
from irp_shared.classification.service import canonical_tenant_id
from irp_shared.report.families import REPORT_FAMILIES, family_for
from irp_shared.report.models import (
    RENDER_FORMAT_HTML,
    REPORT_CODE_RISK_SUMMARY,
    REPORT_VERSION_LABEL_V1,
    RUN_TYPE_REPORT,
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


def canonical_known_at(value: datetime) -> str:
    """The knowledge time as ONE string, whatever the driver handed back.

    **A portability defect caught by execution, not by reading.** PostgreSQL returns
    ``as_of_known_at`` as a tz-AWARE datetime; SQLite returns the same instant NAIVE, because the
    driver has nowhere to keep the offset. Rendering ``.isoformat()`` directly therefore produced
    ``2026-07-01T12:00:00+00:00`` on one engine and ``2026-07-01T12:00:00`` on the other — different
    BYTES for the same report, and the content hash is over the bytes. The identity claim would have
    been quietly engine-dependent.

    A naive value is treated as UTC, which is what the platform stores everywhere; an aware value is
    converted. Both render in the same canonical form.
    """
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def governed_value_content(
    *,
    family_key: str,
    section_title: str,
    model_code: str,
    methodology_ref: str,
    model_version_id: str,
    run_id: str,
    source_snapshot_id: str,
    source_known_at: str,
    values: list[tuple[str, str]],
) -> dict[str, Any]:
    """The pinned content for one family section — the values AND their full provenance.

    Values are carried as STRINGS, verbatim from the source rows' Decimal repr. Round-tripping
    them through float for JSON would change the number a governed report shows, which is the one
    thing a governed report may never do.

    ``model_version_id`` and ``source_snapshot_id`` are pinned rather than merely the model CODE:
    I5 names "run ID, snapshot verification, model version, methodology ref", and a code without a
    version cannot tell a reader WHICH registration produced the number — two versions of one model
    are exactly what MG-10's change-means-new-version rule creates.

    ``source_known_at`` is I3's half. The report's ``as_of`` says WHEN the numbers speak
    about; the knowledge time says AS OF WHEN THEY WERE KNOWN. A regenerated historical report
    is byte-identical to the original precisely because it re-renders what was known then — and
    a reader who cannot see the knowledge time has no way to tell a stale report from a current
    one. It comes from the PINNED source snapshot, which is IA append-only, so rendering it
    costs nothing in determinism.
    """
    return {
        "family": family_key,
        "section_title": section_title,
        "model_code": model_code,
        "methodology_ref": methodology_ref,
        "model_version_id": str(model_version_id),
        "source_run_id": str(run_id),
        "source_snapshot_id": str(source_snapshot_id),
        "source_known_at": str(source_known_at),
        "renderer_version": RENDERER_VERSION,
        "values": [{"metric": m, "value": v} for m, v in values],
    }


def build_report_snapshot(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str,
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
    - **a run computed for a DIFFERENT portfolio than the one the report names.** Found by the
      RPT-2 adversarial review: every run was fenced to the tenant and to its run_type, and the
      report's portfolio was fenced to the tenant, but NOTHING related the two — so a caller with
      one legitimate portfolio and one legitimate run could mint an IA append-only, byte-identically
      reproducible board artifact headed with book A's name carrying book B's risk numbers. Both
      halves were individually correct; the relation between them did not exist. `portfolio_id` is
      REQUIRED here (not optional-with-a-default) precisely so no caller can reach the old
      behaviour by omission.
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
        # THE ATTRIBUTION FENCE. A run's scope_portfolio_id is the book it was computed for; the
        # report names a book in its heading. If they differ, the artifact would attribute one
        # book's governed numbers to another — with a real hash, a real snapshot and a real audit
        # trail. A run with NO scope is refused too: "unscoped" is not "matches", and admitting it
        # would leave the fence open to exactly the runs whose provenance is weakest.
        if str(run.scope_portfolio_id) != str(portfolio_id):
            raise ReportInputError(
                f"family {family.key!r} run {run_id} was computed for portfolio "
                f"{run.scope_portfolio_id!r}, but this report names {portfolio_id!r} — refusing to "
                "attribute one book's governed numbers to another"
            )
        values = family.read_values(session, str(run.run_id), tenant)
        if not values:
            raise ReportInputError(
                f"family {family.key!r} run {run_id} yielded ZERO values — refusing rather than "
                "rendering an empty section, which a reader cannot distinguish from 'no risk'"
            )
        # Resolved from the run's OWN rows and checked against the registered allowlist, never
        # declared by this module — see the families docstring for why a static pair was wrong.
        prov = family.read_provenance(session, str(run.run_id), tenant)
        if run.input_snapshot_id is None:
            raise ReportInputError(
                f"family {family.key!r} run {run_id} pins no input snapshot — a governed number "
                "whose inputs are unnamed cannot be cited in a report"
            )
        source_snapshot = session.execute(
            select(DatasetSnapshot).where(
                DatasetSnapshot.id == str(run.input_snapshot_id),
                DatasetSnapshot.tenant_id == tenant,
            )
        ).scalar_one_or_none()
        if source_snapshot is None:
            raise ReportInputError(
                f"family {family.key!r} run {run_id} pins snapshot {run.input_snapshot_id}, which "
                "is not visible to this tenant — refusing to cite inputs the report cannot name"
            )
        pinned.append(
            (
                family.key,
                governed_value_content(
                    family_key=family.key,
                    section_title=family.section_title,
                    model_code=prov.model_code,
                    methodology_ref=prov.methodology_ref,
                    model_version_id=prov.model_version_id,
                    run_id=str(run.run_id),
                    source_snapshot_id=str(run.input_snapshot_id),
                    source_known_at=canonical_known_at(source_snapshot.as_of_known_at),
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
    from irp_shared.risk.events import RUN_TYPE_VAR

    mapping = {
        # All seven VaR/ES models run under ONE run_type; metric_type is the discriminator, and
        # events.py states that run_type must never equal metric_type. So this filter fences out
        # a non-VaR run, and the metric key rendered by _read_var says which VaR it is.
        "var": RUN_TYPE_VAR,
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
        # I3: the knowledge time, per section. A regenerated historical report is byte-identical
        # because it re-renders what was KNOWN THEN; without this line the reader cannot tell that
        # from a current view, which is the half of I3 that says the report must SAY so.
        parts.append(
            f"<p class='known-at'>Inputs as known at "
            f"{escape(str(section['source_known_at']))}</p>"
        )
        parts.append(
            "<p class='provenance'>"
            f"model <code>{escape(str(section['model_code']))}</code> "
            f"version <code>{escape(str(section['model_version_id']))}</code> · "
            f"run <code>{escape(str(section['source_run_id']))}</code> · "
            f"inputs <code>{escape(str(section['source_snapshot_id']))}</code> · "
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


def generate_report(
    session: Session,
    *,
    acting_tenant: str,
    actor_id: str,
    portfolio_id: str,
    portfolio_code: str,
    as_of_date: date,
    family_runs: dict[str, str],
    generated_at: datetime,
) -> tuple[ReportGeneration, RenderedReport]:
    """Generate one governed report: pin the inputs, render, and record the artifact.

    **No ``model_version_id``, and that is by design rather than omission.** A report registers no
    model: it renders numbers OTHER families produced under THEIR registered versions, and each
    rendered section carries its own family's ``model_code`` and ``methodology_ref``. Inventing a
    "report model" would add a governance object that asserts nothing — the methodology that
    matters is the one behind each number, and that is already pinned. This is recorded on the P8
    census exception list rather than left for a reader to infer.

    Ordering is deliberate: the snapshot is built (and every refusal fires) BEFORE the report row
    exists, so a refused generation leaves no run, no snapshot and no row — the pattern DATA-1
    learned the hard way when a refusal fired after ``begin_nested()`` and left a dangling
    savepoint.
    """
    tenant = canonical_tenant_id(acting_tenant)
    from irp_shared.snapshot.events import SnapshotActor
    from irp_shared.snapshot.service import build_report_input_snapshot

    snapshot = build_report_input_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id=actor_id, actor_type="user"),
        portfolio_id=str(portfolio_id),
        family_runs=family_runs,
        as_of_valuation_date=as_of_date,
    )
    sections = _pinned_sections(session, snapshot_id=str(snapshot.id), acting_tenant=tenant)
    rendered = render_report_html(
        portfolio_code=portfolio_code, as_of=as_of_date, sections=sections
    )

    # THE GOVERNED RUN RAIL, not a hand-rolled row. The first draft of this verb constructed
    # `CalculationRun(...)` directly and emitted NO audit event at all — a governed evidence
    # artifact with no record of its own creation. `create_run` + `update_run_status` emit
    # CALC.RUN_CREATE and CALC.RUN_STATUS_CHANGE against the FROZEN `record_event`.
    #
    # RPT-1 therefore mints NO audit code, following CON-1's recorded precedent verbatim: the run
    # lifecycle rides the existing CALC events and the snapshot rides `record_snapshot_create`.
    # `REPORT.GENERATE` (EVT-090) stays GENESIS-RESERVED — activating it is an R-07 act, and there
    # is nothing for it to say that the CALC pair does not already say.
    run = create_run(
        session,
        tenant_id=tenant,
        run_type=RUN_TYPE_REPORT,
        initiated_by=actor_id,
        input_snapshot_id=str(snapshot.id),
        scope_portfolio_id=str(portfolio_id),
    )
    session.flush()

    row = ReportGeneration(
        tenant_id=tenant,
        calculation_run_id=run.run_id,
        input_snapshot_id=snapshot.id,
        portfolio_id=str(portfolio_id),
        # PINNED, not re-supplied at regeneration (pre-merge audit B1) — it is inside the hashed
        # bytes, and `portfolio.code` is mutable.
        portfolio_code=portfolio_code,
        report_code=REPORT_CODE_RISK_SUMMARY,
        report_version_label=REPORT_VERSION_LABEL_V1,
        render_format=RENDER_FORMAT_HTML,
        as_of_date=as_of_date,
        content_hash=rendered.content_hash,
        generated_at=generated_at,
        generated_by=actor_id,
    )
    session.add(row)
    session.flush()
    update_run_status(session, run, RunStatus.COMPLETED, actor_id=actor_id)
    return row, rendered


def regenerate_report(session: Session, *, report_id: str, acting_tenant: str) -> RenderedReport:
    """Re-render a stored report **from the report id alone** and REFUSE on any hash divergence.

    This is BR-9's proof, executed rather than asserted. Every input to the render comes from the
    stored row and its pinned snapshot — nothing is supplied by the caller.

    **``portfolio_code`` used to be a parameter here, and that was the defect the pre-merge audit
    found (B1).** It is rendered into the ``<h1>`` and therefore into the hashed bytes, so a caller
    who passed a different string got a hash mismatch reported as a RENDERER change; and since
    ``portfolio.code`` is a mutable effective-dated field, a renamed book made its own historical
    reports unreproducible by anyone who did not remember the old string. The asymmetry was visible
    all along — ``as_of_date``, the other report-level rendered value, was already read from the
    row. A reproducibility claim that depends on the caller's memory is not a reproducibility claim.
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
        portfolio_code=row.portfolio_code, as_of=row.as_of_date, sections=sections
    )
    if rendered.content_hash != row.content_hash:
        raise ReportIdentityError(
            f"report {report_id} did not regenerate identically: stored "
            f"{row.content_hash} != regenerated {rendered.content_hash}. Every render input is "
            "pinned and immutable, so this is a RENDERER change or a TAMPERED stored hash — never "
            "an input change."
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
    "generate_report",
    "governed_value_content",
    "regenerate_report",
    "render_report_html",
    "stored_report_hash",
]
