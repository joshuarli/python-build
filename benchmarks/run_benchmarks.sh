#!/bin/sh
# Compatibility entry point for the previous PBS comparison command.
# The benchmark controller owns all preparation, execution, and reporting.
set -eu

REPO="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec python3 "$REPO/benchmarks/bench.py" run --preset pbs "$@"
