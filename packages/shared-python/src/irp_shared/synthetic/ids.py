"""Deterministic id + clock helpers for the synthetic dataset (P1C-6).

Every synthetic id is a ``uuid5`` from a fixed namespace (mirrors the ``entitlement/bootstrap.py``
``_NS`` precedent) and every synthetic timestamp comes from a fixed seed clock — so the dataset is
byte-reproducible across machines and runs. This module deliberately uses **no** wall-clock / random
source: NO ``datetime.now`` / ``datetime.utcnow`` / ``utcnow`` / ``uuid4`` / ``new_uuid`` /
``uuid1``
/ ``random`` / ``secrets`` (an AST source-fence test enforces this — see ``test_synthetic.py``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

#: Reserved synthetic uuid5 namespace — distinct from the entitlement bootstrap ``_NS`` (…00a1).
#: ``…00c6`` nods to P1C-6; the exact value only needs to be fixed + reserved.
_SYN_NS = uuid.UUID("00000000-0000-0000-0000-0000000000c6")


def synthetic_id(key: str) -> str:
    """Deterministic ``uuid5`` id for a synthetic entity, from ``_SYN_NS`` + a business ``key``.

    The same ``key`` always yields the same id (reproducible); distinct keys collide only with
    cryptographically negligible probability (``uuid5`` = SHA-1 over namespace+name)."""
    return str(uuid.uuid5(_SYN_NS, key))


#: The reserved SYNTHETIC tenant — ALL synthetic rows live here, RLS-isolated from every real tenant
#: (and distinct from ``SYSTEM_TENANT_ID``). The seed only ever writes to this tenant.
SYNTHETIC_TENANT_ID = synthetic_id("tenant:synthetic")

#: The synthetic seed actor (an audit/lineage label only — the service-layer binders do not enforce
#: entitlement; the API layer does, and the synthetic tenant has no API users).
SYNTHETIC_ACTOR_ID = synthetic_id("actor:synthetic-seed")

#: Fixed base instant for the seed clock (no host-clock dependence).
SEED_EPOCH = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


class SeedClock:
    """A deterministic, monotonically-advancing clock for the seed run.

    Each ``tick()`` returns ``SEED_EPOCH + N seconds`` (N incrementing), so every governed write
    gets
    a distinct, fixed, reproducible ``system_from`` / audit ``event_time``. No wall clock."""

    def __init__(self, *, start: datetime = SEED_EPOCH) -> None:
        self._start = start
        self._step = 0

    def tick(self) -> datetime:
        """Return the next fixed instant and advance the deterministic step counter."""
        value = self._start + timedelta(seconds=self._step)
        self._step += 1
        return value


def business_date(offset_days: int) -> datetime:
    """A fixed business-time instant ``SEED_EPOCH + offset_days`` (for ``valid_from`` / effective
    dates / ``trade_date`` bases) — deterministic, no wall clock."""
    return SEED_EPOCH + timedelta(days=offset_days)
