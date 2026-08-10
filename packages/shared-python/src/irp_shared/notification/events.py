"""NOTIF-1 vocabulary + the NOTIFY.* audit code (Wave-12 slice 2).

**The R-07 mint (OQ-5=A):** a new governed audit code family ``NOTIFY.*`` — v1 activates the single
``NOTIFY.DISPATCH`` (one ledger entry per notification attempt, so "the CRO was alerted" is
hash-chain-anchored tamper-evident proof, not merely an append-only row). Emitted by CALLING the
FROZEN ``audit.service.record_event`` with ``event_type=NOTIFY.DISPATCH`` (the caller-side pattern,
exactly as ``BREACH.*`` does) — the frozen writer is unchanged. This is the ONLY code mint in the
slice; NO new permission (the read reuses ``breach.view``).

The notification consumer reads ONLY ``BREACH.*`` events (``NOTIFY_ALARM_EVENT_TYPES``), never its
own ``NOTIFY.*`` emits, so it can never self-trigger.
"""

from __future__ import annotations

from irp_shared.limit.events import BREACH_DETECT_EVENT, BREACH_ESCALATE_EVENT

#: The R-07-minted NOTIFY.* audit code (OQ-5=A). One emit per attempt → hash-chained proof-of-alert.
NOTIFY_DISPATCH_EVENT = "NOTIFY.DISPATCH"

#: The audit ``source_module`` tag + ``entity_type`` for notification emits.
SOURCE_MODULE_NOTIFICATION = "notification"
ENTITY_BREACH_NOTIFICATION = "breach_notification"

#: The two ALARM events a breach notification fires on (OQ-2=A): a breach appeared, or a remediation
#: deadline blew. Lifecycle transitions (assign/respond/review/close) are workflow, NOT alarms. The
#: source ``severity`` (warning/info) rides in the payload so a future channel can filter HARD/SOFT
#: (a SOFT DETECT carries severity="info" but still pages under this rule — the ratified OQ-2=A).
NOTIFY_ALARM_EVENT_TYPES = frozenset({BREACH_DETECT_EVENT, BREACH_ESCALATE_EVENT})

#: Delivery outcome vocab (the ``breach_notification.outcome`` column).
NOTIFY_OUTCOME_SENT = "SENT"  #: the sink accepted the notification
NOTIFY_OUTCOME_FAILED = (
    "FAILED"  #: the sink rejected it (durable evidence; terminal in v1, no retry)
)
NOTIFY_OUTCOME_SUPPRESSED = "SUPPRESSED"  #: no eligible recipient (the cursor-advance sentinel row)
#: ALERT-1 (ratified 2026-08-09, OQ-ALR-4): delivery DELIBERATELY not attempted, because this
#: recipient's own durable state for THIS subject is already-delivered. The fourth outcome exists
#: because the courtesy skip needs a row and every prior value would have LIED about it: ``SENT``
#: claims the sink accepted a call that never happened (the Wave-12 honesty doctrine — SENT means
#: "the LOG sink accepted", never a claimed delivery), and ``SUPPRESSED`` means "nobody to tell",
#: which is the opposite of "already told". A row that misdescribes its own act is the false-record
#: class this family has refused twice before.
NOTIFY_OUTCOME_SKIPPED = "SKIPPED"
NOTIFY_OUTCOMES = frozenset(
    {
        NOTIFY_OUTCOME_SENT,
        NOTIFY_OUTCOME_FAILED,
        NOTIFY_OUTCOME_SUPPRESSED,
        NOTIFY_OUTCOME_SKIPPED,
    }
)

#: Outcomes that CONCLUDE an attempt for their recipient (the audit column maps these to
#: ``success``). Declared here, beside the vocabulary, so the reproduction emitter's total mapping
#: reads ONE list rather than re-enumerating it — the mapping stays total and fails CLOSED on any
#: fifth value, which is the property that made this constant necessary at all.
NOTIFY_CONCLUDING_OUTCOMES = frozenset(
    {NOTIFY_OUTCOME_SENT, NOTIFY_OUTCOME_SUPPRESSED, NOTIFY_OUTCOME_SKIPPED}
)

#: Delivery channel vocab. v1 ships only LOG (the record-first posture, OQ-1=A); EMAIL/WEBHOOK are
#: later config-driven adapters behind the same ``NotificationSink`` Protocol (no schema change).
NOTIFY_CHANNEL_LOG = "LOG"
NOTIFY_CHANNELS = frozenset({NOTIFY_CHANNEL_LOG, "EMAIL", "WEBHOOK"})

#: The permission whose in-tenant holders are the recipients (OQ-3=A — the 2L oversight function).
NOTIFY_RECIPIENT_PERMISSION = "breach.review"

#: The fixed NON-NULL sentinel ``recipient_id`` for a no-recipient (SUPPRESSED) row (OQ-4=B). A NULL
#: would defeat the ``(tenant_id, source_sequence_no, recipient_id)`` unique key under Postgres
#: NULL-distinct semantics → unbounded duplicate sentinels on crash-retry (the verifier fold). The
#: all-zeros UUID is never a real ``app_user.id``.
NO_RECIPIENT_SENTINEL = "00000000-0000-0000-0000-000000000000"
