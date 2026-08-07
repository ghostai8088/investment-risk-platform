"""REPRO-1 vocabulary — a LEAF module with no binder imports (the ``scheduling.events`` doctrine).

``irp_worker`` and the census tests import from here; the family registry and the engine import the
compute stack, so they live in ``registry.py`` / ``service.py``. Putting the vocabulary next to the
registry would drag the whole risk+exposure+report stack into every importer's graph — the exact
circularity ``scheduling/events.py`` records at its own head.

**No audit code is minted here.** A reproduction run is an ordinary ``calculation_run`` and is
audited by the existing ``CALC.RUN_CREATE`` / ``CALC.RUN_STATUS_CHANGE`` — the twenty-plus
governed-family precedent (``RISK.*`` / ``PERF.*`` / ``PACING.*`` all reserved-not-minted). The
divergence ALARM reuses ``NOTIFY.DISPATCH``'s transport object only; it writes no
``breach_notification`` row and emits no new audit vocabulary.
"""

from __future__ import annotations

#: The ENT-073 entity name, for audit ``entity_type`` and error messages.
ENTITY_REPRODUCTION_CHECK = "reproduction_check"

# ------------------------------------------------------------------------------- verdict vocab ---
#: The recompute reproduced every compared value. The platform's claim held for this run.
VERDICT_MATCH = "MATCH"
#: The recompute RAN and produced different content. This is the alarm — the code changed what it
#: computes over inputs that are immutable by construction.
VERDICT_DIVERGED = "DIVERGED"
#: The recompute could not be performed at all (a missing binder precondition, an unresolvable
#: model, a refusal from the family's own gates). Deliberately NOT folded into DIVERGED: "we could
#: not check" and "we checked and it broke" call for different responses, and collapsing them is
#: the identity-failure-versus-ordinary-500 mistake RPT-2 had to unpick.
VERDICT_UNREPRODUCIBLE = "UNREPRODUCIBLE"

VERDICTS: frozenset[str] = frozenset({VERDICT_MATCH, VERDICT_DIVERGED, VERDICT_UNREPRODUCIBLE})

#: The verdicts that must raise an operator alarm. MATCH is silence by design; UNREPRODUCIBLE is
#: included because a check that has silently stopped being able to run is indistinguishable, from
#: the outside, from a check that keeps passing.
ALARMING_VERDICTS: frozenset[str] = frozenset({VERDICT_DIVERGED, VERDICT_UNREPRODUCIBLE})

# ------------------------------------------------------------------------------ the alarm ---------
#: Who is owed a divergence alarm (ratified OQ-REPRO-1-4).
#:
#: ``breach.review`` is reused deliberately over a fresh ``repro.review``. A new code would be
#: semantically tidier and held by NOBODY: there is no tenant-onboarding clone of ``ROLE_TEMPLATES``
#: (``entitlement/bootstrap.py`` promises one; it does not exist), so a freshly minted code has no
#: holders in any real tenant and the alarm would record "checked, nobody to notify" forever while
#: looking healthy — the LQ-1 written-believed-inert class. The permission that actually addressed
#: the alarm is recorded on every attempt, so reuse is visible rather than assumed.
ALARM_RECIPIENT_PERMISSION = "breach.review"

# NOTE: the alert's wire name deliberately does NOT live here. It is
# ``notification.sink.ALERT_TYPE_REPRODUCTION``, next to the payload that emits it, because the
# transport owns its own vocabulary. A duplicate constant here would be a second source someone
# would eventually edit while the wire kept using the first — a declaration with no consumer,
# which this codebase has twice deleted rather than kept (`produces_run_on_failure`,
# `target_run_type`). Found at the adversarial review, before it could drift.

__all__ = [
    "ALARMING_VERDICTS",
    "ALARM_RECIPIENT_PERMISSION",
    "ENTITY_REPRODUCTION_CHECK",
    "VERDICTS",
    "VERDICT_DIVERGED",
    "VERDICT_MATCH",
    "VERDICT_UNREPRODUCIBLE",
]
