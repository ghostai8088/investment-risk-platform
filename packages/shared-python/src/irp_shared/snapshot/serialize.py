"""Deterministic, engine-independent canonical serialization for snapshot components (P2-1, §7).

``captured_content`` = ``canonicalize({field: normalized_value, ...})`` over the per-kind immutable
field set; ``content_hash = sha256_hex(captured_content)``. Reuses the audited ``audit.hashing``
primitives (``canonicalize`` sorts keys, compact separators, ``ensure_ascii=False``;
``sha256_hex``)
so the hash is **identical across the AD-011 SQLite/PG split** — in app code, NEVER in the DB.

Normalization (so nothing hits ``canonicalize``'s ``default=str`` fallback non-deterministically):
``Decimal`` -> fixed-scale string at the column scale (QS-01/03); ``datetime`` -> ISO-8601 UTC
(naive assumed UTC, QS-12); ``date`` -> ``YYYY-MM-DD``; GUID/str -> lowercase; ``None`` -> JSON
null
(explicit, distinct from ``""``). The **mutable close-out markers ``valid_to``/``system_to``** (and
``created_at``/``updated_at``) are EXCLUDED — FR rows are close-out-UPDATEd while their content is
immutable. ``restatement_reason``/``supersedes_id`` ARE included (write-once version provenance).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from irp_shared.audit.hashing import canonicalize, sha256_hex

#: Decimal scales per column (canonical_data_model — Position.quantity Numeric(28,8); valuation /
#: position mark/cost_basis Numeric(20,6); fx_rate.rate Numeric(28,12); curve_point.point_value
#: Numeric(20,12)).
_SCALE_QUANTITY = 8
_SCALE_MONEY = 6
_SCALE_FX_RATE = 12
_SCALE_CURVE_POINT = 12
_SCALE_COVARIANCE = 20  # covariance_result.covariance_value Numeric(38,20) (P3-5)


def _norm_datetime(value: datetime) -> str:
    """ISO-8601 UTC (a naive value — e.g. from SQLite — is assumed UTC)."""
    dt = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return dt.isoformat()


def _norm_decimal(value: Decimal, scale: int) -> str:
    """Fixed-scale decimal string (trailing zeros normalized, so 1 and 1.00 hash identically).

    QUANTIZE to the column scale with ROUND_HALF_UP **before** formatting — engine-independence
    (AD-011): Python's ``f"{:.Nf}"`` uses ROUND_HALF_EVEN, but PG ``numeric`` rounds HALF_UP when
    it
    stores a sub-scale value. Without an explicit quantize a value carrying more precision than the
    column scale (e.g. ``0.0000005`` at scale 6) would hash differently build-time (in-memory,
    un-roundtripped) vs verify-time (PG-roundtripped), and differently on SQLite vs PG — a spurious
    drift. Quantizing HALF_UP here makes BOTH ends, on BOTH engines, hash the same scaled value.

    Quantized inside a WIDE local context: the DEFAULT context is prec 28, which raises
    ``InvalidOperation`` for a value a wide column legitimately holds (the P3-5 20dp covariance
    scale permits 18 integer digits = a 38-digit coefficient — the same bug class the P3-4
    ``PreciseDecimal`` fix closed at the bind side; 2026-07 review)."""
    with localcontext() as ctx:
        ctx.prec = 60  # >= every column's precision + scale, with headroom
        quantized = value.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
    return f"{quantized:f}"


def _norm_guid(value: str) -> str:
    return str(value).lower()


def position_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of a ``position`` (FR) version (§7 POSITION field list)."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "portfolio_id": _norm_guid(row.portfolio_id),
        "instrument_id": _norm_guid(row.instrument_id),
        "quantity": _norm_decimal(row.quantity, _SCALE_QUANTITY),
        "cost_basis": (
            None if row.cost_basis is None else _norm_decimal(row.cost_basis, _SCALE_MONEY)
        ),
        "quantity_unit": row.quantity_unit,
        "position_source": row.position_source,
        "restatement_reason": row.restatement_reason,
        "supersedes_id": (None if row.supersedes_id is None else _norm_guid(row.supersedes_id)),
        "valid_from": _norm_datetime(row.valid_from),
        "system_from": _norm_datetime(row.system_from),
        "record_version": row.record_version,
    }


def valuation_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of a ``valuation`` (FR) version (§7 VALUATION field list)."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "portfolio_id": _norm_guid(row.portfolio_id),
        "instrument_id": _norm_guid(row.instrument_id),
        "valuation_date": row.valuation_date.isoformat(),
        "mark_value": _norm_decimal(row.mark_value, _SCALE_MONEY),
        "currency_code": row.currency_code,
        "mark_source": row.mark_source,
        "price_basis": row.price_basis,
        "restatement_reason": row.restatement_reason,
        "supersedes_id": (None if row.supersedes_id is None else _norm_guid(row.supersedes_id)),
        "valid_from": _norm_datetime(row.valid_from),
        "system_from": _norm_datetime(row.system_from),
        "record_version": row.record_version,
    }


def portfolio_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of a ``portfolio`` (EV) version (§7 PORTFOLIO field list — no
    ``system_from``; includes ``name``/``description`` so the hash moves on any EV amend)."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "code": row.code,
        "name": row.name,
        "node_type": row.node_type,
        "parent_portfolio_id": (
            None if row.parent_portfolio_id is None else _norm_guid(row.parent_portfolio_id)
        ),
        "base_currency_code": row.base_currency_code,
        "status": row.status,
        "description": row.description,
        "valid_from": _norm_datetime(row.valid_from),
        "record_version": row.record_version,
    }


def fx_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of an ``fx_rate`` (FR) version (P2-3 FX component). The rate
    is
    captured at the FX scale 12 (Numeric(28,12)); ``rate_date``/``rate_type``/``base``/``quote``
    are
    the immutable logical key. Close-out markers (``valid_to``/``system_to``) are EXCLUDED (the FR
    content is immutable; the row is close-out-UPDATEd) — the ``valuation`` precedent."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "base_currency": row.base_currency,
        "quote_currency": row.quote_currency,
        "rate_date": row.rate_date.isoformat(),
        "rate": _norm_decimal(row.rate, _SCALE_FX_RATE),
        "rate_type": row.rate_type,
        "rate_source": row.rate_source,
        "restatement_reason": row.restatement_reason,
        "supersedes_id": (None if row.supersedes_id is None else _norm_guid(row.supersedes_id)),
        "valid_from": _norm_datetime(row.valid_from),
        "system_from": _norm_datetime(row.system_from),
        "record_version": row.record_version,
    }


def curve_content(row: Any, nodes: list[Any]) -> dict[str, Any]:
    """The immutable captured content of a ``curve`` (FR) version + its node set (P3-1 CURVE
    component). One CURVE component = the header immutable fields + the ordered ``curve_point``
    node
    list (``point_value`` at the curve-point scale 12) — the header+nodes pinned as a unit (the
    nodes
    are IA append-only + version-pinned to the header). ``interpolation_method`` is inert/captured.
    Close-out markers (``valid_to``/``system_to``) are EXCLUDED (the FR content is immutable).
    Nodes
    are sorted by ``(value_type, tenor_days)`` so the hash is order-independent of the read."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "curve_type": row.curve_type,
        "currency_code": row.currency_code,
        "reference_key": row.reference_key,
        "curve_date": row.curve_date.isoformat(),
        "curve_source": row.curve_source,
        "interpolation_method": row.interpolation_method,
        "restatement_reason": row.restatement_reason,
        "supersedes_id": (None if row.supersedes_id is None else _norm_guid(row.supersedes_id)),
        "valid_from": _norm_datetime(row.valid_from),
        "system_from": _norm_datetime(row.system_from),
        "record_version": row.record_version,
        "nodes": [
            {
                "tenor_days": n.tenor_days,
                "tenor_label": n.tenor_label,
                "value_type": n.value_type,
                "point_value": _norm_decimal(n.point_value, _SCALE_CURVE_POINT),
            }
            for n in sorted(nodes, key=lambda x: (x.value_type, x.tenor_days))
        ],
    }


