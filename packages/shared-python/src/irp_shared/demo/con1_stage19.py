"""CON-1 demo stage 19 — the first governed CONCENTRATION numbers (ENT-069).

Four demonstrations on real reachable data (OQ-CON-1-20/21/22, the v6 shapes):

1. **DEMO-GLOBAL flagship:** the campaign BOUNDARY exposure run — selected EXPLICITLY by its
   snapshot's valuation date and asserted to exactly one match; NEVER "latest", which is SCH-2's
   dispatched run whose book is 99.98% one issuer (Part 0 fact 10) — concentrated per issuer /
   sector / country over the 100%-classified book.
2. **DEMO-CONCENTRATION:** a NEW dedicated three-instrument book exercising every coverage class
   in one run — CN-ALPHA (classified both dimensions), CN-BETA (issuer-bearing, deliberately
   UNCLASSIFIED), CN-CASH (no issuer → UNCLASSIFIABLE) — with its own exposure run. The Part 2
   at-sight literals (60,000 / 30,000 / 10,000) come from THIS book.
3. **DEMO-MULTIASSET refusal control:** its instruments carry no issuers and no assignments, so
   the whole book is UNCLASSIFIABLE in every dimension — the run COMMITS FAILED with the 0/0
   all-UNCLASSIFIABLE gap (POST-BUILD per the OQ-CON-1-1 timing rule) and ZERO rows.
4. **Counts (OQ-CON-1-22):** +1 model code (``concentration.dimensional``), +1 INITIAL
   validation, +3 COMPLETED runs (GLOBAL concentration; DEMO-CONCENTRATION exposure +
   concentration) — 25/40/133 → 26/41/136; the FAILED refusal run is additionally pinned by
   status and never counted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.classification.models import (
    BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    BASIS_NOT_APPLICABLE,
    DIMENSION_KIND_COUNTRY_OF_RISK,
    DIMENSION_KIND_SECTOR_INDUSTRY,
    SCHEME_FAMILY_ISIC,
    SCHEME_FAMILY_ISO_3166_1,
    ClassificationScheme,
)
from irp_shared.classification.service import ClassificationActor, capture_assignment
from irp_shared.concentration.bootstrap import (
    CONCENTRATION_MODEL_CODE,
    register_concentration_model,
)
from irp_shared.concentration.events import ConcentrationActor
from irp_shared.concentration.service import run_concentration
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.exposure.events import RUN_TYPE_EXPOSURE_AGGREGATE
from irp_shared.model.models import VALIDATION_TYPE_INITIAL
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    record_validation,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.portfolio.models import Portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument, update_instrument
from irp_shared.reference.issuer import create_issuer
from irp_shared.reference.legal_entity import create_legal_entity
from irp_shared.reference.service import ReferenceActor
from irp_shared.snapshot.models import DatasetSnapshot
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

DEMO_ACTOR_ID = "demo_data_steward"
_CODE_VERSION = "demo-con1"
_ENVIRONMENT_ID = "demo"
_COVERAGE_FLOOR = Decimal("0.5")

#: The campaign boundary the flagship exposure run r0 was built at (the Part 2 reference date).
_BOUNDARY_VALUATION_DATE = datetime(2026, 5, 18, tzinfo=UTC).date()

#: Validity base — before every economic as-of (the campaign convention).
_T0 = datetime(2024, 6, 1, tzinfo=UTC)
_BOOK_AS_OF = datetime(2026, 5, 18, tzinfo=UTC)
_MARK_DATE = _BOOK_AS_OF.date()

#: The Part 2 at-sight book: (code, name, asset_class, quantity, mark, issuer key or None).
_BOOK: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    ("CN-ALPHA", "Concentra Alpha Corp equity", "EQUITY", "600", "100.00", "ALPHA-CORP"),
    ("CN-BETA", "Concentra Beta LLC equity", "EQUITY", "300", "100.00", "BETA-LLC"),
    ("CN-CASH", "Concentra cash proxy", "CASH", "100", "100.00", None),
)

#: (issuer code, name, jurisdiction); CN-ALPHA's instrument is classified C26 / US at capture.
_ISSUERS: tuple[tuple[str, str, str], ...] = (
    ("ALPHA-CORP", "Concentra Alpha Corporation", "US"),
    ("BETA-LLC", "Concentra Beta LLC", "US"),
)


class DemoCon1Error(Exception):
    """CON-1 demo-stage refusal."""


class DemoCon1AlreadySeededError(DemoCon1Error):
    """Refuse-not-skip: the stage has already run in this tenant."""


@dataclass(frozen=True)
class Con1Stage19Summary:
    model_version_id: str
    global_concentration_run_id: str
    book_exposure_run_id: str
    book_concentration_run_id: str
    multiasset_failed_run_id: str
    completed_runs_added: int  # 3
    validations_added: int  # 1
    #: OQ-REF-1-29: the codes the demo role was granted and then TORE DOWN (REF-1's four + CON-1's
    #: three). Reported so the stage's test can assert the census rather than trust this docstring.
    entitlement_codes_censused: tuple[str, ...] = ()
    role_permission_rows_torn_down: int = 0


#: The REF-1 + CON-1 read codes OQ-REF-1-29 requires the demo to census. ``concentration.run`` is
#: deliberately absent: this role demonstrates READ access.
_CENSUS_CODES: tuple[str, ...] = (
    "concentration.issuer.view",
    "concentration.view",
    "reference.classification.view",
    "reference.classification_assignment.view",
    "reference.issuer.view",
    "reference.legal_entity.view",
)


def _census_and_teardown_entitlements(session: Session) -> tuple[tuple[str, ...], int]:
    """OQ-REF-1-29, PAID HERE: census the REF-1 + CON-1 read codes against the catalog, grant them
    to a demo role, prove the grant resolves, then TEAR THE GRANTS DOWN and prove none survive.

    REF-1 recorded this as its own obligation and shipped no Role/Permission code at all; the CON-1
    record then recorded it as "paid in CON-1's demo stage" while stage 19 likewise had none. It is
    built now rather than re-deferred a second time.

    The teardown is the point: a demo that only ever GRANTS leaves rows behind that a later census
    reads as production entitlements. Deleting them and asserting zero remain is what makes the
    demonstration honest."""
    from irp_shared.entitlement.models import Permission, Role, RolePermission

    missing = [
        code
        for code in _CENSUS_CODES
        if session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        is None
    ]
    if missing:
        # The catalog is bootstrap-seeded; a missing code means the wrong schema, not a demo gap.
        raise DemoCon1Error(f"permission codes absent from the catalog: {missing}")

    role = Role(
        tenant_id=DEMO_TENANT_ID,
        code="demo_concentration_reader",
        name="Demo concentration reader (OQ-REF-1-29 census)",
    )
    session.add(role)
    session.flush()
    for code in _CENSUS_CODES:
        permission = session.execute(select(Permission).where(Permission.code == code)).scalar_one()
        session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    session.flush()

    granted = {
        session.execute(select(Permission).where(Permission.id == rp.permission_id))
        .scalar_one()
        .code
        for rp in session.execute(
            select(RolePermission).where(RolePermission.role_id == role.id)
        ).scalars()
    }
    if granted != set(_CENSUS_CODES):
        raise DemoCon1Error(
            f"the demo role's grants {sorted(granted)} do not match the "
            f"census {list(_CENSUS_CODES)}"
        )

    torn_down = 0
    for rp in list(
        session.execute(select(RolePermission).where(RolePermission.role_id == role.id)).scalars()
    ):
        session.delete(rp)
        torn_down += 1
    session.flush()
    session.delete(role)
    session.flush()
    survivors = list(
        session.execute(select(RolePermission).where(RolePermission.role_id == role.id)).scalars()
    )
    if survivors:
        raise DemoCon1Error(f"{len(survivors)} role_permission rows survived the teardown")
    return _CENSUS_CODES, torn_down


def _system_scheme(session: Session, family: str, version: str) -> ClassificationScheme:
    scheme = session.execute(
        select(ClassificationScheme).where(
            ClassificationScheme.tenant_id == SYSTEM_TENANT_ID,
            ClassificationScheme.scheme_family == family,
            ClassificationScheme.version_label == version,
        )
    ).scalar_one_or_none()
    if scheme is None:
        raise DemoCon1Error(
            f"the stage-18 SYSTEM {family} {version} scheme is missing — stage 19 must run AFTER "
            f"stage 18"
        )
    return scheme


def _portfolio_by_code(session: Session, code: str) -> Portfolio:
    row = session.execute(
        select(Portfolio).where(Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == code)
    ).scalar_one_or_none()
    if row is None:
        raise DemoCon1Error(f"demo portfolio {code!r} not found — the campaign must run first")
    return row


def _boundary_exposure_run(session: Session, portfolio_id: str) -> CalculationRun:
    """The campaign boundary run, selected EXPLICITLY (OQ-CON-1-20): the COMPLETED exposure run
    whose snapshot valuation date is the boundary — asserted to exactly ONE match."""
    rows = list(
        session.execute(
            select(CalculationRun)
            .join(DatasetSnapshot, DatasetSnapshot.id == CalculationRun.input_snapshot_id)
            .where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_type == RUN_TYPE_EXPOSURE_AGGREGATE,
                CalculationRun.status == "COMPLETED",
                CalculationRun.scope_portfolio_id == str(portfolio_id),
                DatasetSnapshot.as_of_valuation_date == _BOUNDARY_VALUATION_DATE,
            )
        ).scalars()
    )
    if len(rows) != 1:
        raise DemoCon1Error(
            f"expected exactly ONE boundary exposure run at {_BOUNDARY_VALUATION_DATE} for the "
            f"flagship book, found {len(rows)} — the explicit-selection identity is broken"
        )
    return rows[0]


def _earliest_exposure_run(session: Session, portfolio_id: str) -> CalculationRun:
    """DEMO-MULTIASSET's refusal input: the EARLIEST completed exposure run (deterministic and
    explicit — any of its runs works for the 0/0 control; created_at ASC is the stable pick)."""
    row = session.execute(
        select(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.run_type == RUN_TYPE_EXPOSURE_AGGREGATE,
            CalculationRun.status == "COMPLETED",
            CalculationRun.scope_portfolio_id == str(portfolio_id),
        )
        .order_by(CalculationRun.created_at.asc(), CalculationRun.run_id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise DemoCon1Error("DEMO-MULTIASSET has no completed exposure run — MF-1 must run first")
    return row


def run_demo_con1_stage19(session: Session) -> Con1Stage19Summary:
    """Register the model, build the coverage book, and run the three demonstrations."""
    existing = session.execute(
        select(Portfolio).where(
            Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == "DEMO-CONCENTRATION"
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DemoCon1AlreadySeededError("the DEMO-CONCENTRATION book is already seeded")

    isic = _system_scheme(session, SCHEME_FAMILY_ISIC, "Rev. 5")
    countries = _system_scheme(session, SCHEME_FAMILY_ISO_3166_1, "2026")
    schemes = {
        DIMENSION_KIND_SECTOR_INDUSTRY: str(isic.id),
        DIMENSION_KIND_COUNTRY_OF_RISK: str(countries.id),
    }

    # --- 1. The registered model (+1 model code) ---
    version = register_concentration_model(
        session,
        tenant_id=DEMO_TENANT_ID,
        actor_id=DEMO_ACTOR_ID,
        code_version=_CODE_VERSION,
        coverage_floor=_COVERAGE_FLOOR,
    )
    session.flush()

    # --- 2. The DEMO-CONCENTRATION coverage book (Part 2 literals) ---
    ref_actor = ReferenceActor(actor_id=DEMO_ACTOR_ID)
    pf = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="DEMO-CONCENTRATION",
        name="Demo concentration coverage book (CON-1)",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id=DEMO_ACTOR_ID),
    ).id
    issuer_ids: dict[str, str] = {}
    for code, name, jurisdiction in _ISSUERS:
        core = create_legal_entity(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            jurisdiction=jurisdiction,
            actor=ref_actor,
        )
        issuer = create_issuer(
            session,
            tenant_id=DEMO_TENANT_ID,
            legal_entity_id=core.id,
            issuer_type="CORPORATE",
            actor=ref_actor,
        )
        issuer_ids[code] = str(issuer.id)

    demo_actor = ClassificationActor(tenant_id=DEMO_TENANT_ID, actor_id=DEMO_ACTOR_ID)
    for code, name, asset_class, qty, mark, issuer_key in _BOOK:
        inst = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            asset_class=asset_class,
            actor=ref_actor,
        )
        if issuer_key is not None:
            update_instrument(session, inst, actor=ref_actor, issuer_id=issuer_ids[issuer_key])
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst.id,
            acting_tenant=DEMO_TENANT_ID,
            actor=PositionActor(actor_id=DEMO_ACTOR_ID),
            quantity=Decimal(qty),
            valid_from=_T0,
        )
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=inst.id,
            valuation_date=_MARK_DATE,
            acting_tenant=DEMO_TENANT_ID,
            actor=ValuationActor(actor_id=DEMO_ACTOR_ID),
            mark_value=Decimal(mark),
            currency_code="USD",
            valid_from=_T0,
        )
        if code == "CN-ALPHA":
            # Classified on BOTH dimensions at capture — the OQ-CON-1-27 consistent pair form.
            capture_assignment(
                session,
                actor=demo_actor,
                entity_type="instrument",
                entity_id=str(inst.id),
                scheme_id=str(isic.id),
                dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
                node_code="C26",
                basis=BASIS_NOT_APPLICABLE,
                asserted_ancestor_code="C",
            )
            capture_assignment(
                session,
                actor=demo_actor,
                entity_type="instrument",
                entity_id=str(inst.id),
                scheme_id=str(countries.id),
                dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
                node_code="US",
                basis=BASIS_IMMEDIATE_ISSUER_RESIDENCE,
            )
    session.flush()

    book_exposure = run_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ExposureActor(actor_id=DEMO_ACTOR_ID),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        portfolio_id=pf,
        as_of_valid_at=_BOOK_AS_OF,
        base_currency="USD",
    )
    if book_exposure.status != "COMPLETED":
        raise DemoCon1Error("the DEMO-CONCENTRATION exposure run did not COMPLETE — refusing")

    # --- 3. The three demonstrations ---
    con_actor = ConcentrationActor(actor_id=DEMO_ACTOR_ID)

    global_pf = _portfolio_by_code(session, "DEMO-GLOBAL")
    boundary = _boundary_exposure_run(session, str(global_pf.id))
    global_run = run_concentration(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=con_actor,
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=str(version.id),
        exposure_run_id=str(boundary.run_id),
        scheme_by_dimension=schemes,
    )
    if global_run.status != "COMPLETED":
        raise DemoCon1Error(
            f"the flagship concentration run FAILED ({global_run.failure_reason}) — refusing"
        )

    book_run = run_concentration(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=con_actor,
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=str(version.id),
        exposure_run_id=str(book_exposure.run.run_id),
        scheme_by_dimension=schemes,
    )
    if book_run.status != "COMPLETED":
        raise DemoCon1Error(
            f"the coverage-book concentration run FAILED ({book_run.failure_reason}) — refusing"
        )

    multiasset_pf = _portfolio_by_code(session, "DEMO-MULTIASSET")
    multiasset_exposure = _earliest_exposure_run(session, str(multiasset_pf.id))
    refused = run_concentration(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=con_actor,
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=str(version.id),
        exposure_run_id=str(multiasset_exposure.run_id),
        scheme_by_dimension=schemes,
    )
    # The refusal control: the run EXISTS, is FAILED with the 0/0 gap, and wrote ZERO rows —
    # a refusal that silently completed (or silently vanished) would be the fail-open this
    # stage exists to catch (P5: assert by evidence).
    if refused.status != "FAILED":
        raise DemoCon1Error(
            f"the DEMO-MULTIASSET refusal control did not FAIL (status {refused.status}) — the "
            f"0/0 all-UNCLASSIFIABLE gate is broken"
        )
    if refused.rows:
        raise DemoCon1Error("the FAILED refusal run wrote rows — the gaps path is broken")
    if "ALL_UNCLASSIFIABLE" not in (refused.failure_reason or ""):
        raise DemoCon1Error(
            f"the refusal named the wrong gap: {refused.failure_reason!r} (expected the 0/0 "
            f"ALL_UNCLASSIFIABLE gap, not the coverage floor — the v6 re-timing)"
        )

    # --- 4. The INITIAL validation (+1), evidenced by the completed demo runs ---
    record_validation(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ModelValidationActor(actor_id="demo_validator", actor_type="user"),
        request=RecordValidationRequest(
            model_version_id=str(version.id),
            validation_type=VALIDATION_TYPE_INITIAL,
            outcome="APPROVED",
            scope_summary=(
                f"{CONCENTRATION_MODEL_CODE} v1: shares/CR-5/HHI reproduced against the CON-1 "
                "record Part 2 hand-derived literals on the flagship and coverage books; the 0/0 "
                "all-UNCLASSIFIABLE refusal exercised on DEMO-MULTIASSET. NOT a regulatory ratio "
                "(the registered limitation). Validator independence is a demo simplification."
            ),
            report_ref="10_delivery_backlog/con_1_decision_record.md",
            next_review_due=datetime.now(UTC).date() + timedelta(days=365),
            evidence=(
                ValidationEvidenceInput(
                    evidence_type="CALCULATION_RUN", run_id=str(global_run.run.run_id)
                ),
                ValidationEvidenceInput(
                    evidence_type="CALCULATION_RUN", run_id=str(book_run.run.run_id)
                ),
            ),
        ),
    )
    session.flush()

    # --- 4. OQ-REF-1-29: the entitlement census + teardown (REF-1's debt, paid here) ---
    census_codes, torn_down = _census_and_teardown_entitlements(session)

    return Con1Stage19Summary(
        entitlement_codes_censused=census_codes,
        role_permission_rows_torn_down=torn_down,
        model_version_id=str(version.id),
        global_concentration_run_id=str(global_run.run.run_id),
        book_exposure_run_id=str(book_exposure.run.run_id),
        book_concentration_run_id=str(book_run.run.run_id),
        multiasset_failed_run_id=str(refused.run.run_id),
        completed_runs_added=3,
        validations_added=1,
    )
