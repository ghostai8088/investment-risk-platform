"""Anti-corruption layer for generic CSV ingestion (THR-05 / THR-06) — pure logic, no DB.

Enforced at the boundary BEFORE any staged row is persisted: file-type allowlist (CSV only),
filename sanitization (path-traversal), explicit encoding decode, std-lib CSV parse (no shell-out,
no spreadsheet/macro engine), and per-cell formula-injection neutralization. The byte-size cap is a
transport guard enforced by the caller WHILE reading the upload (this module exposes the limit).
``scan_for_malware`` is a NON-enforcing no-op AV seam (OD-042) — a real integration swaps it later
with no signature change. Every failure raises an :class:`AntiCorruptionError` carrying a stable
``reason`` code so the rejection can be audited (metadata/reason only — never the raw payload).
"""

from __future__ import annotations

import csv
import io
import os
from collections.abc import Sequence
from typing import Any

from irp_shared.ingestion.models import SCAN_SKIPPED

#: Hard upload-size cap (10 MiB) — a DoS guard (THR-05). The caller counts bytes WHILE reading and
#: must not trust ``Content-Length``; this is the single source of truth for the limit.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: CSV-only allowlist. The decisive check is the ``.csv`` extension; content-type is advisory
#: (browsers misreport CSV as ``application/vnd.ms-excel`` etc.), so it is permissive but bounded.
ALLOWED_EXTENSIONS = (".csv",)
ALLOWED_CONTENT_TYPES = frozenset(
    {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel", ""}
)

#: Leading characters that make a spreadsheet cell an executable formula on export (THR-06).
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

#: ``csv.DictReader`` collects surplus cells of a too-wide row under this key (as a list). We reject
#: such ragged rows so no list-valued cell can slip past per-cell formula neutralization (THR-06).
_OVERFLOW_KEY = "__overflow__"


class AntiCorruptionError(Exception):
    """An upload rejected by the anti-corruption layer. ``reason`` is a stable, audit-safe code."""

    reason = "anti_corruption"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class FileTypeNotAllowed(AntiCorruptionError):
    reason = "file_type_not_allowed"


class FilenameUnsafe(AntiCorruptionError):
    reason = "filename_unsafe"


class EncodingInvalid(AntiCorruptionError):
    reason = "encoding_invalid"


class MalformedContent(AntiCorruptionError):
    reason = "malformed_content"


class EmptyFile(AntiCorruptionError):
    reason = "empty_file"


def sanitize_filename(raw: str | None) -> str:
    """Return a safe basename: strip directories, null bytes, and control chars; reject traversal.

    The client filename is never trusted as a path (THR-06); only the basename is kept."""
    if not raw:
        raise FilenameUnsafe("missing filename")
    if "\x00" in raw:
        raise FilenameUnsafe("filename contains a null byte")
    # Take the basename under both separators; reject any residual traversal token.
    base = os.path.basename(raw.replace("\\", "/"))
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    if not base or base in {".", ".."} or ".." in base:
        raise FilenameUnsafe(f"unsafe filename: {raw!r}")
    return base[:255]


def validate_file_type(filename: str, content_type: str | None) -> None:
    """Reject anything that is not a ``.csv`` upload (CSV-only allowlist)."""
    lowered = filename.lower()
    if not lowered.endswith(ALLOWED_EXTENSIONS):
        raise FileTypeNotAllowed(f"only CSV uploads are allowed (got {filename!r})")
    if content_type is not None and content_type.split(";")[0].strip() not in ALLOWED_CONTENT_TYPES:
        raise FileTypeNotAllowed(f"content-type {content_type!r} is not an allowed CSV type")


def decode_text(raw_bytes: bytes, encoding: str = "utf-8") -> str:
    """Strictly decode the upload (default UTF-8). An undecodable byte stream is rejected — we do
    not silently substitute replacement characters (which would corrupt the staged data)."""
    if not raw_bytes:
        raise EmptyFile("uploaded file is empty")
    try:
        return raw_bytes.decode(encoding)
    except UnicodeDecodeError as exc:
        raise EncodingInvalid(f"file is not valid {encoding}: {exc}") from exc


def neutralize_cell(value: Any) -> Any:
    """Neutralize a CSV-injection formula cell by prefixing a single quote (THR-06). Non-string and
    empty values pass through unchanged; the original text is preserved (prefixed), not dropped."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def parse_csv(text: str) -> list[dict[str, Any]]:
    """Parse CSV with the std-lib reader (no shell-out / macro engine) into a list of dict rows,
    formula-neutralizing every cell. Raises :class:`MalformedContent` on a garbled file."""
    try:
        reader = csv.DictReader(io.StringIO(text), restkey=_OVERFLOW_KEY)
        if reader.fieldnames is None or not any(f for f in reader.fieldnames):
            raise MalformedContent("CSV has no header row")
        rows: list[dict[str, Any]] = []
        for raw_row in reader:
            # A row with MORE columns than the header would smuggle surplus cells (a list under
            # the overflow key) past per-cell neutralization — reject the ragged row outright.
            if _OVERFLOW_KEY in raw_row:
                raise MalformedContent("row has more columns than the header")
            rows.append({key: neutralize_cell(val) for key, val in raw_row.items()})
    except csv.Error as exc:
        raise MalformedContent(f"malformed CSV: {exc}") from exc
    if not rows:
        raise EmptyFile("CSV has a header but no data rows")
    return rows


def scan_for_malware(raw_bytes: bytes) -> str:
    """No-op AV/malware scan seam (OD-042). Returns a NON-clean ``SKIPPED`` status today so a
    deployment can never silently believe scanning happened; a real AV integration replaces this
    body (and may gate on ``CLEAN``) with NO caller/schema change. ``raw_bytes`` is unused."""
    del raw_bytes  # placeholder: no scanning performed at the skeleton level
    return SCAN_SKIPPED


def validate_and_parse(
    raw_bytes: bytes, *, filename: str, content_type: str | None
) -> tuple[str, Sequence[dict[str, Any]]]:
    """Run the full anti-corruption pipeline and return ``(sanitized_filename, parsed_rows)``.

    Order: filename sanitize → type allowlist → decode → CSV parse + neutralize. Any failure raises
    an :class:`AntiCorruptionError`; nothing is persisted by this pure function."""
    safe_name = sanitize_filename(filename)
    validate_file_type(safe_name, content_type)
    text = decode_text(raw_bytes)
    rows = parse_csv(text)
    return safe_name, rows
