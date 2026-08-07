"""Report endpoints (RPT-2) — the governed report becomes REACHABLE, and every read re-proves it.

Thin layer over ``irp_shared.report`` (ENT-072, RPT-1). Two properties are load-bearing and both
come from the schema rather than from this router's preferences:

**Every HTML read is a reproduction check (remit I1).** ``report_generation`` stores the SHA-256 of
the rendered bytes and deliberately NOT the bytes — so ``GET /reports/{id}/html`` must re-render
from the pinned snapshot, and the service refuses on any divergence from the stored hash. A
divergence here is the platform failing its own BR-9 claim (a renderer change or a tampered hash,
never an input change — every render input is pinned), so it maps to **500**, not any 4xx: the
client did nothing wrong, and labeling it a client error would bury an integrity failure. Do not
"optimize" this by caching the body; the absent column is the design.

**The wire cannot assert evidence time (remit I2, ratified OQ-W16P-2).** ``generated_at`` is
server-stamped in this router; the request schema is ``extra="forbid"`` so a caller supplying a
``generated_at``-shaped field is refused with a 422 rather than silently ignored — an ignored field
is indistinguishable, to the caller, from an honored one. The in-process batch parameter on the
service remains, per the recorded ENT-072 column rationale.

**The permission split (remit I3):** ``report.view`` gates governed OUTPUT and includes auditor_3l
(the unbroken 3L chain); ``report.generate`` is a WRITE verb — it mints a run, a snapshot and an IA
row — and excludes the auditor (the snapshot.create / ``*.run`` class). SOD-08's approve/publish
half stays unminted: no publish verb ships here.

Failure model: every generate refusal fires PRE-persist inside the service (a refused generation
leaves no run, no snapshot, no row), and ``raise_mapped_write`` rolls the whole unit back on the
mapped refusals. There is no PUT/PATCH/DELETE — ENT-072 is append-only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_backend.api.write_errors import raise_mapped_write
from irp_backend.deps import get_tenant_session, require_permission, require_uuid_principal_id
from irp_shared.entitlement.service import Principal
from irp_shared.portfolio.models import Portfolio
from irp_shared.report.families import ReportProvenanceError
from irp_shared.report.models import ReportGeneration
from irp_shared.report.service import (
    ReportIdentityError,
    ReportInputError,
    canonical_known_at,
    generate_report,
    regenerate_report,
)

router = APIRouter(prefix="/reports", tags=["reports"])

#: Module-level guard singletons (deny-by-default; built once, not in argument defaults).
_require_view = require_permission("report.view")
_require_generate = require_permission("report.generate")

#: The write path's refusal map. EXACT-type lookup (`errors[type(exc)]`, the API-2 MRO trap):
#: ReportProvenanceError subclasses ReportInputError's sibling ValueError, but each needs its OWN
#: key — a provenance refusal ("this run's model citation cannot be trusted") and an input refusal
#: ("this run is not visible / not COMPLETED / yields nothing") are both 422s today, and keeping
#: the keys separate is what lets a future split cost one line instead of an incident. Bare
#: ValueError is deliberately ABSENT: a valueless governed row is a data defect and must stay a
#: loud 500, never a client error.
_GENERATE_ERRORS: dict[type[Exception], tuple[int, str]] = {
    ReportInputError: (422, "report input refused"),
    ReportProvenanceError: (422, "report provenance refused"),
}
_GENERATE_EXCS = tuple(_GENERATE_ERRORS)


class ReportGenerateIn(BaseModel):
    """The generate request. ``extra="forbid"`` is remit I2's fence: a ``generated_at`` (or any
    other unexpected field) in the body is REFUSED, not ignored — silence would be
    indistinguishable from acceptance."""

    model_config = ConfigDict(extra="forbid")

    #: Typed ``uuid.UUID``, not ``str`` (RPT-2 review, BLOCKING): these values reach a
    #: PostgreSQL ``uuid`` column, where a malformed string raises `invalid input syntax for type
    #: uuid` and surfaces as a **500** — while the SQLite unit tier stores GUID as CHAR(36),
    #: matches nothing, and proves a tidy 404 that production never exhibits. Typing them here
    #: makes FastAPI refuse a malformed id with a 422 before any query runs, on BOTH engines.
    portfolio_id: uuid.UUID
    as_of_date: date
    #: family key -> COMPLETED run id. Any non-empty subset of the registered families is valid BY
    #: DESIGN (a var-only report is a report); the empty dict is refused by the service.
    family_runs: dict[str, uuid.UUID]


class ReportOut(BaseModel):
    id: str
    calculation_run_id: str
    input_snapshot_id: str
    portfolio_id: str
    portfolio_code: str
    report_code: str
    report_version_label: str
    render_format: str
    as_of_date: date
    content_hash: str
    #: Canonicalized UTC ISO string — NOT a raw datetime. SQLite hands the column back naive and
    #: PostgreSQL aware (the ENT-072 column is timezone-less), so a raw echo would be
    #: engine-dependent; ``canonical_known_at`` is the shipped normalizer for exactly this.
    generated_at: str
    generated_by: str


class ReportListOut(BaseModel):
    items: list[ReportOut]


def _out(row: ReportGeneration) -> ReportOut:
    return ReportOut(
        id=str(row.id),
        calculation_run_id=str(row.calculation_run_id),
        input_snapshot_id=str(row.input_snapshot_id),
        portfolio_id=str(row.portfolio_id),
        portfolio_code=row.portfolio_code,
        report_code=row.report_code,
        report_version_label=row.report_version_label,
        render_format=row.render_format,
        as_of_date=row.as_of_date,
        content_hash=row.content_hash,
        generated_at=canonical_known_at(row.generated_at),
        generated_by=row.generated_by,
    )


def _visible_report(db: Session, report_id: str, tenant_id: str) -> ReportGeneration:
    """Tenant-fenced point read. Missing and foreign are the SAME 404 — a 403 on a foreign id
    would itself disclose that the id exists (the LIM-2 fence posture)."""
    row = db.execute(
        select(ReportGeneration).where(
            ReportGeneration.id == report_id, ReportGeneration.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    return row


@router.post("", response_model=ReportOut, status_code=201)
def generate(
    body: ReportGenerateIn,
    principal: Principal = Depends(_require_generate),
    db: Session = Depends(get_tenant_session),
) -> ReportOut:
    actor_id = require_uuid_principal_id(principal)
    # The portfolio must be a REAL row visible to this tenant, and the rendered code comes from
    # THAT row — never from the caller. Two fences in one read: a foreign/unknown portfolio 404s
    # before anything is written, and a caller cannot stamp a misleading display code onto a
    # governed artifact for a book they can see but did not name correctly.
    portfolio = db.execute(
        select(Portfolio).where(
            Portfolio.id == str(body.portfolio_id), Portfolio.tenant_id == principal.tenant_id
        )
    ).scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="portfolio not found")

    try:
        row, _rendered = generate_report(
            db,
            acting_tenant=principal.tenant_id,
            actor_id=actor_id,
            portfolio_id=str(portfolio.id),
            portfolio_code=portfolio.code,
            as_of_date=body.as_of_date,
            family_runs={k: str(v) for k, v in body.family_runs.items()},
            # Remit I2 (ratified OQ-W16P-2): SERVER-stamped. The wire has no way to assert this.
            generated_at=datetime.now(UTC),
        )
        db.commit()
    except _GENERATE_EXCS as exc:
        raise_mapped_write(db, exc, _GENERATE_ERRORS)
        raise AssertionError("unreachable") from exc  # pragma: no cover - the mapper always raises
    return _out(row)


@router.get("", response_model=ReportListOut)
def list_reports(
    portfolio_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ReportListOut:
    stmt = select(ReportGeneration).where(ReportGeneration.tenant_id == principal.tenant_id)
    if portfolio_id is not None:
        stmt = stmt.where(ReportGeneration.portfolio_id == str(portfolio_id))
    # as_of_date leads the ordering because it leads the shipped index (tenant, report_code,
    # as_of_date); id breaks ties deterministically. generated_at is NOT the sort key — it has no
    # index and, being caller-asserted on the batch path, no total-order guarantee.
    stmt = (
        stmt.order_by(ReportGeneration.as_of_date.desc(), ReportGeneration.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(stmt).scalars().all()
    return ReportListOut(items=[_out(r) for r in rows])


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> ReportOut:
    return _out(_visible_report(db, str(report_id), principal.tenant_id))


@router.get("/{report_id}/html", response_class=HTMLResponse)
def get_report_html(
    report_id: uuid.UUID,
    principal: Principal = Depends(_require_view),
    db: Session = Depends(get_tenant_session),
) -> HTMLResponse:
    """The rendered artifact — re-rendered from the pin on every read, never served from storage.

    This is remit I1 made structural: the response bytes hash to the stored ``content_hash`` or
    the request fails. A 404 covers missing/foreign ids; a 500 covers the one failure that is
    genuinely the platform's — regeneration diverging from the recorded identity.
    """
    _visible_report(db, str(report_id), principal.tenant_id)  # 404 before any work
    try:
        rendered = regenerate_report(
            db, report_id=str(report_id), acting_tenant=principal.tenant_id
        )
    except ReportIdentityError as exc:
        # The platform failing its own BR-9 claim. NEVER a 4xx: the client did nothing wrong, and
        # a client-shaped status would bury an integrity failure in request-error noise.
        raise HTTPException(
            status_code=500,
            detail=f"report identity failure — regeneration diverged from the stored hash: {exc}",
        ) from exc
    except ReportInputError as exc:
        # The row passed the visibility probe above but the snapshot read refused (a race, or a
        # partially restored database). Same opaque 404 as the probe — not a distinct signal.
        raise HTTPException(status_code=404, detail="report not found") from exc
    # THE ARTIFACT'S OWN BOUNDARY (RPT-2 review, HIGH). The FE renders this in a
    # `sandbox=""` iframe — but nginx proxies `/reports/...` on the SPA's OWN ORIGIN, so a viewer
    # who navigates, bookmarks or is redirected to this URL renders the same bytes with full
    # script capability and read access to `sessionStorage["irp.session"]` (which holds the OIDC
    # bearer token). The iframe sandbox protects the app; it does nothing for direct navigation.
    # These headers make the RESPONSE carry its own restriction, so the artifact is inert wherever
    # it is opened — the property the view's docstring claims, now true of the bytes themselves.
    #
    # `sandbox` in CSP puts even a directly-navigated document in a null origin; `default-src
    # 'none'` with `style-src 'unsafe-inline'` admits exactly what a print-clean report needs
    # (its inline <style>) and nothing else — no scripts, no images, no fetch, no frames.
    # `nosniff` stops a content-type disagreement from becoming a rendering decision.
    return HTMLResponse(
        content=rendered.body,
        headers={
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"
            ),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )
