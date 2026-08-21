"""Governed mapping lifecycle + the load path (W19-S3a, REQ-INT-001).

    propose -> ratify -> load

Every verb runs in the CALLER's single tenant-scoped transaction (no mid-call commit — the endpoint
or the demo stage owns it), the ``irp_shared.ingestion`` precedent.

**What this module is NOT.** It makes no model call. Per OQ-ING-3=A the drafting AI runs
OPERATOR-SIDE and sees SCHEMA ONLY — column names, inferred types, obfuscated sample values, never
client holdings — so no external model call happens inside the deployed product and no API key
exists in the deployed stack. :func:`propose_mapping_version` RECORDS a proposal produced
elsewhere, together with the model version and prompt identity that produced it. That is the point
of the ratified design: the model is a drafting tool AT THE BOUNDARY, never in the path of a number.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_STATUS_CHANGE
from irp_shared.audit.service import record_event
from irp_shared.db.mixins import utcnow
from irp_shared.ingest_mapping.errors import (
    MappingContentImmutableError,
    MappingLifecycleError,
    MappingNotVisible,
    OverlappingLoadError,
    PortfolioCodeNotVisible,
    SelfRatificationError,
    UnknownTargetFieldError,
    UnratifiedMappingError,
)
from irp_shared.ingest_mapping.events import (
    ENTITY_MAPPING_VERSION,
    MAPPING_EVENT,
    SOURCE_MODULE,
)
from irp_shared.ingest_mapping.interpreter import (
    TARGET_COST_BASIS,
    TARGET_FIELDS,
    TARGET_INSTRUMENT,
    TARGET_PORTFOLIO_CODE,
    TARGET_QUANTITY,
    TARGET_QUANTITY_UNIT,
    TARGET_VALID_FROM,
    ResolutionContext,
    assert_targets_coherent,
    declared_operation_kinds,
    interpret_row,
)
from irp_shared.ingest_mapping.models import (
    AUTHORSHIP_HAND_AUTHORED,
    AUTHORSHIP_MODEL_PROPOSED,
    LIFECYCLE_FIELDS,
    STATUS_PROPOSED,
    STATUS_RATIFIED,
    STATUS_SUPERSEDED,
    IngestionMappingVersion,
)
from irp_shared.ingestion.models import IngestionBatch, IngestionStagedRecord
from irp_shared.lineage.models import DataSource
from irp_shared.lineage.service import DataSourceNotVisible
from irp_shared.model.guards import assert_model_version_in_tenant
from irp_shared.portfolio.models import Portfolio
from irp_shared.position import (
    PositionActor,
    correct_position,
    create_position,
    supersede_position,
)
from irp_shared.position.position import _current_open  # noqa: PLC2701 - the bitemporal head read


def canonical_actor(actor_id: str) -> str:
    """Canonicalize an actor id so an identity comparison cannot be defeated by FORMAT.

    A principal id is a UUID, and ``require_uuid_principal_id`` accepts any spelling
    ``uuid.UUID()`` parses — so ``d8c6987d-...`` and ``D8C6987D-...`` are the SAME PERSON to
    authentication and two different strings to ``==``. The slice review reproduced the
    consequence: the proposer re-authenticates with the uppercase spelling and ratifies their own
    mapping, because ``SelfRatificationError`` compared raw strings.

    This is the ``AdminActor`` convention (``entitlement/admin_service.py``), whose docstring says
    identity is canonicalized "so the comparison cannot be defeated by case or format", and the
    ENT-075 four-eyes rail already carries the uppercase-UUID vector as a named test and mutant.
    This slice did not reuse that rail and so did not inherit the lesson; it does now.

    A non-UUID actor id (a service principal, a demo literal) is compared case-folded rather than
    rejected — the guard's job is to refuse self-ratification, not to police id formats.
    """
    text_id = str(actor_id).strip()
    try:
        return str(uuid.UUID(text_id))
    except (ValueError, AttributeError, TypeError):
        return text_id.casefold()


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime to UTC-aware for comparison.

    SQLite hands back NAIVE datetimes from ``DateTime(timezone=True)`` columns while PostgreSQL
    hands back aware ones, so any comparison mixing a stored value with a freshly computed one must
    go through here. Two tiers disagreeing about ``tzinfo`` is exactly the shape that lets a guard
    pass its own unit tests and then never fire — found here by execution, not by reading.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def canonical_operations_hash(operations: Sequence[dict[str, Any]]) -> str:
    """sha256 over a CANONICAL serialization of the operation list — clause (9)'s repro key.

    ``sort_keys`` plus no whitespace, so two mappings differing only in key order hash the same and
    a mapping differing in ONE declared factor does not. The hash is what a reproduction check
    compares; the JSON column is what a human reads.
    """
    blob = json.dumps(list(operations), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _emit(
    session: Session,
    version: IngestionMappingVersion,
    *,
    action: str,
    actor_id: str,
    actor_type: str,
    before_status: str | None,
    outcome: str = "success",
    agent_model: str | None = None,
    agent_model_version: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Emit one ``DATA.MAPPING`` event.

    DC-2 metadata ONLY — the operations HASH and KINDS, never the operations themselves (a
    mapping's column names are client schema) and never a staged cell.
    """
    record_event(
        session,
        event_type=MAPPING_EVENT,
        tenant_id=version.tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        source_module=SOURCE_MODULE,
        entity_type=ENTITY_MAPPING_VERSION,
        entity_id=version.id,
        action=action,
        outcome=outcome,
        before_value=({"status": before_status} if before_status is not None else None),
        after_value={
            "status": version.status,
            "data_source_id": version.data_source_id,
            "source_type": version.source_type,
            "version_label": version.version_label,
            "authorship": version.authorship,
            "operations_hash": version.operations_hash,
            "operation_kinds": sorted(declared_operation_kinds(list(version.operations))),
            "proposer_model_version_id": version.proposer_model_version_id,
            "proposal_prompt_hash": version.proposal_prompt_hash,
            "supersedes_id": version.supersedes_id,
        },
        correlation_id=correlation_id,
        agent_model=agent_model,
        agent_model_version=agent_model_version,
        data_classification="DC-2",
    )


