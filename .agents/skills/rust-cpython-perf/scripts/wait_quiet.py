#!/usr/bin/env python3
"""Wait for the performance harness's CPU-idle and power checks to pass.

Exit 0 on a quiet sample; exit 1 when the supplied minute limit expires.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "rust-cpython"))
import perf

minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0
min_idle = float(sys.argv[2]) if len(sys.argv) > 2 else perf.DEFAULT_MIN_IDLE
sample = perf._host_sample(min_idle, wait_seconds=minutes * 60)
print(f"{'QUIET' if sample['quiet'] else 'NOT QUIET'} idle={sample['cpu_idle_percent']}% "
      f"ac={sample['ac_power']} at {sample['time']}")
sys.exit(0 if sample["quiet"] else 1)
