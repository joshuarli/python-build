#!/usr/bin/env python3
"""Block until the host reads quiet by perf.py's own definition.

Usage: python3 .claude/skills/rust-cpython-perf/wait_quiet.py [MINUTES] [MIN_IDLE]

Exit 0 as soon as one sample is quiet (CPU idle at or above MIN_IDLE percent,
on AC power); exit 1 if MINUTES (default 180) pass without one. Run it with
run_in_background so the completion notification is the wake-up.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "rust-cpython"))
import perf  # noqa: E402

minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0
min_idle = float(sys.argv[2]) if len(sys.argv) > 2 else perf.DEFAULT_MIN_IDLE
sample = perf._host_sample(min_idle, wait_seconds=minutes * 60)
print(f"{'QUIET' if sample['quiet'] else 'NOT QUIET'} idle={sample['cpu_idle_percent']}% "
      f"ac={sample['ac_power']} at {sample['time']}")
sys.exit(0 if sample["quiet"] else 1)
