"""The CLOSED transformation vocabulary (OQ-ING-2=A, ratified 2026-08-12) — W19-S3a.

Seven operations, a fixed list, each independently tested and each with its own refusal proven to
FIRE. **Not an expression language.** The ratified reasons, in the order they were weighted:

1. *"What did this mapping do?"* keeps a simple answer a non-engineer can audit.
2. Reproducing a historical load never means reproducing an interpreter's exact behaviour.
3. The platform does not acquire a sandbox to own.

A file that cannot be expressed forces a NEW operation to be added deliberately and reviewed — that
is the feature, and it is why :class:`~irp_shared.ingest_mapping.errors.UnsupportedOperationError`
must name the unsupported operation rather than fail vaguely.

**The LQ-1 T4 trap, closed by construction.** A vocabulary tuple and a dispatch table are TWO
mandatory sites: a name in the tuple with no dispatch entry compiles, imports, passes every census,
and then refuses every capture at runtime (``DIMENSION_KIND_LIQUIDITY_TIER`` did exactly that).
:data:`OPERATIONS` and :data:`_DISPATCH` are therefore censused against each other by **exact set
equality in BOTH directions**, and each operation additionally has a test proving it EXECUTES —
because an operation reachable only through a dispatch table is invisible to a vocabulary census.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from irp_shared.ingest_mapping.errors import (
    CastRefusedError,
    ConcatenateRefusedError,
    DateParseRefusedError,
    MissingSourceColumnError,
    ScaleRefusedError,
    UnsupportedOperationError,
)

OP_RENAME = "rename"
OP_CAST = "cast"
OP_SCALE = "scale"
OP_PARSE_DATE = "parse-date"
OP_CODE_LOOKUP = "code-lookup"
OP_CONSTANT = "constant"
OP_CONCATENATE = "concatenate"

#: The closed set. Adding a member here without a :data:`_DISPATCH` entry (or vice versa) fails the
#: two-way census by construction — that is the point.
OPERATIONS: tuple[str, ...] = (
    OP_RENAME,
    OP_CAST,
    OP_SCALE,
    OP_PARSE_DATE,
    OP_CODE_LOOKUP,
    OP_CONSTANT,
    OP_CONCATENATE,
)

#: Cast target types. Plain strings; a new one is a value plus a dispatch arm, not a migration.
CAST_DECIMAL = "decimal"
CAST_INTEGER = "integer"
CAST_STRING = "string"
CAST_TYPES: tuple[str, ...] = (CAST_DECIMAL, CAST_INTEGER, CAST_STRING)


def _numeric_text(raw: Any) -> str:
    """The text of a cell, prepared for numeric coercion.

    Two repairs, both narrow and both necessary against real custodian files:

    1. **Thousands separators are stripped.** Every real statement has them.
    2. **A leading anti-corruption quote is removed.** This is the important one, and it is not
       cosmetic. ``anticorruption.neutralize_cell`` prefixes ``'`` to any cell starting with
       ``= + - @``, which is a CSV-injection defence (THR-06) — and a SHORT POSITION starts with
       ``-``. So every short in every client file reaches the interpreter as ``'-3.2``, and without
       this the platform would refuse to load any book containing one, while ``position.quantity``
       is documented as SIGNED (long > 0, short < 0). Verified by execution, not assumed.

    The repair is deliberately confined to the NUMERIC path. ``rename`` and ``concatenate`` keep the
    neutralized text exactly as staged, because the defence exists for values that flow onward into
    a spreadsheet, and a quantity does not: it is coerced to Decimal here and stored as a number.
    """
    if raw is None:
        return ""
    text_value = str(raw).strip().replace(",", "")
    if text_value.startswith("'") and len(text_value) > 1 and text_value[1] in "+-.0123456789":
        text_value = text_value[1:]
    return text_value


def _cell(payload: dict[str, Any], column: str, row_number: int) -> Any:
    """Read one staged cell, refusing a missing column rather than substituting a null.

    A null holding is worse than a refused batch: it reads as a real position of zero.
    """
    if column not in payload:
        raise MissingSourceColumnError(column, row_number)
    return payload[column]


# --- the seven arms ---------------------------------------------------------------------------


def _op_rename(spec: dict[str, Any], payload: dict[str, Any], row_number: int, ctx: Any) -> Any:
    """Take a source column's value unchanged."""
    return _cell(payload, str(spec["source"]), row_number)


def _op_cast(spec: dict[str, Any], payload: dict[str, Any], row_number: int, ctx: Any) -> Any:
    """Coerce a source cell to a declared type, refusing rather than defaulting.

    Thousands separators and surrounding whitespace are stripped for the numeric types because
    every real custodian file has them; nothing else is repaired. ``"n/a"``, ``""``, and a
    fractional value cast to ``integer`` all refuse.
    """
    to_type = str(spec.get("to", CAST_DECIMAL))
    raw = _cell(payload, str(spec["source"]), row_number)
    if to_type not in CAST_TYPES:
        raise CastRefusedError(raw, to_type, row_number)
    if to_type == CAST_STRING:
        return "" if raw is None else str(raw).strip()
    cleaned = _numeric_text(raw)
    if not cleaned:
        raise CastRefusedError(raw, to_type, row_number)
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError, ArithmeticError) as exc:
        raise CastRefusedError(raw, to_type, row_number) from exc
    if not value.is_finite():
        raise CastRefusedError(raw, to_type, row_number)
    if to_type == CAST_INTEGER:
        if value != value.to_integral_value():
            raise CastRefusedError(raw, to_type, row_number)
        return int(value)
    return value


