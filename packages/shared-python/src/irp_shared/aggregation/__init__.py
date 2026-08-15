"""Aggregation contracts (Wave 18, REQ-PPM-006/-007) — the neutral declaration surface.

Deliberately NOT under ``reproduction/``: the reproduction registry answers "can this family's
number be recomputed"; this package answers "what does this family CONSUME and how may its output
be COMBINED". PPM-008's rollup, the read views, and the reproduction adapters all consult it, so it
belongs to none of them. See ``contracts.py``.
"""

from irp_shared.aggregation.contracts import (
    EXPOSURE_CONSUMER_MEASURES,
    ForeignMeasureError,
    UndeclaredConsumerError,
    consumed_exposure_measure,
    refuse_foreign_measure,
)

__all__ = [
    "EXPOSURE_CONSUMER_MEASURES",
    "ForeignMeasureError",
    "UndeclaredConsumerError",
    "consumed_exposure_measure",
    "refuse_foreign_measure",
]
