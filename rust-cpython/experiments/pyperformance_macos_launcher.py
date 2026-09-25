"""Run one pinned pyperformance script and ledger reaped child CPU usage.

Pyperf starts workers by rerunning argv[0]. Keeping this launcher as argv[0]
lets each worker report the CPU used by benchmark subprocesses it reaped.
The ledger runs after the benchmark body, outside pyperf's timed interval.
"""

import json
import os
from pathlib import Path
import resource
import sys


script = Path(os.environ["PYPERFORMANCE_SCRIPT"])
ledger = Path(os.environ["PYPERFORMANCE_CPU_LEDGER"])
try:
    namespace = {"__name__": "__main__", "__file__": str(script)}
    exec(compile(script.read_bytes(), str(script), "exec"), namespace)
finally:
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    record = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "worker": "--worker" in sys.argv,
        "child_user_seconds": children.ru_utime,
        "child_system_seconds": children.ru_stime,
        "own_user_seconds": own.ru_utime,
        "own_system_seconds": own.ru_stime,
    }
    (ledger / f"{os.getpid()}.json").write_text(
        json.dumps(record, sort_keys=True) + "\n", encoding="utf-8"
    )
