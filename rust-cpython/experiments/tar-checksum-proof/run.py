"""Measure complete pinned-source archive reads with identical imports on both sides."""

import argparse
import json
from pathlib import Path
import sys
import tarfile
import time

import _tar_checksum_proof

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from source_tar_hybrid import archive_digest, read_archive, EXPECTED_DIGEST


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("control", "candidate"))
    parser.add_argument("archive")
    parser.add_argument("--loops", type=int, default=3)
    args = parser.parse_args()
    if args.loops < 1:
        parser.error("--loops must be positive")
    if args.mode == "candidate":
        original = tarfile.calc_chksums

        def calc_chksums(buf):
            if type(buf) is bytes and len(buf) == 512:
                return _tar_checksum_proof.scan(buf)
            return original(buf)

        tarfile.calc_chksums = calc_chksums
    archive_digest(args.archive)
    result = None
    start = time.perf_counter()
    for _ in range(args.loops):
        current = read_archive(args.archive)
        if result is not None and current != result:
            raise ValueError("archive result changed between passes")
        result = current
    internal = time.perf_counter() - start
    if result != (EXPECTED_DIGEST, 6539, 6031, 136064031):
        raise ValueError("archive result differs from locked result")
    print(json.dumps({"mode": args.mode, "digest": result[0], "members": result[1],
                      "regular_files": result[2], "regular_bytes": result[3],
                      "logical_bytes": result[3] * args.loops, "loops": args.loops,
                      "internal_seconds": internal}, sort_keys=True))


if __name__ == "__main__":
    main()
