"""The interpreter: staged rows -> canonical position fields (W19-S3a, REQ-INT-001 clause 4).

**This module is the ONLY path from ``ingestion_staged_record`` to canonical ``position`` rows**,
and that is asserted by a census which DISCOVERS write paths mechanically rather than checking a
hand list (``test_ingest_mapping_census.py``). The clause is scoped exactly as the requirement
words it — *"from staged rows to canonical positions"*. ``POST /positions`` still calls
``create_position`` directly under ``position.edit``: that is an **intentionally unmapped
manual-entry path outside REQ-INT-001's guarantee**, recorded rather than quietly left open,
because a census that pretended to close it would be asserting something false.

The interpreter is deterministic by construction: given the same ratified mapping version, the same
staged rows, and the same ``lookup_as_of``, it produces the same canonical field dicts. Those are
exactly the three inputs clause (9) names, and the third is named because ``code-lookup`` reads
reference data held in neither of the other two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from irp_shared.ingest_mapping.errors import (
    CodeLookupRefusedError,
    ConstantTypeRefusedError,
    UnknownTargetFieldError,
)
from irp_shared.ingest_mapping.operations import (
    OP_CODE_LOOKUP,
    OP_CONSTANT,
    OPERATIONS,
    apply_operation,
    is_finite_decimal,
)
from irp_shared.reference.identifier import AmbiguousIdentifier, resolve_identifier

#: The canonical fields a positions mapping may target — the DECLARED set that clause (5)'s
#: ``UnknownTargetFieldError`` polices. Deliberately NOT "every column on ``position``": the FR
#: close-out columns, ``record_version`` and ``supersedes_id`` are protocol state the binder owns,
#: and ``position_source`` is EXCLUDED because the amended requirement bans free-text attribution.
TARGET_PORTFOLIO_CODE = "portfolio_code"
TARGET_INSTRUMENT = "instrument"
TARGET_QUANTITY = "quantity"
TARGET_COST_BASIS = "cost_basis"
TARGET_QUANTITY_UNIT = "quantity_unit"
TARGET_VALID_FROM = "valid_from"

TARGET_FIELDS: tuple[str, ...] = (
    TARGET_PORTFOLIO_CODE,
    TARGET_INSTRUMENT,
    TARGET_QUANTITY,
    TARGET_COST_BASIS,
    TARGET_QUANTITY_UNIT,
    TARGET_VALID_FROM,
)

#: The targets a mapping MUST produce for a loadable position. ``cost_basis`` and ``quantity_unit``
#: are genuinely optional (a custodian file often carries neither); the other four are not, and a
#: mapping missing one is refused at RATIFICATION rather than producing a null holding at load.
REQUIRED_TARGETS: frozenset[str] = frozenset(
    {TARGET_PORTFOLIO_CODE, TARGET_INSTRUMENT, TARGET_QUANTITY, TARGET_VALID_FROM}
)

#: Which targets must end up numeric / temporal. Used by BOTH the ratification-time constant check
#: and the load-time coercion, so an incoherent constant cannot become a ratified mapping.
_DECIMAL_TARGETS: frozenset[str] = frozenset({TARGET_QUANTITY, TARGET_COST_BASIS})
_DATETIME_TARGETS: frozenset[str] = frozenset({TARGET_VALID_FROM})


@dataclass
class ResolutionContext:
    """The one seam the operations reach outside themselves — code-lookup resolution.

    Holds the ``lookup_as_of`` so every lookup in a batch resolves against the SAME instant. A
    per-call "now" would make a load non-reproducible in a way no test would notice until an
    identifier was superseded, which is the failure clause (9) exists to prevent.
    """

    session: Session
    acting_tenant: str
    lookup_as_of: datetime
    #: scheme -> count, the evidence a load actually performed lookups (P18 positive control).
    resolved: dict[str, int] = field(default_factory=dict)

    def resolve_code(self, *, scheme: str, value: Any, row_number: int) -> str:
        """Resolve one identifier to an instrument id as of :attr:`lookup_as_of`, or REFUSE.

        Both refusal arms fire: unresolved, and ambiguous. Never a closest match, never a silent
        arbitrary pick — ``resolve_identifier`` already returns a typed ``AmbiguousIdentifier``
        rather than choosing, and this re-raises it as a mapping refusal so a caller failing closed
        on ``MappingError`` catches it.
        """
        cleaned = "" if value is None else str(value).strip()
        if not cleaned:
            raise CodeLookupRefusedError(scheme, value, row_number, "is empty")
        try:
            instrument = resolve_identifier(
                self.session,
                scheme=scheme,
                value=cleaned,
                acting_tenant=self.acting_tenant,
                as_of=self.lookup_as_of,
            )
        except AmbiguousIdentifier as exc:
            raise CodeLookupRefusedError(scheme, value, row_number, "resolves ambiguously") from exc
        if instrument is None:
            raise CodeLookupRefusedError(scheme, value, row_number, "resolves to nothing")
        self.resolved[scheme] = self.resolved.get(scheme, 0) + 1
        return str(instrument.id)


def assert_targets_coherent(operations: list[dict[str, Any]]) -> None:
    """Ratification-time check: every target is declared, required targets are present, and every
    ``constant`` is coercible to its target's type.

    Run at RATIFICATION as well as at load, deliberately. A mapping that would refuse every row at
    load time must not be allowed to become the ratified one — a refusal at load is evidence the
    platform worked, but a *ratified* mapping that can never load anything is a governance record
    saying a human approved something unusable.
    """
    targets: set[str] = set()
    for spec in operations:
        target = str(spec.get("target", ""))
        if target not in TARGET_FIELDS:
            raise UnknownTargetFieldError(target, TARGET_FIELDS)
        targets.add(target)
        if str(spec.get("op", "")) == OP_CONSTANT:
            _assert_constant_coercible(spec.get("value"), target)
    missing = REQUIRED_TARGETS - targets
    if missing:
        raise UnknownTargetFieldError(
            f"<missing required target(s): {', '.join(sorted(missing))}>", TARGET_FIELDS
        )


def _assert_constant_coercible(value: Any, target: str) -> None:
    if target in _DECIMAL_TARGETS:
        try:
            coerced = Decimal(str(value))
        except Exception as exc:  # noqa: BLE001 - any coercion failure is the same refusal
            raise ConstantTypeRefusedError(value, target) from exc
        if not coerced.is_finite():
            raise ConstantTypeRefusedError(value, target)
    elif target in _DATETIME_TARGETS and not isinstance(value, datetime):
        # A constant valid_from would pin every row of every load to one instant; the mapping must
        # parse it from the file. Refused rather than silently accepted as a string.
        raise ConstantTypeRefusedError(value, target)


def interpret_row(
    operations: list[dict[str, Any]],
    payload: dict[str, Any],
    row_number: int,
    ctx: ResolutionContext,
) -> dict[str, Any]:
    """Apply the ratified operation list to ONE staged row, producing canonical field values.

    Operations are applied in declared order and a later operation on the same target overwrites an
    earlier one — a mapping that renames then scales the same quantity column is the ordinary case,
    and the order is part of the ratified artifact rather than an implementation detail.
    """
    out: dict[str, Any] = {}
    for spec in operations:
        target = str(spec.get("target", ""))
        if target not in TARGET_FIELDS:
            raise UnknownTargetFieldError(target, TARGET_FIELDS)
        out[target] = apply_operation(spec, payload, row_number, ctx)
    return _coerce(out)


def _coerce(values: dict[str, Any]) -> dict[str, Any]:
    """Normalize interpreted values to the binder's expected Python types.

    Numeric targets land as ``Decimal`` and are finiteness-guarded before any write — the same
    pre-write guard every governed binder on this platform carries, because a NaN or infinity
    reaching a ``PreciseDecimal`` column is a 500 plus a RUNNING orphan (the BT-1 lesson).
    """
    out = dict(values)
    for target in _DECIMAL_TARGETS:
        if out.get(target) is not None:
            raw = out[target]
            coerced = raw if isinstance(raw, Decimal) else Decimal(str(raw))
            if not is_finite_decimal(coerced):
                raise ConstantTypeRefusedError(raw, target)
            out[target] = coerced
    for target in _DATETIME_TARGETS:
        if isinstance(out.get(target), datetime) and out[target].tzinfo is None:
            # parse-date produces a naive datetime; the platform stores UTC everywhere (QS-12).
            out[target] = out[target].replace(tzinfo=UTC)
    if out.get(TARGET_QUANTITY_UNIT) is not None:
        out[TARGET_QUANTITY_UNIT] = str(out[TARGET_QUANTITY_UNIT])[:20]
    return out


def declared_operation_kinds(operations: list[dict[str, Any]]) -> frozenset[str]:
    """The distinct operation kinds a mapping declares.

    REQ-INT-001 clause (8)'s floor of three is asserted against this, so a rename-only demo cannot
    pass.
    """
    kinds = (str(spec.get("op", "")) for spec in operations)
    return frozenset(kind for kind in kinds if kind in OPERATIONS)


def uses_code_lookup(operations: list[dict[str, Any]]) -> bool:
    """True when a mapping reads reference data — i.e. when clause (9)'s third input is live."""
    return any(str(spec.get("op", "")) == OP_CODE_LOOKUP for spec in operations)