def _op_scale(spec: dict[str, Any], payload: dict[str, Any], row_number: int, ctx: Any) -> Any:
    """Multiply a numeric cell by a DECLARED factor (quantities in thousands, prices in cents).

    Both arms refuse. The factor arm is the one that matters: a zero factor turns a whole book into
    zero holdings, and every downstream reproduction of that load would agree with itself.
    """
    try:
        factor = Decimal(str(spec["factor"]))
    except (InvalidOperation, ValueError, ArithmeticError, KeyError) as exc:
        raise ScaleRefusedError(f"declared factor {spec.get('factor')!r} is not a number") from exc
    if not factor.is_finite() or factor <= 0:
        raise ScaleRefusedError(f"declared factor {factor} must be finite and positive")
    raw = _cell(payload, str(spec["source"]), row_number)
    cleaned = _numeric_text(raw)
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError, ArithmeticError) as exc:
        raise ScaleRefusedError(f"{raw!r} is not numeric", row_number) from exc
    if not value.is_finite():
        raise ScaleRefusedError(f"{raw!r} is not finite", row_number)
    return value * factor


def _op_parse_date(spec: dict[str, Any], payload: dict[str, Any], row_number: int, ctx: Any) -> Any:
    """Parse a cell under a DECLARED strptime format.

    The format is declared by the mapping and never sniffed — sniffing is how a ``03/04/2026`` UK
    file silently loads as an April date. Both a shape miss and a real calendar miss (``31/02``)
    refuse.
    """
    fmt = str(spec["format"])
    raw = _cell(payload, str(spec["source"]), row_number)
    cleaned = "" if raw is None else str(raw).strip()
    try:
        return datetime.strptime(cleaned, fmt)  # noqa: DTZ007 - tz applied by the interpreter
    except (ValueError, TypeError) as exc:
        raise DateParseRefusedError(raw, fmt, row_number) from exc


def _op_code_lookup(
    spec: dict[str, Any], payload: dict[str, Any], row_number: int, ctx: Any
) -> Any:
    """Resolve an identifier to a canonical entity AS OF the batch's ``lookup_as_of``.

    Scoped to ``identifier_xref`` (instruments) because it is the ONLY as-of-capable resolver in
    the platform — ``resolve_node`` / ``resolve_scheme`` / ``resolve_currency`` /
    ``resolve_calendar`` all resolve current state only and take no ``as_of``. REQ-INT-001 clause
    (9) names the code-lookup reference data as of the load precisely because this operation reads
    data held in neither the mapping nor the staged file, so the resolution is pinned to a recorded
    instant, never to "now".

    Delegated to ``ctx.resolve_code`` so this module stays free of a reference-package import and
    the interpreter owns the one seam a test can drive.
    """
    scheme = str(spec["scheme"])
    raw = _cell(payload, str(spec["source"]), row_number)
    return ctx.resolve_code(scheme=scheme, value=raw, row_number=row_number)


def _op_constant(spec: dict[str, Any], payload: dict[str, Any], row_number: int, ctx: Any) -> Any:
    """A declared literal, independent of the file.

    How a single-account statement names its portfolio, and how a file with no unit column declares
    ``SHARES``. Type-checked against the target field at RATIFICATION as well as at load, so a
    mapping carrying an incoherent constant can never become the ratified one.
    """
    return spec["value"]


def _op_concatenate(
    spec: dict[str, Any], payload: dict[str, Any], row_number: int, ctx: Any
) -> Any:
    """Join several source columns with a declared separator.

    Refuses on ANY missing input rather than joining what it has: half an identifier looks like a
    valid identifier, which is the dangerous failure here.
    """
    sources = [str(s) for s in spec["sources"]]
    missing = tuple(s for s in sources if s not in payload)
    if missing:
        raise ConcatenateRefusedError(missing, row_number)
    sep = str(spec.get("separator", ""))
    return sep.join("" if payload[s] is None else str(payload[s]).strip() for s in sources)


#: The dispatch table. Censused against :data:`OPERATIONS` by exact set equality BOTH ways.
_DISPATCH: dict[str, Callable[[dict[str, Any], dict[str, Any], int, Any], Any]] = {
    OP_RENAME: _op_rename,
    OP_CAST: _op_cast,
    OP_SCALE: _op_scale,
    OP_PARSE_DATE: _op_parse_date,
    OP_CODE_LOOKUP: _op_code_lookup,
    OP_CONSTANT: _op_constant,
    OP_CONCATENATE: _op_concatenate,
}


def dispatch_names() -> frozenset[str]:
    """The dispatch table's key set — the census reads this rather than the private dict."""
    return frozenset(_DISPATCH)


def apply_operation(
    spec: dict[str, Any], payload: dict[str, Any], row_number: int, ctx: Any
) -> Any:
    """Apply ONE declared operation to ONE staged row, or refuse BY NAME.

    The single entry point: nothing else may reach ``_DISPATCH``, so an operation added to the
    vocabulary without a dispatch arm refuses here rather than silently producing ``None``.
    """
    op = str(spec.get("op", ""))
    fn = _DISPATCH.get(op)
    if fn is None:
        raise UnsupportedOperationError(op, OPERATIONS)
    return fn(spec, payload, row_number, ctx)


def is_finite_decimal(value: object) -> bool:
    """True for a Decimal/float that is finite — the pre-write guard every numeric target uses."""
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, int) and not isinstance(value, bool)
