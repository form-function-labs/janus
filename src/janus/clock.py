"""The system clock adapter.

The domain stays clock-free (so it's deterministic and testable); time enters
only here, through the ``Clock`` port.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime


class SystemClock:
    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def monotonic(self) -> float:
        return time.monotonic()