def exposure_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of an ``exposure_aggregate`` (IA) atom (P3-3 EXPOSURE
    component). The atom is TRUE append-only — the strongest pin flavor (no valid axis, no
    ``record_version``; ``system_from`` is the append time; re-verification is byte-identical
    unless tampered). Scales: ``signed_quantity`` 8; ``mark_value``/``exposure_amount`` 6;
    ``fx_rate`` 12 (the exposure column scales). ``fx_legs`` is the captured JSON leg evidence
    (an opaque immutable string)."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "calculation_run_id": _norm_guid(row.calculation_run_id),
        "input_snapshot_id": _norm_guid(row.input_snapshot_id),
        "portfolio_id": _norm_guid(row.portfolio_id),
        "instrument_id": _norm_guid(row.instrument_id),
        "base_currency": row.base_currency,
        "mark_currency": row.mark_currency,
        "signed_quantity": _norm_decimal(row.signed_quantity, _SCALE_QUANTITY),
        "mark_value": _norm_decimal(row.mark_value, _SCALE_MONEY),
        "fx_rate": _norm_decimal(row.fx_rate, _SCALE_FX_RATE),
        "fx_legs": row.fx_legs,
        "exposure_amount": _norm_decimal(row.exposure_amount, _SCALE_MONEY),
        "exposure_type": row.exposure_type,
        "system_from": _norm_datetime(row.system_from),
    }


