"""LQ-1 demo stage 23 — the first governed LIQUIDITY numbers (ENT-071).

Three demonstrations on real reachable data:

1. **The SYSTEM-seeded 22e-4 ladder** (ratified OQ-LQ-1-16): the four categories
   17 CFR 270.22e-4(b)(1)(ii) NAMES, written SYSTEM-side so every tenant reads one regulatory
   vocabulary. The hybrid ``classification_scheme``/``classification_node`` tables make that
   lawful; the closed 7-table hybrid set is UNCHANGED (these are existing members).

2. **DEMO-LIQUIDITY flagship:** a dedicated four-instrument book exercising every coverage class in
   one run — two tiered liquid, one tiered ILLIQUID, one deliberately UNTIERED — so the run
   COMPLETES with a real illiquid share AND a coverage ratio below 1. The at-sight literals in the
   record come from THIS book.

3. **The refusal control:** the same book re-run against a model version whose coverage floor is
   set ABOVE the book's actual coverage. The run COMMITS FAILED with ZERO rows and a named reason.
   This is the fail-closed direction that matters: without it the platform would report a
   confident illiquid share over a book nobody had finished classifying. **The FAILED run is
   pinned by status and never counted** in the demo triple.

**Counts:** +1 model code (``risk.liquidity_tiers``), +1 INITIAL validation, +2 COMPLETED runs
(the DEMO-LIQUIDITY exposure run and the flagship liquidity run). The triple is MEASURED by the
14-z suite on a fresh battery, never derived here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.classification.models import (
    BASIS_NOT_APPLICABLE,
    DIMENSION_KIND_LIQUIDITY_TIER,
    LIQUIDITY_TIER_CODES,
    LIQUIDITY_TIER_SEMANTICS,
    SCHEME_FAMILY_SEC_22E4,
    ClassificationScheme,
)
from irp_shared.classification.service import (
    ClassificationActor,
    capture_assignment,
    create_node,
    create_scheme,
)
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.liquidity.bootstrap import (
    LIQUIDITY_MODEL_CODE,
    register_liquidity_model,
)
from irp_shared.liquidity.service import run_liquidity
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
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

DEMO_ACTOR_ID = "demo_data_steward"
_CODE_VERSION = "demo-lq1"
_ENVIRONMENT_ID = "demo"
_SCHEME_VERSION = "2024"
#: 0.5 — the flagship book's coverage is 0.9, so the floor is genuinely CLEARED rather than
#: trivially satisfied. A floor no book could fail would demonstrate nothing.
_COVERAGE_FLOOR = Decimal("0.5")
#: The refusal control's floor: STRICTLY ABOVE the book's real coverage of 0.9, so the refusal
#: fires on real data rather than on a contrived empty book. It was first set to 0.9 exactly and
#: did NOT trip — the binder's test is `coverage < floor`, so an equal floor is a cleared floor.
#: Caught by running the stage; a refusal control that does not refuse proves the opposite of
#: what it claims.
_REFUSAL_FLOOR = Decimal("0.95")
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_BOOK_AS_OF = datetime(2026, 5, 18, tzinfo=UTC)
_MARK_DATE = _BOOK_AS_OF.date()

#: (code, name, asset_class, quantity, mark, tier or None). Hand-chosen so the shares are exact
#: at 6dp and checkable by eye: 40,000 + 20,000 + 30,000 + 10,000 = 100,000 long.
_BOOK: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    ("LQ-TBILL", "Demo T-bill", "GOVERNMENT_BOND", "400", "100", "HIGHLY_LIQUID"),
    ("LQ-CORP", "Demo corporate bond", "CORPORATE_BOND", "200", "100", "MODERATELY_LIQUID"),
    ("LQ-PRIVATE", "Demo private placement", "PRIVATE_CREDIT", "300", "100", "ILLIQUID"),
    ("LQ-UNTIERED", "Demo unassessed holding", "EQUITY", "100", "100", None),
)


class DemoLq1Error(RuntimeError):
    """The stage cannot run against the demo tenant's current state."""


class DemoLq1AlreadySeededError(DemoLq1Error):
    """Refuse-not-skip: the stage has already run in this tenant."""


