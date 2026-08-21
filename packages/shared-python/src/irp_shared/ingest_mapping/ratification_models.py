"""ENT-078 ``ingestion_mapping_ratification`` — four-eyes that cannot be edited into existence.

**Why a second table, when ENT-077 already has ``ratified_by_actor_id``.** Because an approval
recorded by MUTATING a row can be edited after the fact, and ENT-077 is status-mutable by design.
Worse, its content guard is an ORM ``before_update`` listener, which does not fire on any non-ORM
write path — so ratification evidence living in ENT-077's own columns is editable at the database by
anything that does not go through the ORM. The approval is the one fact in this whole spine that has
to be unfalsifiable.

ENT-075's own docstring records the same lesson being learned the hard way: *"The first
implementation of this module described that design in this docstring and then recorded approval
by MUTATING the request row — which every SQLite test accepted and PostgreSQL's
``irp_prevent_mutation`` trigger refused outright."* This table is the shape that fix produced,
applied deliberately rather than after the trigger catches it.

**A resolution is a NEW ROW**, referencing the mapping version it decides. IA TRUE append-only: in
``APPEND_ONLY_TABLES``, with the ``irp_prevent_mutation`` trigger AND the ORM guard — the 0072
belt-and-braces pattern, because ENT-075 shipped without the ORM half and only the trigger caught
its first mutation.

**The per-tenant monotonic ``seq`` is app-assigned under the tenant advisory lock** (the MG-2
pattern). A state machine over an append-only log needs a DB-monotonic ordering key: a wall clock
ties, and two ratifiers acting in the same millisecond is exactly what this table adjudicates.
ENT-077 had no lock on its ratify path at all, so the lock lands WITH this lifecycle rather than
after it.

**This table OWNS the "at most one RATIFIED mapping per source" invariant** (DS3b-5,
owner-ratified). ``data_source_id`` and ``source_type`` are denormalized onto the row for one
reason: so the question "which mapping is current for this source?" is answered from the
append-only surface instead of from ENT-077's mutable ``status``. The slice's headline claim is that
approval facts must be unfalsifiable; leaving the invariant resting on the column the table exists
to stop trusting would have left that claim resting on the thing it just argued against.

It is enforced STRUCTURALLY — the latest resolution row per source **whose outcome is in
``GOVERNING_OUTCOMES``**, made unique by ``uq_..._seq`` — and **not** by a partial unique index. Two
index drafts were written and the database refused both; the ``__table_args__`` comment records why,
because that is where a reader looking for the missing index will go.

The ``GOVERNING_OUTCOMES`` filter is not a detail. Without it a ``WITHDRAWN`` row for an unrelated
competing proposal outranks a live ratification and the source reads back as ungoverned — a BLOCKING
defect this table shipped with and a different-engine review found. See the constant.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: What a resolution row DECIDES. A total enumeration with a DB CHECK (the 0053 pattern): an
#: unenumerated outcome must fail CLOSED, because an outcome nobody enumerated is an outcome nobody
#: decided needed four eyes.
#:
#: There is deliberately no REJECT: a checker's refusal to ratify is inaction, and the version stays
#: PROPOSED. WITHDRAW is the PROPOSER's act of taking their own proposal back — a different fact
#: with a different actor, which is why it is a resolution outcome and not a status nobody writes.
OUTCOME_RATIFIED = "RATIFIED"
OUTCOME_WITHDRAWN = "WITHDRAWN"
#: A version that WAS ratified and has since been replaced. Appended as its own row rather than
#: recorded by editing the RATIFIED one — see the class docstring's note on why a life is a
#: SEQUENCE of facts, which is the whole reason this table is append-only.
OUTCOME_SUPERSEDED = "SUPERSEDED"
RESOLUTION_OUTCOMES: tuple[str, ...] = (
    OUTCOME_RATIFIED,
    OUTCOME_WITHDRAWN,
    OUTCOME_SUPERSEDED,
)

#: The outcomes that speak to WHICH VERSION GOVERNS A SOURCE, as opposed to what happened to one
#: proposal. **This distinction is the fix for a BLOCKING defect the first build shipped**, and it
#: is written here because the whole "latest row wins" rule is meaningless without it.
#:
#: The first version asked for the latest row for a source across ALL outcomes. But ``WITHDRAWN``
#: is a decision about a PROPOSAL — the proposer took their own draft back — and a proposal that
#: was never ratified never governed anything. Two PROPOSED versions may legitimately coexist for
#: one source, so withdrawing the second one appended a WITHDRAWN row that outranked the first
#: one's live RATIFIED row, and:
#:
#: - :func:`ratified_mapping_for` then reported NO current mapping and every load for that source
#:   refused — an ingestion outage caused by an ordinary "I changed my mind";
#: - :func:`ratify_mapping_version` then found NO incumbent to supersede, so the next legitimate
#:   ratification hit ENT-077's partial unique index and a governed act raised a raw
#:   ``IntegrityError`` instead of superseding cleanly.
#:
#: Both reproduced by execution before the fix. The class docstring below claimed "no state can
#: exist in which the question has two answers"; that claim was FALSE as written, and it is the
#: filter — not the ordering alone — that makes it true.
GOVERNING_OUTCOMES: frozenset[str] = frozenset({OUTCOME_RATIFIED, OUTCOME_SUPERSEDED})

#: The CHECK suffixes. Pass the SUFFIX to `op.create_check_constraint`, never the full name — the
#: convention prepends `ck_<table>_` itself and a doubled name truncates at 63 invisibly (0057).
#: Budget: `ck_ingestion_mapping_ratification_` is 34 of 63, leaving 29.
CHECK_OUTCOME = "outcome"
CHECK_RESOLVER = "resolver_present"


class IngestionMappingRatification(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """ENT-078 — one decision about one mapping version, recorded once and never edited."""

    __tablename__ = "ingestion_mapping_ratification"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # The per-tenant monotonic ordering key, app-assigned under the tenant advisory lock.
        UniqueConstraint("tenant_id", "seq", name="uq_ingestion_mapping_ratification_seq"),
        # NOTE there is deliberately NO "one row per mapping version" constraint, and the first
        # draft had one. It was wrong, and the DB said so within minutes: a version that is ratified
        # and later replaced has TWO facts in its life — it was ratified, and it was superseded —
        # and forcing them into one row would mean EDITING a decision, which is the single thing
        # this table exists to make impossible. A life is a sequence of facts (the ENT-075 /
        # breach_action shape); the constraint that matters is the one below.
        CheckConstraint(
            "outcome IN ('" + "', '".join(RESOLUTION_OUTCOMES) + "')",
            name=CHECK_OUTCOME,
        ),
        # "Resolved by nobody" is unrepresentable — the one CHECK that keeps the control
        # non-decorative (ENT-075's `ck_entitlement_request_resolution`, same reasoning).
        CheckConstraint(
            "resolved_by IS NOT NULL AND length(resolved_by) > 0",
            name=CHECK_RESOLVER,
        ),
        # DS3b-5 IS OWNED HERE — but NOT by a partial unique index, and the two failed attempts
        # are worth more than the answer.
        #
        # Attempt 1: unique on (tenant, source, source_type) WHERE outcome='RATIFIED', plus one row
        # per version. The database refused a legitimate replacement immediately: the incumbent's
        # decision was, and permanently remains, a ratification.
        # Attempt 2: append a SUPERSEDED row for the incumbent first. Also refused — appending a
        # row does not REMOVE the old RATIFIED row from a partial index. On an append-only log
        # nothing ever leaves a predicate, which makes "at most one row matching P" and "at most one
        # CURRENT thing" different statements. A partial unique index can only express the first.
        #
        # The invariant is therefore enforced STRUCTURALLY: the current ratified mapping for a
        # source is the one named by the latest row **whose outcome is in `GOVERNING_OUTCOMES`**,
        # and `uq_..._seq` makes "latest" unique by construction.
        #
        # THE FILTER IS LOAD-BEARING AND WAS MISSING. An earlier version of this comment said "the
        # LATEST resolution row for that source" with no filter, and asserted that "no state can
        # exist in which the question has two answers". That was FALSE: a WITHDRAWN row for an
        # unrelated competing proposal outranks a live RATIFIED row, and the question then answers
        # "none" while a ratified mapping is sitting right there. Reproduced by execution, found by
        # a different-engine review, fixed by filtering to the outcomes that speak to governance.
        # See `GOVERNING_OUTCOMES` above for the full account.
        #
        # This still satisfies what DS3b-5 ratified: the invariant lives on the append-only surface
        # rather than on ENT-077's mutable `status`.
        Index("ix_ingestion_mapping_ratification_tenant_outcome", "tenant_id", "outcome"),
    )

    #: Per-tenant monotonic sequence (1-based) — the deterministic ordering key. Wall clocks tie.
    seq: Mapped[int] = mapped_column(nullable=False)

    #: The version this row decides. Explicitly named: the convention-generated FK name is 74 chars
    #: and PostgreSQL truncates at 63 SILENTLY.
    mapping_version_id: Mapped[str] = mapped_column(
        GUID,
        ForeignKey(
            "ingestion_mapping_version.id", name="fk_ingestion_mapping_ratification_version"
        ),
        nullable=False,
        index=True,
    )

    #: Denormalized from the version SO THIS TABLE CAN ANSWER THE INVARIANT'S QUESTION (DS3b-5).
    #: Not a convenience: `ratified_mapping_for(source)` filters the resolution log on these two
    #: columns and takes the highest `seq`. Without them that read would have to join back to
    #: ENT-077 and filter on its mutable `status` — the column this table exists to stop trusting.
    data_source_id: Mapped[str] = mapped_column(GUID, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)

    outcome: Mapped[str] = mapped_column(String(20), nullable=False)

    #: WHO decided, canonicalized before comparison. The person-level SoD compares this to the
    #: version's `proposed_by_actor_id` — and compares them CANONICALIZED, because the S3a review
    #: reproduced a self-ratification that walked straight through a raw string comparison using
    #: nothing but the uppercase spelling of the same UUID.
    resolved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: DC-2 metadata: why. Never a credential, never a staged cell.
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        "IngestionMappingRatification is append-only (AUD-01); update/delete is forbidden — "
        "a decision that can be edited after the fact is not evidence of a decision"
    )


# BOTH halves, deliberately: the ORM guard here AND the `irp_prevent_mutation` trigger in the
# migration. ENT-075 shipped with only the trigger and its first mutation attempt was caught by
# PostgreSQL rather than by the code, which is a worse place to find out.
event.listen(IngestionMappingRatification, "before_update", _block_mutation)
event.listen(IngestionMappingRatification, "before_delete", _block_mutation)