def factor_content(row: Any) -> dict[str, Any]:
    """The captured content of a ``factor`` (EV) definition version (P3-3 FACTOR component — the
    ``portfolio_content`` EV flavor: no ``system_from``; ``record_version`` is the authoritative
    drift discriminator; the scope/vocab fields are value-captured so an EV amend moves the
    hash)."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "factor_code": row.factor_code,
        "factor_source": row.factor_source,
        "factor_family": row.factor_family,
        "factor_type": row.factor_type,
        "region": row.region,
        "currency_code": row.currency_code,
        "asset_class": row.asset_class,
        "frequency": row.frequency,
        "factor_name": row.factor_name,
        "description": row.description,
        "valid_from": _norm_datetime(row.valid_from),
        "record_version": row.record_version,
    }


def factor_return_series_content(factor: Any, rows: list[Any]) -> dict[str, Any]:
    """The captured content of one factor's pinned RETURN WINDOW (P3-4 FACTOR_RETURN component —
    the ``curve_content`` header+rows shape over FR rows). Each row is an immutable FR VERSION
    (corrections close it out and insert successors) ⇒ per-row id re-resolution is byte-stable;
    a later vendor supersede/correction is invisible to the pinned window (TR-09). Rows ordered
    by ``return_date``; values at the factor-return scale 12."""
    return {
        "factor_id": _norm_guid(factor.id),
        "factor_code": factor.factor_code,
        "factor_source": factor.factor_source,
        "return_type": rows[0].return_type if rows else None,
        "frequency": factor.frequency,
        "rows": [
            {
                "id": _norm_guid(r.id),
                "return_date": r.return_date.isoformat(),
                "return_type": r.return_type,
                "return_value": _norm_decimal(r.return_value, _SCALE_CURVE_POINT),
                "valid_from": _norm_datetime(r.valid_from),
                "system_from": _norm_datetime(r.system_from),
                "record_version": r.record_version,
            }
            for r in sorted(rows, key=lambda x: x.return_date)
        ],
    }


def factor_exposure_content(row: Any) -> dict[str, Any]:
    """The captured content of one ``factor_exposure_result`` row (P3-5 FACTOR_EXPOSURE component
    — an IA TRUE append-only row: the pin is byte-stable by construction). The full immutable
    column set at column scale (loading 12dp; exposure_amount 6dp)."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "calculation_run_id": _norm_guid(row.calculation_run_id),
        "input_snapshot_id": _norm_guid(row.input_snapshot_id),
        "model_version_id": _norm_guid(row.model_version_id),
        "system_from": _norm_datetime(row.system_from),
        "portfolio_id": _norm_guid(row.portfolio_id),
        "instrument_id": _norm_guid(row.instrument_id),
        "factor_id": _norm_guid(row.factor_id),
        "factor_code": row.factor_code,
        "factor_family": row.factor_family,
        "base_currency": row.base_currency,
        "mark_currency": row.mark_currency,
        "loading": _norm_decimal(row.loading, _SCALE_CURVE_POINT),
        "exposure_amount": _norm_decimal(row.exposure_amount, _SCALE_MONEY),
    }


