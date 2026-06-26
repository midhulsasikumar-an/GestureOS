"""GestureOS application entry point.

STUB — Checkpoint 0 (Project Foundation).
Full app wiring (App/core.py + App/capture_thread.py) is implemented in
Checkpoint 1 (GestureOS Core Platform) and later.

This stub exists so the project root has a runnable entry point from the
very first checkpoint, matching the Implementation Plan §4 Acceptance
Criteria: 'Running `python main.py` from a clean checkout produces no
import errors and exits cleanly.'
"""

from __future__ import annotations

import sys


__version__ = "0.0.0+checkpoint0"
__checkpoint__ = "0"


def main() -> int:
    """Stub entry point. Prints version and exits with code 0.

    Full GUI / capture-thread / pipeline orchestration is added in
    Checkpoint 1+ per the Implementation Plan.
    """
    print(f"GestureOS v{__version__} (Checkpoint {__checkpoint__} stub)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
