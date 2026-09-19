#!/bin/sh
# In-container driver: extract our tarball, sanity-check both interpreters,
# then run the rigorous suite once for each, sequentially in this same
# container so host conditions are shared.
#
# Invoked by benchmarks/run_benchmarks.sh with:
#   /inputs/ours.tar.gz  our packaged musl tarball (bind-mounted, read-only)
#   /results             writable output directory (bind-mounted)
set -eu

mkdir -p /bench/ours
tar -xzf /inputs/ours.tar.gz -C /bench/ours
OURS=/bench/ours/python/bin/python3.14
PBS=/bench/pbs/python/bin/python3.14

"$OURS" -c "import sys; assert sys.version_info[:3] == (3, 14, 6), sys.version_info"
"$PBS" -c "import sys; assert sys.version_info[:3] == (3, 14, 6), sys.version_info"

/bench/run_single.sh pbs-314-musl "$PBS" /results
/bench/run_single.sh ours-musl "$OURS" /results