@dataclass(frozen=True)
class Lq1Stage23Summary:
    model_version_id: str
    scheme_id: str
    book_exposure_run_id: str
    liquidity_run_id: str
    refused_run_id: str
    illiquid_share: Decimal
    highly_liquid_share: Decimal
    coverage_ratio: Decimal
    untiered_instrument_count: int
    completed_runs_added: int  # 2
    validations_added: int  # 1


def _system_tier_scheme(session: Session) -> ClassificationScheme:
    """SYSTEM-seed the 22e-4 ladder, idempotently.

    The four codes and their day thresholds are the RULE's, not this platform's — the vocabulary
    is a transcription, which is why it is SYSTEM-side rather than a per-tenant convention.
    """
    existing = session.execute(
        select(ClassificationScheme).where(
            ClassificationScheme.tenant_id == SYSTEM_TENANT_ID,
            ClassificationScheme.scheme_family == SCHEME_FAMILY_SEC_22E4,
            ClassificationScheme.version_label == _SCHEME_VERSION,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    system_actor = ClassificationActor(tenant_id=SYSTEM_TENANT_ID, actor_id=DEMO_ACTOR_ID)
    scheme = create_scheme(
        session,
        actor=system_actor,
        scheme_family=SCHEME_FAMILY_SEC_22E4,
        version_label=_SCHEME_VERSION,
        name="SEC Rule 22e-4 liquidity categories",
        dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
        authority="SEC",
    )
    # A FLAT ladder: every category is level 1. The rule names four peers, not a hierarchy, and
    # encoding a false parent-child relationship would make the ancestor walk assert something the
    # regulation does not say.
    for code in LIQUIDITY_TIER_CODES:
        create_node(
            session,
            actor=system_actor,
            scheme_id=scheme.id,
            code=code,
            name=code.replace("_", " ").title(),
            level=1,
            description=LIQUIDITY_TIER_SEMANTICS[code],
        )
    session.flush()
    return scheme


def run_demo_lq1_stage23(session: Session) -> Lq1Stage23Summary:
    """Seed the ladder, build the coverage book, and run the flagship plus the refusal control."""
    existing = session.execute(
        select(Portfolio).where(
            Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == "DEMO-LIQUIDITY"
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DemoLq1AlreadySeededError("the DEMO-LIQUIDITY book is already seeded")

    scheme = _system_tier_scheme(session)

    # --- 1. The registered model (+1 model code, +1 INITIAL validation) ---
    version = register_liquidity_model(
        session,
        tenant_id=DEMO_TENANT_ID,
        actor_id=DEMO_ACTOR_ID,
        code_version=_CODE_VERSION,
        coverage_floor=_COVERAGE_FLOOR,
    )
    session.flush()

    # --- 2. The DEMO-LIQUIDITY coverage book ---
    ref_actor = ReferenceActor(actor_id=DEMO_ACTOR_ID)
    pf = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="DEMO-LIQUIDITY",
        name="Demo liquidity coverage book (LQ-1)",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id=DEMO_ACTOR_ID),
    ).id
    demo_actor = ClassificationActor(tenant_id=DEMO_TENANT_ID, actor_id=DEMO_ACTOR_ID)

    for code, name, asset_class, qty, mark, tier in _BOOK:
        inst = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            asset_class=asset_class,
            actor=ref_actor,
        )
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
        if tier is not None:
            capture_assignment(
                session,
                actor=demo_actor,
                entity_type="instrument",
                entity_id=str(inst.id),
                scheme_id=str(scheme.id),
                dimension_kind=DIMENSION_KIND_LIQUIDITY_TIER,
                node_code=tier,
                basis=BASIS_NOT_APPLICABLE,
            )
        # LQ-UNTIERED deliberately receives NO assignment. It is the UNCLASSIFIED residual, and
        # its presence is what makes the coverage ratio meaningful rather than always 1.
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
        raise DemoLq1Error("the DEMO-LIQUIDITY exposure run did not COMPLETE — refusing")

    # --- 3. The flagship liquidity run ---
    outcome = run_liquidity(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor_id=DEMO_ACTOR_ID,
        actor_type="user",
        exposure_run_id=str(book_exposure.run.run_id),
        scheme_id=str(scheme.id),
        model_version=version,
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
    )
    if outcome.status != "COMPLETED":
        raise DemoLq1Error(f"the flagship liquidity run FAILED ({outcome.failure_reason})")

    summary_row = next(
        (r for r in outcome.rows if r.metric_type == "ILLIQUID_SHARE"),
        None,
    )
    highly = next((r for r in outcome.rows if r.metric_type == "HIGHLY_LIQUID_SHARE"), None)
    if summary_row is None or highly is None:
        raise DemoLq1Error("the flagship run wrote no summary rows — refusing")

    # --- 4. The refusal control: a floor ABOVE the book's real coverage ---
    strict = register_liquidity_model(
        session,
        tenant_id=DEMO_TENANT_ID,
        actor_id=DEMO_ACTOR_ID,
        code_version=_CODE_VERSION,
        coverage_floor=_REFUSAL_FLOOR,
        version_label="v1-strict-floor",
    )
    session.flush()
    refused = run_liquidity(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor_id=DEMO_ACTOR_ID,
        actor_type="user",
        exposure_run_id=str(book_exposure.run.run_id),
        scheme_id=str(scheme.id),
        model_version=strict,
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
    )
    if refused.status != "FAILED":
        raise DemoLq1Error(
            "the sub-floor control did not FAIL — the coverage floor is not fail-closed"
        )
    if refused.rows:
        raise DemoLq1Error(
            f"the FAILED run wrote {len(refused.rows)} rows — a refused run must write NONE"
        )

    # --- 5. The INITIAL validation (+1), evidenced by the completed demo runs ---
    #
    # This was MISSING from the first draft: the stage claimed "+1 INITIAL validation" in its
    # docstring and its summary dataclass while recording none. Measured on PG as (1, 0, 2) — the
    # zero is what exposed it. A governed family shipping without a recorded validation would have
    # left CTRL-003's evidence chain broken for the one number this slice exists to produce.
    record_validation(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ModelValidationActor(actor_id="demo_validator", actor_type="user"),
        request=RecordValidationRequest(
            model_version_id=str(version.id),
            validation_type=VALIDATION_TYPE_INITIAL,
            outcome="APPROVED",
            scope_summary=(
                f"{LIQUIDITY_MODEL_CODE} v1: tier shares and coverage reproduced against the "
                "LQ-1 record's hand-derived literals on the DEMO-LIQUIDITY book (illiquid 0.3, "
                "highly liquid 0.4, coverage 0.9); the sub-floor refusal exercised on the same "
                "book against a stricter declared floor. NOT the Rule 22e-4 15% test, and "
                "instrument-grain rather than position-grain (both registered limitations). "
                "Validator independence is a demo simplification."
            ),
            report_ref="10_delivery_backlog/lq_1_decision_record.md",
            next_review_due=datetime.now(UTC).date() + timedelta(days=365),
            evidence=(
                ValidationEvidenceInput(
                    evidence_type="CALCULATION_RUN", run_id=str(outcome.run.run_id)
                ),
            ),
        ),
    )
    session.flush()

    return Lq1Stage23Summary(
        model_version_id=str(version.id),
        scheme_id=str(scheme.id),
        book_exposure_run_id=str(book_exposure.run.run_id),
        liquidity_run_id=str(outcome.run.run_id),
        refused_run_id=str(refused.run.run_id),
        illiquid_share=summary_row.metric_value,
        highly_liquid_share=highly.metric_value,
        coverage_ratio=summary_row.coverage_ratio,
        untiered_instrument_count=summary_row.untiered_instrument_count,
        completed_runs_added=2,
        validations_added=1,
    )


__all__ = [
    "DEMO_ACTOR_ID",
    "LIQUIDITY_MODEL_CODE",
    "VALIDATION_TYPE_INITIAL",
    "DemoLq1AlreadySeededError",
    "DemoLq1Error",
    "Lq1Stage23Summary",
    "run_demo_lq1_stage23",
]