def resolve_mapping_version(
    session: Session, mapping_version_id: str, *, acting_tenant: str
) -> IngestionMappingVersion:
    """Resolve a version by id with an EXPLICIT tenant predicate on top of RLS — defense in depth,
    the domain convention everywhere in this repo."""
    row = session.execute(
        select(IngestionMappingVersion).where(
            IngestionMappingVersion.id == str(mapping_version_id),
            IngestionMappingVersion.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise MappingNotVisible(str(mapping_version_id))
    return row


def assert_only_lifecycle_fields_change(version: IngestionMappingVersion) -> None:
    """Refuse a CONTENT edit on a mapping version.

    **This is no longer the control — the ORM ``before_update`` listener on the model is** (see
    ``models._refuse_content_mutation``). It stayed as an eager pre-flush assertion because it
    fails at the point of the mistake rather than at the next flush, which is a better error.

    The history is worth keeping: this function WAS the only guard, and it could never fire. Both
    of its production call sites assign nothing but lifecycle fields, so it was decorative at both,
    and its two tests called it directly — the "refusal reachable only through a private helper the
    real path never calls" shape. An ordinary ``version.operations = [...]`` plus any subsequent
    query silently persisted the edit through autoflush. Found by the slice review, by execution.
    """
    state = version.__dict__.get("_sa_instance_state")
    if state is None:  # pragma: no cover - a detached object cannot be mid-update
        return
    changed = tuple(
        sorted(
            attr.key
            for attr in state.attrs
            if attr.history.has_changes() and attr.key not in LIFECYCLE_FIELDS
        )
    )
    if changed:
        raise MappingContentImmutableError(changed)


def propose_mapping_version(
    session: Session,
    *,
    tenant_id: str,
    data_source_id: str,
    source_type: str,
    version_label: str,
    operations: list[dict[str, Any]],
    actor_id: str,
    authorship: str = AUTHORSHIP_HAND_AUTHORED,
    proposer_model_version_id: str | None = None,
    proposal_prompt_hash: str | None = None,
    proposal_prompt_ref: str | None = None,
    proposal_response_ref: str | None = None,
    supersedes_id: str | None = None,
    actor_type: str = "user",
    now: datetime | None = None,
) -> IngestionMappingVersion:
    """Record a PROPOSED mapping version.

    Coherence is checked HERE, not only at load: a mapping whose targets are undeclared, whose
    required targets are missing, or whose constants cannot be coerced is refused before a human is
    ever asked to ratify it. Asking a human to approve something unusable is worse than refusing it.

    ``MODEL_PROPOSED`` requires the model version and the prompt identity, and the model version is
    **re-resolved tenant-filtered** before it is stamped — PostgreSQL FK checks bypass RLS, so the
    FK alone would durably admit a cross-tenant reference.
    """
    now = now or utcnow()
    source = session.execute(
        select(DataSource).where(
            DataSource.id == str(data_source_id), DataSource.tenant_id == str(tenant_id)
        )
    ).scalar_one_or_none()
    if source is None:
        raise DataSourceNotVisible(str(data_source_id))

    assert_targets_coherent(operations)

    if authorship == AUTHORSHIP_MODEL_PROPOSED:
        if not proposer_model_version_id or not proposal_prompt_hash:
            raise MappingLifecycleError(
                version_label, authorship, "propose without model version + prompt identity"
            )
        assert_model_version_in_tenant(
            session,
            str(proposer_model_version_id),
            acting_tenant=str(tenant_id),
            error=MappingNotVisible,
        )
    else:
        proposer_model_version_id = None
        proposal_prompt_hash = None

    version = IngestionMappingVersion(
        tenant_id=str(tenant_id),
        data_source_id=source.id,
        source_type=source_type,
        version_label=version_label,
        status=STATUS_PROPOSED,
        operations=list(operations),
        operations_hash=canonical_operations_hash(operations),
        authorship=authorship,
        proposer_model_version_id=proposer_model_version_id,
        proposal_prompt_hash=proposal_prompt_hash,
        proposal_prompt_ref=proposal_prompt_ref,
        proposal_response_ref=proposal_response_ref,
        proposed_by_actor_id=str(actor_id),
        proposed_at=now,
        supersedes_id=(str(supersedes_id) if supersedes_id else None),
    )
    session.add(version)
    session.flush()
    _emit(
        session,
        version,
        action=ACTION_CREATE,
        actor_id=str(actor_id),
        actor_type=actor_type,
        before_status=None,
    )
    return version


def ratify_mapping_version(
    session: Session,
    *,
    mapping_version_id: str,
    acting_tenant: str,
    actor_id: str,
    actor_type: str = "user",
    now: datetime | None = None,
) -> IngestionMappingVersion:
    """Ratify a PROPOSED version, superseding whatever was ratified before it.

    Two refusals fire here. **Lifecycle**: a version that is not PROPOSED cannot be ratified — the
    alternate-path half of the Wave-11 standing review angle, since a gate that fires only in the
    obvious state is not a control. **Self-ratification**: the ratifier may not be the proposer.

    The self-ratification refusal is the REFUSAL HALF of four-eyes only. What makes four-eyes real
    is the permission separation — a ratifier code never co-granted with the proposer path, with
    its P11 holder-set pin, route census and SoD row — and that lands at S3b. Shipping the equality
    check here was ratified as a deliberate widening of S3a's scope line (DS3a-3).
    """
    now = now or utcnow()
    version = resolve_mapping_version(session, mapping_version_id, acting_tenant=acting_tenant)
    if version.status != STATUS_PROPOSED:
        raise MappingLifecycleError(version.id, version.status, "ratify")
    if canonical_actor(actor_id) == canonical_actor(version.proposed_by_actor_id):
        raise SelfRatificationError(str(actor_id))

    # Supersede the incumbent FIRST and FLUSH, so the partial unique index never sees two RATIFIED
    # rows for the same key even transiently — the close-first ordering the FR binders use, for the
    # same reason.
    incumbent = session.execute(
        select(IngestionMappingVersion).where(
            IngestionMappingVersion.tenant_id == str(acting_tenant),
            IngestionMappingVersion.data_source_id == version.data_source_id,
            IngestionMappingVersion.source_type == version.source_type,
            IngestionMappingVersion.status == STATUS_RATIFIED,
        )
    ).scalar_one_or_none()
    if incumbent is not None:
        before = incumbent.status
        incumbent.status = STATUS_SUPERSEDED
        incumbent.superseded_at = now
        assert_only_lifecycle_fields_change(incumbent)
        session.flush()
        _emit(
            session,
            incumbent,
            action=ACTION_STATUS_CHANGE,
            actor_id=str(actor_id),
            actor_type=actor_type,
            before_status=before,
        )

    before = version.status
    version.status = STATUS_RATIFIED
    version.ratified_by_actor_id = str(actor_id)
    version.ratified_at = now
    assert_only_lifecycle_fields_change(version)
    session.flush()
    _emit(
        session,
        version,
        action=ACTION_STATUS_CHANGE,
        actor_id=str(actor_id),
        actor_type=actor_type,
        before_status=before,
    )
    return version


def ratified_mapping_for(
    session: Session, *, acting_tenant: str, data_source_id: str, source_type: str
) -> IngestionMappingVersion:
    """The one RATIFIED version for a (source, source_type), or REFUSE — clause (1)."""
    row = session.execute(
        select(IngestionMappingVersion).where(
            IngestionMappingVersion.tenant_id == str(acting_tenant),
            IngestionMappingVersion.data_source_id == str(data_source_id),
            IngestionMappingVersion.source_type == str(source_type),
            IngestionMappingVersion.status == STATUS_RATIFIED,
        )
    ).scalar_one_or_none()
    if row is None:
        raise UnratifiedMappingError(str(data_source_id), str(source_type))
    return row


class LoadResult:
    """What one load produced — the evidence a caller and a test both read."""

    def __init__(
        self,
        *,
        mapping_version: IngestionMappingVersion,
        lookup_as_of: datetime,
        created: list[str],
        restated: list[str],
        superseded: list[str],
        lookups: dict[str, int],
    ) -> None:
        self.mapping_version = mapping_version
        self.lookup_as_of = lookup_as_of
        self.created = created
        self.restated = restated
        self.superseded = superseded
        self.lookups = lookups

    @property
    def row_count(self) -> int:
        return len(self.created) + len(self.restated) + len(self.superseded)


def load_batch(
    session: Session,
    *,
    batch: IngestionBatch,
    acting_tenant: str,
    actor: PositionActor,
    source_type: str,
    restatement_reason: str | None = None,
    now: datetime | None = None,
) -> LoadResult:
    """Interpret a staged batch into canonical positions through its RATIFIED mapping version.

    **This is the only path from staged rows to canonical positions** (clause 4). It:

    1. resolves the RATIFIED mapping for the batch's ``data_source`` — or refuses (clause 1);
    2. stamps the batch's ``mapping_version_id`` and ``lookup_as_of``, so the load is reproducible
       from the three inputs clause (9) names;
    3. interprets every staged row in ``row_number`` order;
    4. writes each position through the governed binder, with the ORIGIN lineage edge rooted at the
       INGESTION data source rather than the tenant's MANUAL root (DS3a-4) — a file-loaded holding
       recorded as manual entry would be a false provenance record, which is worse than none.

    An overlapping re-load REFUSES unless ``restatement_reason`` is supplied (DP-19-7, fail-closed);
    a flagged restatement supersedes bitemporally through ``correct_position``, the shipped TR-08
    rail rather than a new one.
    """
    now = now or utcnow()
    mapping = ratified_mapping_for(
        session,
        acting_tenant=acting_tenant,
        data_source_id=batch.data_source_id,
        source_type=source_type,
    )
    source = session.execute(
        select(DataSource).where(DataSource.id == str(batch.data_source_id))
    ).scalar_one_or_none()
    if source is None:  # pragma: no cover - the batch's own FK guarantees it
        raise DataSourceNotVisible(str(batch.data_source_id))

    batch.mapping_version_id = mapping.id
    batch.lookup_as_of = now
    session.flush()

    ctx = ResolutionContext(session=session, acting_tenant=str(acting_tenant), lookup_as_of=now)
    operations = list(mapping.operations)

    staged = (
        session.execute(
            select(IngestionStagedRecord)
            .where(IngestionStagedRecord.batch_id == batch.id)
            .order_by(IngestionStagedRecord.row_number)
        )
        .scalars()
        .all()
    )

    created: list[str] = []
    restated: list[str] = []
    superseded: list[str] = []
    for record in staged:
        values = interpret_row(operations, dict(record.payload), record.row_number, ctx)
        portfolio = _resolve_portfolio_by_code(
            session, str(values[TARGET_PORTFOLIO_CODE]), acting_tenant=str(acting_tenant)
        )
        instrument_id = str(values[TARGET_INSTRUMENT])
        valid_from = values[TARGET_VALID_FROM]

        head = _current_open(
            session,
            acting_tenant=str(acting_tenant),
            portfolio_id=portfolio.id,
            instrument_id=instrument_id,
        )
        # THE COMPARISON MUST NORMALIZE, and this is not pedantry: SQLite returns a NAIVE datetime
        # from a DateTime(timezone=True) column while the interpreter produces a UTC-aware one, so
        # a raw `==` is False for two identical instants. The overlap check would never fire, the
        # loader would fall through to a create, and the failure would surface as a raw
        # IntegrityError from `uq_position_current` instead of the governed refusal.
        head_at = _as_utc(head.valid_from) if head is not None else None
        loaded_at = _as_utc(valid_from)
        if loaded_at is None:
            # `assert_targets_coherent` makes valid_from a REQUIRED target at proposal time, so a
            # ratified mapping cannot omit it. This is the belt to that braces: an operation could
            # still evaluate to None at load time, and a null valid_from would open a version whose
            # validity period nothing can reason about.
            raise UnknownTargetFieldError(TARGET_VALID_FROM, TARGET_FIELDS)
        if head is not None and head_at is not None:
            if head_at == loaded_at:
                # The overlap DP-19-7 governs: same holding, same as-of, already open.
                if restatement_reason is None:
                    raise OverlappingLoadError(portfolio.id, instrument_id, record.row_number)
                corrected = correct_position(
                    session,
                    head,
                    restatement_reason=restatement_reason,
                    acting_tenant=str(acting_tenant),
                    actor=actor,
                    now=now,
                    origin_source=source,
                    quantity=values[TARGET_QUANTITY],
                    cost_basis=values.get(TARGET_COST_BASIS),
                    quantity_unit=values.get(TARGET_QUANTITY_UNIT),
                )
                restated.append(corrected.id)
                continue
            if loaded_at < head_at:
                # A BACKDATED file against an open later head. Refused ALWAYS, flagged or not: an
                # as-known correction cannot express "this is the truth for an earlier valid date
                # than the one already open", and letting it through would silently reorder a
                # client's history. Out of scope for a restatement flag, not covered by one.
                raise OverlappingLoadError(portfolio.id, instrument_id, record.row_number)
            # A LATER as-of: the ordinary next periodic file. An effective-dated supersede, which
            # is NOT an overlap and correctly needs no restatement flag.
            newer = supersede_position(
                session,
                portfolio_id=portfolio.id,
                instrument_id=instrument_id,
                acting_tenant=str(acting_tenant),
                actor=actor,
                effective_at=valid_from,
                now=now,
                origin_source=source,
                quantity=values[TARGET_QUANTITY],
                cost_basis=values.get(TARGET_COST_BASIS),
                quantity_unit=values.get(TARGET_QUANTITY_UNIT),
            )
            superseded.append(newer.id)
            continue

        # No open head: the first capture of this holding.
        row = create_position(
            session,
            portfolio_id=portfolio.id,
            instrument_id=instrument_id,
            acting_tenant=str(acting_tenant),
            actor=actor,
            quantity=values[TARGET_QUANTITY],
            valid_from=valid_from,
            cost_basis=values.get(TARGET_COST_BASIS),
            quantity_unit=values.get(TARGET_QUANTITY_UNIT),
            now=now,
            origin_source=source,
        )
        created.append(row.id)

    return LoadResult(
        mapping_version=mapping,
        lookup_as_of=now,
        created=created,
        restated=restated,
        superseded=superseded,
        lookups=dict(ctx.resolved),
    )


def _resolve_portfolio_by_code(session: Session, code: str, *, acting_tenant: str) -> Portfolio:
    """Resolve a portfolio by its firm-assigned ``code``, tenant-predicated.

    NOT a ``code-lookup`` operation: ``resolve_identifier`` — the platform's only as-of-capable
    resolver — is hard-fenced to ``entity_type='instrument'`` (the P1B-3 scope fence), and lifting
    that fence is its own surface with its own review. A multi-account file therefore needs either
    a portfolio resolver or that fence lifted, and that is an S3b / Wave-20 entry condition rather
    than something assumed away here. The demonstrating file is single-account and its portfolio
    arrives through a ``constant`` operation.
    """
    row = session.execute(
        select(Portfolio).where(Portfolio.tenant_id == str(acting_tenant), Portfolio.code == code)
    ).scalar_one_or_none()
    if row is None:
        # Its OWN class: `MappingNotVisible` stores its argument as `mapping_version_id`, so a
        # handler reading that attribute to report which MAPPING was not visible would have
        # been handed a portfolio code. A record that mislabels what failed to resolve is a
        # small false record, and small false records are how the large ones start.
        raise PortfolioCodeNotVisible(code)
    return row
