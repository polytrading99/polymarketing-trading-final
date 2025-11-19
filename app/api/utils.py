from __future__ import annotations

from decimal import Decimal
from typing import Optional


def decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["decimal_to_float"]

