"""Sync the entitlement catalog into EXISTING databases (RPT-2 review finding, BLOCKING class).

**The defect this repairs is platform-wide and predates RPT-2.** Since P0.5 the mint procedure has
been "append to ``entitlement/bootstrap.py``; ``0002`` live-imports it; a fresh ``alembic upgrade
head`` seeds it" — recorded as the precedent in ``0002``'s own docstring and in
``entitlement_sod_model.md``. That is true only for a database created AFTER the mint. ``0002`` is
long since applied on any live deployment, so ``upgrade head`` is a no-op there and **every code
minted after a database was created has never reached it**.

Proven by execution on the local PG at head ``0063`` (RPT-2 review):

    report.* rows before        -> 0   (simulating the pre-mint state of a live database)
    alembic upgrade head        -> UPGRADE_EXIT=0
    report.* rows after         -> 0   ← the mint is undeliverable

The consequence is not cosmetic. ``require_permission`` is deny-by-default: a code absent from the
database denies EVERY holder, so on a live deployment the RPT-2 report surface would 403 for all
five ratified roles — while every unit test, the fresh-database smoke, and CI all pass, because
each of them builds its database from empty. The same silence has covered `liquidity.*`,
`concentration.*`, `schedule.*`, `limit.*`, `breach.*` and the rest since their mints.

**This migration is the class fix (P10), not the instance fix.** It syncs the WHOLE catalog and the
WHOLE role-template grant set, so every code minted since P0.5 lands wherever it is missing.

**Idempotent by construction, and additive only.** Every id is a deterministic ``uuid5``
(``permission_id`` / ``role_id`` / ``role_permission_id``), so "insert what is absent" needs no
bookkeeping and re-running changes nothing on an unmodified database. It never UPDATES and never
DELETES: a description edited in a live database stays edited.

**AMENDED at the Wave-16 close (P17), and the amendment is the point of the rule.** As merged, this
migration DID re-insert a template grant an administrator had deliberately revoked — reproduced by
execution at the pre-merge audit (revoke → downgrade → upgrade → the grant is back,
``UPGRADE_EXIT=0``) and disclosed in this docstring as an accepted consequence. The close review
refused to ratify the sync on those terms: mandating it without addressing revocation durability
institutionalises the resurrection, turning a governance action into a transient one. So:

* the sync logic moved to ``irp_shared.entitlement.sync.sync_catalog`` — ONE implementation, so the
  next sync migration cannot re-derive the additive half and lose the revocation half; and
* it consults ``role_permission_revocation`` (migration ``0066``) and SKIPS + LOGS revoked grants.

**Editing an applied migration is not something to do lightly, so the justification is explicit.**
On any database whose head is below ``0066`` the ledger table does not exist, the consulted
revocation set is empty, and the inserts are byte-identical to the merged version — verified by
differential execution, not by argument (``test_entitlement_sync.py`` runs both code paths against
the same fixture and compares the resulting rows). The behaviour changes only where a revocation
has been recorded, which is exactly the case the rule is about. The alternative — leaving a known
resurrecting sync in the tree beside a corrected one — is the two-mechanisms-for-one-property shape
FK-1 had just finished retiring.

**What the ledger still cannot save.** Downgrading below ``0066`` DROPS the revocation table, and a
subsequent re-upgrade therefore has nothing to consult. No design inside a migration can survive
the destruction of its own evidence; it is stated here rather than papered over.

**The standing consequence, recorded so the next mint does not re-learn it (P17):** appending to
``bootstrap.py`` is NOT sufficient for a live deployment. A mint needs its own sync migration
declaring the codes it delivers in a literal ``DELIVERS`` tuple — which
``test_entitlement_mint_delivery.py`` checks against the catalog, so the omission fails a test
rather than reaching production as a 403.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from alembic import op

from irp_shared.entitlement.bootstrap import ALL_CODES
from irp_shared.entitlement.sync import sync_catalog

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "0064_entitlement_sync"
down_revision: str | None = "0063_report_generation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYNC_TS = datetime(2026, 8, 7, 0, 0, 0, tzinfo=UTC)

#: The permission codes this migration DELIVERS to a running database (P17's mechanical gate). It
#: syncs the whole catalog, so its delivered set IS the catalog as of this revision — spelled as a
#: literal rather than an import, because the gate's whole job is to notice when the constant grows
#: past what any migration has shipped. An import here would make the check vacuous forever.
DELIVERS: tuple[str, ...] = (
    "ops.audit.verify",
    "data.upload",
    "lineage.view",
    "lineage.source.manage",
    "model.inventory.view",
    "model.inventory.register",
    "model.validate",
    "dq.rule.manage",
    "dq.result.view",
    "reference.instrument.view",
    "reference.instrument.edit",
    "reference.issuer.view",
    "reference.issuer.edit",
    "reference.counterparty.view",
    "reference.counterparty.edit",
    "reference.identifier.resolve",
    "reference.corporate_action.edit",
    "reference.calendar.edit",
    "reference.currency.view",
    "reference.currency.edit",
    "reference.rating_scale.view",
    "reference.rating_scale.edit",
    "reference.calendar.view",
    "reference.legal_entity.view",
    "reference.legal_entity.edit",
    "reference.identifier.view",
    "reference.identifier.edit",
    "reference.corporate_action.view",
    "reference.classification.view",
    "reference.classification_assignment.view",
    "reference.classification.edit",
    "portfolio.view",
    "portfolio.edit",
    "position.view",
    "position.edit",
    "exposure.aggregate.run",
    "exposure.view",
    "risk.run",
    "risk.view",
    "perf.run",
    "perf.view",
    "transaction.view",
    "transaction.record",
    "valuation.view",
    "valuation.edit",
    "snapshot.view",
    "snapshot.create",
    "marketdata.view",
    "marketdata.ingest",
    "commitment.view",
    "commitment.edit",
    "commitment.record",
    "pacing.run",
    "pacing.view",
    "concentration.run",
    "concentration.view",
    "concentration.issuer.view",
    "liquidity.run",
    "liquidity.view",
    "schedule.manage",
    "schedule.view",
    "limit.manage",
    "limit.approve",
    "limit.view",
    "breach.view",
    "breach.respond",
    "breach.review",
    "report.generate",
    "report.view",
)


def upgrade() -> None:
    # A structural cross-check at the only moment both facts are in hand: what this revision claims
    # to deliver must be a subset of the catalog it syncs. It is not a substitute for
    # ``test_entitlement_mint_delivery.py`` (which sees the CURRENT catalog); it stops a later edit
    # to DELIVERS from silently disagreeing with this revision's own sync.
    unknown = sorted(set(DELIVERS) - set(ALL_CODES))
    if unknown:
        raise RuntimeError(f"0064 DELIVERS names codes absent from the catalog: {unknown}")

    report = sync_catalog(op.get_bind(), now=SYNC_TS)
    # A no-op on an unmodified database is the expected outcome, not a failure — the counts are
    # logged so an operator can see what a live deployment was actually missing.
    logger.info(
        "0064 entitlement sync: +%d permissions, +%d roles, +%d grants, "
        "%d revoked grants skipped, ledger_present=%s",
        report.permissions_inserted,
        report.roles_inserted,
        report.grants_inserted,
        len(report.grants_skipped_revoked),
        report.ledger_present,
    )


def downgrade() -> None:
    """Deliberately a NO-OP.

    This migration cannot know which rows it inserted versus which ``0002`` (or an operator)
    created — the ids are deterministic, so they are indistinguishable by construction. Deleting
    the catalog on downgrade would revoke permissions this migration never granted and take the
    entitlement surface of a live deployment with it. A no-op downgrade is the honest behaviour;
    the schema is unchanged either way.
    """