def covariance_content(row: Any) -> dict[str, Any]:
    """The captured content of one ``covariance_result`` row (P3-5 COVARIANCE component — an IA
    TRUE append-only row). ``covariance_value`` at the 20dp covariance scale."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "calculation_run_id": _norm_guid(row.calculation_run_id),
        "input_snapshot_id": _norm_guid(row.input_snapshot_id),
        "model_version_id": _norm_guid(row.model_version_id),
        "system_from": _norm_datetime(row.system_from),
        "factor_id_1": _norm_guid(row.factor_id_1),
        "factor_id_2": _norm_guid(row.factor_id_2),
        "factor_code_1": row.factor_code_1,
        "factor_code_2": row.factor_code_2,
        "statistic_type": row.statistic_type,
        "return_type": row.return_type,
        "frequency": row.frequency,
        "n_observations": row.n_observations,
        "window_start": row.window_start.isoformat(),
        "window_end": row.window_end.isoformat(),
        "covariance_value": _norm_decimal(row.covariance_value, _SCALE_COVARIANCE),
    }


def benchmark_membership_content(benchmark: Any, constituent: Any) -> dict[str, Any]:
    """The captured content of one pinned ``benchmark_constituent`` FR version (P3-7 BENCHMARK
    component — the ``factor_return`` per-row FR flavor: each row is an immutable FR VERSION, so a
    later vendor supersede/correction closes it out and inserts a successor and is invisible to the
    pin, TR-09). Each component carries the benchmark HEADER identity + the effective_date so the
    binder can read ``(benchmark_id, effective_date)`` + code/source from any pin. ``weight`` at the
    constituent scale 12; ``constituent_currency`` captured verbatim (its NULL-ness is a binder
    refusal, never imputed)."""
    return {
        "id": _norm_guid(constituent.id),
        "tenant_id": _norm_guid(constituent.tenant_id),
        "benchmark_id": _norm_guid(benchmark.id),
        "benchmark_code": benchmark.benchmark_code,
        "benchmark_source": benchmark.benchmark_source,
        "benchmark_currency": benchmark.benchmark_currency,
        "effective_date": constituent.effective_date.isoformat(),
        "instrument_id": _norm_guid(constituent.instrument_id),
        "weight": _norm_decimal(constituent.weight, _SCALE_CURVE_POINT),
        "constituent_currency": constituent.constituent_currency,
        "valid_from": _norm_datetime(constituent.valid_from),
        "system_from": _norm_datetime(constituent.system_from),
        "record_version": constituent.record_version,
    }


def proxy_mapping_content(row: Any) -> dict[str, Any]:
    """The captured content of one pinned ``proxy_mapping`` FR version (PA-2 PROXY_MAPPING
    component — the per-row FR flavor: a later weight supersede/correction closes this version out
    and inserts a successor, invisible to the pin; TR-09). ``weight`` at the 12dp loading scale."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "private_instrument_id": _norm_guid(row.private_instrument_id),
        "factor_id": _norm_guid(row.factor_id),
        "weight": _norm_decimal(row.weight, _SCALE_CURVE_POINT),
        "mapping_method": row.mapping_method,
        "valid_from": _norm_datetime(row.valid_from),
        "system_from": _norm_datetime(row.system_from),
        "record_version": row.record_version,
    }


def scenario_shock_content(definition: Any, shock: Any) -> dict[str, Any]:
    """The captured content of one pinned ``scenario_shock`` FR version (P3-6 SCENARIO component —
    the ``benchmark_constituent`` per-row FR flavor: each row is an immutable FR VERSION, so a later
    shock supersede/correction closes it out + inserts a successor and is invisible to the pin,
    TR-09). Each component carries the scenario DEFINITION identity (id/code/scenario_type) so the
    run binder can read the scenario from any pin. ``shock_value`` at the 12dp shock scale;
    ``shock_type`` verbatim."""
    return {
        "id": _norm_guid(shock.id),
        "tenant_id": _norm_guid(shock.tenant_id),
        "scenario_definition_id": _norm_guid(definition.id),
        "scenario_code": definition.code,
        "scenario_type": definition.scenario_type,
        "factor_id": _norm_guid(shock.factor_id),
        "shock_value": _norm_decimal(shock.shock_value, _SCALE_CURVE_POINT),
        "shock_type": shock.shock_type,
        "valid_from": _norm_datetime(shock.valid_from),
        "system_from": _norm_datetime(shock.system_from),
        "record_version": shock.record_version,
    }


