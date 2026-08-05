"""RPT-1 — the first reproducible risk report (Wave-15 opener 2).

One report, for one portfolio as of one date, over already-shipped governed numbers: run-ID-bound,
snapshot-pinned, model-version-stamped, and byte-identically regenerable from its bound inputs
(REQ-RPT-001 / BR-9).
"""

from irp_shared.report.models import (
    RENDER_FORMAT_HTML,
    RENDER_FORMATS,
    REPORT_CODE_RISK_SUMMARY,
    REPORT_VERSION_LABEL_V1,
    RUN_TYPE_REPORT,
    ReportGeneration,
)

__all__ = [
    "RENDER_FORMATS",
    "RENDER_FORMAT_HTML",
    "REPORT_CODE_RISK_SUMMARY",
    "REPORT_VERSION_LABEL_V1",
    "RUN_TYPE_REPORT",
    "ReportGeneration",
]
