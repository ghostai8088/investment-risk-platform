"""Deterministic hashing for the audit hash chain (audit_event_taxonomy.md §4A).

``event_payload_hash = SHA-256(canonical(payload))``
``event_hash         = SHA-256(previous_event_hash + event_payload_hash)``

Canonical serialization sorts keys and uses compact separators so the same logical event
always produces the same hash across engines and Python runs (HC-02/HC-03).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

#: Genesis link for the first event in a chain.
GENESIS_HASH = "0" * 64

#: Canonical serialization version recorded on each event (HC-03).
HASH_VERSION = "1"

HASH_ALGORITHM = "SHA-256"


def canonicalize(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def payload_hash(payload: dict[str, Any]) -> str:
    return sha256_hex(canonicalize(payload))


def chain_hash(previous_event_hash: str, event_payload_hash: str) -> str:
    return sha256_hex(previous_event_hash + event_payload_hash)