def transaction_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of a ``transaction`` (ENT-011, IA) row (PM-1 TRANSACTION
    component — the P3-3 EXPOSURE true-append-only pin flavor: no valid axis, no ``record_version``;
    ``system_from`` is the append time; re-verification is byte-identical unless tampered). The FULL
    immutable column set is pinned so the row reconstructs exactly (the return binder reads only the
    pinned content, never a live transaction). Scales: ``quantity`` 8; ``price``/``gross_amount`` 6
    (the transaction column scales). ``gross_amount``/``currency_code`` MAY be NULL — captured
    verbatim; a NULL on an in-set flow is a binder refusal (never imputed)."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "portfolio_id": _norm_guid(row.portfolio_id),
        "instrument_id": _norm_guid(row.instrument_id),
        "txn_type": row.txn_type,
        "trade_date": row.trade_date.isoformat(),
        "settle_date": (None if row.settle_date is None else row.settle_date.isoformat()),
        "quantity": _norm_decimal(row.quantity, _SCALE_QUANTITY),
        "price": (None if row.price is None else _norm_decimal(row.price, _SCALE_MONEY)),
        "gross_amount": (
            None if row.gross_amount is None else _norm_decimal(row.gross_amount, _SCALE_MONEY)
        ),
        "currency_code": row.currency_code,
        "external_ref": row.external_ref,
        "reverses_transaction_id": (
            None if row.reverses_transaction_id is None else _norm_guid(row.reverses_transaction_id)
        ),
        "description": row.description,
        "system_from": _norm_datetime(row.system_from),
    }


def portfolio_return_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of a ``portfolio_return_result`` (ENT-053, IA) row (P3-8
    PORTFOLIO_RETURN component — the P3-3 EXPOSURE true-append-only pin flavor: no valid axis, no
    ``record_version``; ``system_from`` the append time; byte-identical on re-verify). The FULL
    immutable column set is pinned so the benchmark-relative binder reconstructs each sub-period
    return (``metric_type``/``period_start``/``period_end``/``return_value``) exactly. Scales:
    ``begin_mv``/``end_mv``/``net_external_flow`` 6; ``return_value`` 12 (the result scales)."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "calculation_run_id": _norm_guid(row.calculation_run_id),
        "input_snapshot_id": _norm_guid(row.input_snapshot_id),
        "model_version_id": _norm_guid(row.model_version_id),
        "portfolio_id": _norm_guid(row.portfolio_id),
        "metric_type": row.metric_type,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "begin_mv": _norm_decimal(row.begin_mv, _SCALE_MONEY),
        "end_mv": _norm_decimal(row.end_mv, _SCALE_MONEY),
        "net_external_flow": _norm_decimal(row.net_external_flow, _SCALE_MONEY),
        "return_value": _norm_decimal(row.return_value, _SCALE_CURVE_POINT),
        "n_flows": row.n_flows,
        "n_periods": row.n_periods,
        "base_currency": row.base_currency,
        "system_from": _norm_datetime(row.system_from),
    }


