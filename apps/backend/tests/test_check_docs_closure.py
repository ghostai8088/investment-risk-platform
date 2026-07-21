"""API-1b (OQ-W9C-5): the closure-discipline docs-check — teeth for the API-1-class missing-stamp
miss that recurred at FIVE consecutive wave closes. Guards the two failure modes the verifier
(CLAIM 6) proved a naive check would hit: a slice-id in another row's PROSE, and an in-flight
planning DRAFT whose own roadmap row is not yet DONE."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

from check_docs import _closure_stamp_errors, _done_slice_ids  # noqa: E402


def test_done_slice_ids_are_row_anchored_not_prose() -> None:
    roadmap = "\n".join(
        [
            "| 1 | **API-1 — the read surface** ✅ **DONE** (the API-1b scope-column gap) | M |",
            "| 4 | **FE-3 — the product UI** ✅ **DONE** (the API-1b entity-read gap) | L |",
            "| 1 | **API-1b — the flagship reads** (OD-API-1-H, not yet done) | S/M |",
            "| 2 | **FE-3b — the browser login** | M |",
        ]
    )
    done = _done_slice_ids(roadmap)
    # Row-anchored: only the leading bold title token of a ✅ **DONE** row is a match.
    assert done == {"API-1", "FE-3"}
    # The CLAIM-6 trap: "API-1b" appears inside TWO ✅ **DONE** rows' prose — it must NOT be counted
    # (else CI false-fails the in-flight API-1b planning DRAFT).
    assert "API-1B" not in done
    # A row without the DONE marker is not counted (an in-flight planning DRAFT is legitimate).
    assert "FE-3B" not in done


def test_real_tree_has_no_unstamped_shipped_record() -> None:
    """Regression guard: every DONE slice's decision record is stamped (not left 'DRAFT for
    ratification'). This is the exact invariant the API-1 stamp miss violated before the Wave-9
    close fixed it."""
    assert _closure_stamp_errors() == []
