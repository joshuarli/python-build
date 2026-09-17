import json
from pathlib import Path
import sys

sys.path.insert(0, ".")
from buildsys.inputs import Cache, InputError, load_lock

cache = Cache(Path(".cache"))
try:
    inputs = load_lock(Path("sources.lock.json"))
    for entry in inputs:
        if entry.role == "reference":
            continue
        try:
            path = cache.require(entry)
            print(f"cached  {entry.name}")
        except InputError:
            print(f"fetch   {entry.name} ...", flush=True)
            path = cache.fetch(entry)
            print(f"ok      {entry.name} -> {path}")
except InputError as error:
    print(f"FAIL: {error}", file=sys.stderr)
    sys.exit(1)