def desmoothed_return_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of a ``desmoothed_return_result`` (ENT-056, IA) row (PA-3
    DESMOOTHED_RETURN component — the PORTFOLIO_RETURN/VAR governed-row pin flavor: no valid axis,
    no ``record_version``; ``system_from`` the append time; byte-identical on re-verify). The FULL
    immutable column set is pinned so the proxy-weight binder reconstructs the regression target
    (``metric_type``/``period_start``/``period_end``/``metric_value``) exactly. Nullable echo
    columns pin as null (the summary row's per-period echoes; a per-period row's summary echoes)."""

    def _opt_dec(value: Any, scale: int) -> str | None:
        return _norm_decimal(value, scale) if value is not None else None

    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "calculation_run_id": _norm_guid(row.calculation_run_id),
        "input_snapshot_id": _norm_guid(row.input_snapshot_id),
        "model_version_id": _norm_guid(row.model_version_id),
        "portfolio_id": _norm_guid(row.portfolio_id),
        "instrument_id": _norm_guid(row.instrument_id),
        "metric_type": row.metric_type,
        "period_start": row.period_start.isoformat(),
        "period_end": row.period_end.isoformat(),
        "metric_value": _norm_decimal(row.metric_value, _SCALE_CURVE_POINT),
        "observed_return": _opt_dec(row.observed_return, _SCALE_CURVE_POINT),
        "begin_mark": _opt_dec(row.begin_mark, _SCALE_MONEY),
        "end_mark": _opt_dec(row.end_mark, _SCALE_MONEY),
        "alpha": _norm_decimal(row.alpha, _SCALE_CURVE_POINT),
        "mark_currency": row.mark_currency,
        "observed_stdev": _opt_dec(row.observed_stdev, _SCALE_CURVE_POINT),
        "n_periods": row.n_periods,
        "system_from": _norm_datetime(row.system_from),
    }


def var_result_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of a ``var_result`` (ENT-027, IA) row (BT-1 VAR component —
    the P3-3 EXPOSURE true-append-only pin flavor: no valid axis, no ``record_version``;
    ``system_from`` the append time; byte-identical on re-verify). The BT-1-era immutable column
    set is pinned so the backtest binder reconstructs each forecast (``metric_type``/
    ``confidence_level``/``horizon_days``/``window_end``/``var_value``) exactly.

    **TWO columns are DELIBERATELY excluded** — PA-4's ``residual_variance`` and BT-2's
    ``estimate_age_days``. The reason is false drift, and it is sufficient on its own: adding a key
    would change the recomputed bytes of every ALREADY-PINNED var_result component and make
    ``verify_snapshot`` report drift on historical BT-1 snapshots that never moved. Test-pinned by
    ``test_var_result_pin_key_set_is_frozen``.

    *(Wave-5-close correction: this note also used to argue "and the backtest binder refuses
    VAR_PARAMETRIC_TOTAL rows in v1 anyway — no consumer reads it from a pin". **BT-2 admitted
    VAR_PARAMETRIC_TOTAL to METRIC_TYPES, so that clause is now FALSE** and has been struck. The
    exclusion stands on the false-drift reason alone. Recorded rather than quietly deleted: BT-2's
    own headline fold was a citation that had stopped saying what the text needed — this is the
    same class, self-inflicted, in the shipped code BT-2 changed.)*

    Scales: ``var_value``/``sigma`` 6 (the base-currency money scale); ``confidence_level`` 4;
    ``z_score`` 12."""
    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "calculation_run_id": _norm_guid(row.calculation_run_id),
        "input_snapshot_id": _norm_guid(row.input_snapshot_id),
        "model_version_id": _norm_guid(row.model_version_id),
        "exposure_run_id": _norm_guid(row.exposure_run_id),
        "covariance_run_id": (
            None if row.covariance_run_id is None else _norm_guid(row.covariance_run_id)
        ),
        "metric_type": row.metric_type,
        "base_currency": row.base_currency,
        "confidence_level": _norm_decimal(row.confidence_level, 4),
        "horizon_days": row.horizon_days,
        "z_score": None if row.z_score is None else _norm_decimal(row.z_score, _SCALE_CURVE_POINT),
        "sigma": None if row.sigma is None else _norm_decimal(row.sigma, _SCALE_MONEY),
        "var_value": _norm_decimal(row.var_value, _SCALE_MONEY),
        "n_factors": row.n_factors,
        "n_observations": row.n_observations,
        "window_start": row.window_start.isoformat(),
        "window_end": row.window_end.isoformat(),
        "system_from": _norm_datetime(row.system_from),
    }


