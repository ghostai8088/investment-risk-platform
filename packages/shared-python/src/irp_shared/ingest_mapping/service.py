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

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_CREATE, ACTION_STATUS_CHANGE
from irp_shared.audit.service import record_event
from irp_shared.db.mixins import utcnow
from irp_shared.ingest_mapping.errors import (
    MappingContentImmutableError,
    MappingLifecycleError,
    MappingNotVisible,
    NotTheProposerError,
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
    STATUS_WITHDRAWN,
    IngestionMappingVersion,
)
from irp_shared.ingest_mapping.ratification_models import (
    OUTCOME_RATIFIED,
    OUTCOME_SUPERSEDED,
    OUTCOME_WITHDRAWN,
    IngestionMappingRatification,
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


def _lock_tenant(session: Session, tenant_id: str) -> None:
    """Serialize mapping resolutions within a tenant (PostgreSQL; no-op elsewhere).

    Without it the ``seq`` assignment and the one-ratified-mapping invariant are both TOCTOU: two
    ratifiers read the same ``max(seq)`` and race, and two resolutions for two different versions of
    one source can pass their individual checks. Keyed on the tenant, transaction-scoped, released
    at COMMIT — the ``admin_service._lock_tenant`` pattern, reused rather than re-invented.

    **It is a literal no-op off PostgreSQL, and that is why its proof is a `_pg` test with real
    threads.** SQLite serializes writes at the file level anyway, so deleting this call is invisible
    to any single-connection unit test — a mutant would be killed by nothing. The remit's
    verification caught that before the mutant was written.
    """
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        key = int.from_bytes(uuid.UUID(str(tenant_id)).bytes[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


def _next_seq(session: Session, tenant_id: str) -> int:
    """Per-tenant monotonic sequence, assigned under the tenant lock (the MG-2 pattern).

    A state machine over an append-only log needs a DB-monotonic ordering key: a wall clock ties,
    and two ratifiers acting in the same millisecond is precisely what this table adjudicates.
    """
    current = session.execute(
        select(func.max(IngestionMappingRatification.seq)).where(
            IngestionMappingRatification.tenant_id == str(tenant_id)
        )
    ).scalar()
    return int(current or 0) + 1


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

    # `supersedes_id` gets the SAME treatment as `proposer_model_version_id` above, and the reason
    # is written out because S3a applied it to one field and not to the other sitting beside it.
    # It is a self-FK, and PostgreSQL evaluates FK checks BYPASSING RLS — so the constraint happily
    # accepts another tenant's version id and the row durably records a cross-tenant reference.
    # Nothing downstream would catch it: `supersedes_id` is lineage prose to every read that shows
    # it. Resolving it tenant-filtered is the only place this can be refused.
    if supersedes_id is not None:
        resolve_mapping_version(session, str(supersedes_id), acting_tenant=str(tenant_id))

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
    reason: str | None = None,
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
    _lock_tenant(session, acting_tenant)
    version = resolve_mapping_version(session, mapping_version_id, acting_tenant=acting_tenant)
    if version.status != STATUS_PROPOSED:
        raise MappingLifecycleError(version.id, version.status, "ratify")
    if canonical_actor(actor_id) == canonical_actor(version.proposed_by_actor_id):
        raise SelfRatificationError(str(actor_id))

    # The incumbent is found through the RESOLUTION table too, by the same latest-row rule.
    # Reading ENT-077.status here would reintroduce the dependency this slice removed.
    incumbent_row = session.execute(
        select(IngestionMappingRatification)
        .where(
            IngestionMappingRatification.tenant_id == str(acting_tenant),
            IngestionMappingRatification.data_source_id == version.data_source_id,
            IngestionMappingRatification.source_type == version.source_type,
        )
        .order_by(IngestionMappingRatification.seq.desc())
        .limit(1)
    ).scalar_one_or_none()
    incumbent = None
    if incumbent_row is not None and incumbent_row.outcome == OUTCOME_RATIFIED:
        incumbent = session.execute(
            select(IngestionMappingVersion).where(
                IngestionMappingVersion.id == incumbent_row.mapping_version_id
            )
        ).scalar_one_or_none()
    if incumbent is not None:
        # CLOSE FIRST, and the ORDER IS THE INVARIANT — not a tidiness preference, and not (as an
        # earlier draft of this comment claimed) protection for a partial unique index, which this
        # table does not have. "Which mapping governs this source" is answered by the HIGHEST `seq`
        # for the source. Append the SUPERSEDED row second and it outranks the new RATIFIED row, so
        # the source reads back as having NO current mapping and every subsequent load refuses.
        # `_next_seq` allocates in call order, so the call order IS the answer.
        session.add(
            IngestionMappingRatification(
                tenant_id=str(acting_tenant),
                seq=_next_seq(session, acting_tenant),
                mapping_version_id=incumbent.id,
                data_source_id=incumbent.data_source_id,
                source_type=incumbent.source_type,
                outcome=OUTCOME_SUPERSEDED,
                resolved_by=str(actor_id),
                resolved_at=now,
                reason=f"superseded by {version.version_label}",
            )
        )
        session.flush()

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

    # THE DECISION, recorded as an APPEND-ONLY ROW before anything else. ENT-077's status is a
    # projection of this fact, never the authority for it — a ratification that lives only in a
    # mutable column can be edited into existence after the fact, and ENT-077's content guard is an
    # ORM listener that does not fire on a non-ORM write.
    session.add(
        IngestionMappingRatification(
            tenant_id=str(acting_tenant),
            seq=_next_seq(session, acting_tenant),
            mapping_version_id=version.id,
            data_source_id=version.data_source_id,
            source_type=version.source_type,
            outcome=OUTCOME_RATIFIED,
            resolved_by=str(actor_id),
            resolved_at=now,
            reason=reason,
        )
    )
    session.flush()

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
    # RESOLVED THROUGH ENT-078, and specifically through its LATEST row for this source.
    #
    # Not through ENT-077's `status`: that is a mutable column whose only guard is an ORM listener,
    # so a gate reading it would let a non-ORM UPDATE decide which mapping governs a client's
    # holdings. And an append-only decision table the load path does not consult is evidence nobody
    # reads — the declaration-without-consumption defect, which the remit's verification caught.
    #
    # LATEST, not "any RATIFIED row": on an append-only log the incumbent's ratification is still
    # there after it is superseded, so "is there a RATIFIED row" is true forever once it has been
    # true once. The current decision is the last one made, and `uq_..._seq` makes that unique.
    latest = session.execute(
        select(IngestionMappingRatification)
        .where(
            IngestionMappingRatification.tenant_id == str(acting_tenant),
            IngestionMappingRatification.data_source_id == str(data_source_id),
            IngestionMappingRatification.source_type == str(source_type),
        )
        .order_by(IngestionMappingRatification.seq.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is None or latest.outcome != OUTCOME_RATIFIED:
        raise UnratifiedMappingError(str(data_source_id), str(source_type))
    row = session.execute(
        select(IngestionMappingVersion).where(
            IngestionMappingVersion.id == latest.mapping_version_id,
            IngestionMappingVersion.tenant_id == str(acting_tenant),
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
                    # The CORRECTION's provenance is whatever produced the correction, never what
                    # produced the row being corrected (DS3b-3, per verb).
                    mapping_version_id=mapping.id,
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
                # NOT carried from the prior version: this row was produced by THIS load. Without
                # the explicit stamp the column would be dropped to NULL here, and a provenance FK
                # that vanishes when the second file arrives is worse than none.
                mapping_version_id=mapping.id,
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
            # Clause (2)'s position half: the ratifying mapping version, by hard FK.
            mapping_version_id=mapping.id,
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


def withdraw_mapping_version(
    session: Session,
    *,
    mapping_version_id: str,
    acting_tenant: str,
    actor_id: str,
    reason: str,
    actor_type: str = "user",
    now: datetime | None = None,
) -> IngestionMappingVersion:
    """The PROPOSER takes their own proposal back (DS3b-6, owner-ratified).

    ``STATUS_WITHDRAWN`` was declared at S3a with no path producing it — the inert-state class the
    ENT-075 review struck when it deleted ``REJECTED``: a state an auditor can read in the
    vocabulary and infer a flow that does not exist. This is the verb that makes it real, shipped
    beside the lifecycle it belongs to rather than left for a future gate.

    **Withdrawal is NOT rejection, and the distinction is deliberate.** A checker's refusal to
    ratify is inaction: the version stays PROPOSED for someone else to approve or for nobody to.
    Withdrawal is the PROPOSER's own act — a different fact with a different actor — which is why it
    is a resolution OUTCOME here rather than a status nobody writes. There is still no reject verb,
    for exactly ENT-075's recorded reason.

    A ``reason`` is REQUIRED. A proposal removed from the queue with no explanation is the shape an
    auditor cannot distinguish from one that was never made.
    """
    now = now or utcnow()
    _lock_tenant(session, acting_tenant)
    version = resolve_mapping_version(session, mapping_version_id, acting_tenant=acting_tenant)
    if version.status != STATUS_PROPOSED:
        # A RATIFIED version is not withdrawn, it is SUPERSEDED by ratifying a replacement — the
        # alternate-path half, because a gate that fires only in the obvious state is not a control.
        raise MappingLifecycleError(version.id, version.status, "withdraw")
    if canonical_actor(actor_id) != canonical_actor(version.proposed_by_actor_id):
        raise NotTheProposerError(str(actor_id), str(version.proposed_by_actor_id))

    session.add(
        IngestionMappingRatification(
            tenant_id=str(acting_tenant),
            seq=_next_seq(session, acting_tenant),
            mapping_version_id=version.id,
            data_source_id=version.data_source_id,
            source_type=version.source_type,
            outcome=OUTCOME_WITHDRAWN,
            resolved_by=str(actor_id),
            resolved_at=now,
            reason=reason,
        )
    )
    session.flush()

    before = version.status
    version.status = STATUS_WITHDRAWN
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
