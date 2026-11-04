"""Canonical JSON and content hashes.

Package equality is byte equality of this encoding. Key order, whitespace,
and insignificant float noise must not change a hash.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any


def normalize(value: Any) -> Any:
    """Reduce a JSON-like tree to stable numbers, lists, and dicts."""

    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats cannot be hashed")
        quantized = Decimal(str(round(value, 6))).quantize(Decimal("0.000001"))
        return float(quantized)
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    raise TypeError(f"cannot canonicalize {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    """UTF-8 canonical JSON: sorted keys, no insignificant whitespace."""

    text = json.dumps(
        normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return text.encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_hash(value: Any) -> str:
    return sha256_hex(canonicalize(value))