def proxy_weight_estimate_content(row: Any) -> dict[str, Any]:
    """The immutable captured content of one ``proxy_weight_estimate_result`` (ENT-057, IA) row
    (PA-4 PROXY_WEIGHT component — the ``var_result`` true-append-only pin flavor: no valid axis,
    no ``record_version``; ``system_from`` the append time; byte-identical on re-verify). Pins the
    cited ``ESTIMATION_SUMMARY`` singleton so the total-VaR binder reads its ``residual_stdev`` +
    the row's own ``instrument_id`` (the correlation key back to the proxied instrument) WITHOUT a
    live read. ``metric_value``/``std_error``/``residual_stdev`` at the 12dp regression scale."""

    def _opt_dec(value: Any, scale: int) -> str | None:
        return _norm_decimal(value, scale) if value is not None else None

    return {
        "id": _norm_guid(row.id),
        "tenant_id": _norm_guid(row.tenant_id),
        "calculation_run_id": _norm_guid(row.calculation_run_id),
        "input_snapshot_id": _norm_guid(row.input_snapshot_id),
        "model_version_id": _norm_guid(row.model_version_id),
        "portfolio_id": _norm_guid(row.portfolio_id),
        "instrument_id": _norm_guid(row.instrument_id),
        "source_desmoothed_run_id": _norm_guid(row.source_desmoothed_run_id),
        "metric_type": row.metric_type,
        "factor_id": None if row.factor_id is None else _norm_guid(row.factor_id),
        "metric_value": _norm_decimal(row.metric_value, _SCALE_CURVE_POINT),
        "std_error": _opt_dec(row.std_error, _SCALE_CURVE_POINT),
        "n_observations": row.n_observations,
        "n_regressors": row.n_regressors,
        "residual_stdev": _opt_dec(row.residual_stdev, _SCALE_CURVE_POINT),
        "min_observations": row.min_observations,
        "series_currency": row.series_currency,
        "system_from": _norm_datetime(row.system_from),
    }


def benchmark_return_series_content(benchmark: Any, rows: list[Any]) -> dict[str, Any]:
    """The captured content of one benchmark's pinned RETURN WINDOW (P3-8 BENCHMARK_RETURN component
    — the ``factor_return_series_content`` header+rows shape over ``benchmark_return`` FR rows).
    Each row is an immutable FR VERSION (corrections close it out + insert a successor) ⇒ per-row id
    re-resolution is byte-stable; a later vendor supersede/correction is invisible to the pinned
    window (TR-09; ENT-052's first governed consumer). The benchmark HEADER identity + the uniform
    ``return_type``/``return_basis`` are carried so the binder reads them from the pin. Rows ordered
    by ``return_date``; values at the return scale 12."""
    return {
        "benchmark_id": _norm_guid(benchmark.id),
        "benchmark_code": benchmark.benchmark_code,
        "benchmark_source": benchmark.benchmark_source,
        "benchmark_currency": benchmark.benchmark_currency,
        "return_type": rows[0].return_type if rows else None,
        "return_basis": rows[0].return_basis if rows else None,
        "rows": [
            {
                "id": _norm_guid(r.id),
                "return_date": r.return_date.isoformat(),
                "return_type": r.return_type,
                "return_basis": r.return_basis,
                "return_value": _norm_decimal(r.return_value, _SCALE_CURVE_POINT),
                "valid_from": _norm_datetime(r.valid_from),
                "system_from": _norm_datetime(r.system_from),
                "record_version": r.record_version,
            }
            for r in sorted(rows, key=lambda x: x.return_date)
        ],
    }


def serialize_content(content: dict[str, Any]) -> str:
    """Canonical-serialize a per-kind content dict (sorted keys, compact, engine-independent)."""
    return canonicalize(content)


def content_hash(captured_content: str) -> str:
    """``sha256_hex`` of the canonical ``captured_content`` string (§7)."""
    return sha256_hex(captured_content)


def manifest_hash(
    *,
    tenant_id: str,
    as_of_valid_at: datetime,
    as_of_known_at: datetime,
    as_of_valuation_date: date,
    binding_predicate_version: str,
    component_count: int,
    component_hashes: list[tuple[str, str, str]],
) -> str:
    """The header reproducibility fingerprint: SHA-256 over the header cutoffs +
    ``component_count``
    (folded IN, anti-truncation) + the component hashes sorted by the NORMALIZED
    ``(component_kind, target_entity_id)``. Deterministic given identical cutoffs (§7)."""
    ordered = sorted(
        (
            [kind.lower(), _norm_guid(target_id), c_hash]
            for kind, target_id, c_hash in component_hashes
        ),
        key=lambda triple: (triple[0], triple[1]),
    )
    preimage = {
        "header": {
            "tenant_id": _norm_guid(tenant_id),
            "as_of_valid_at": _norm_datetime(as_of_valid_at),
            "as_of_known_at": _norm_datetime(as_of_known_at),
            "as_of_valuation_date": as_of_valuation_date.isoformat(),
            "binding_predicate_version": binding_predicate_version,
        },
        "component_count": component_count,
        "component_hashes": ordered,
    }
    return sha256_hex(canonicalize(preimage))
