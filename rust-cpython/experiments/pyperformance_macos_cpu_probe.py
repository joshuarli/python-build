"""Show how Darwin wait4 accounts for CPU in a waited three-process tree."""

import argparse
import json
import os
from pathlib import Path
import platform
import resource


def cpu(usage: resource.struct_rusage) -> dict[str, float]:
    return {"user_seconds": usage.ru_utime, "system_seconds": usage.ru_stime}


def work() -> None:
    value = 0
    for number in range(600_000):
        value += number * number
    for _ in range(120_000):
        os.stat("/dev/null")
    if value <= 0:
        raise RuntimeError("CPU probe did not perform its work")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("CPU probe requires native macOS arm64")
    if args.output.exists():
        parser.error(f"refusing to overwrite {args.output}")

    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_fd)
        grandchild = os.fork()
        if grandchild == 0:
            os.close(write_fd)
            work()
            os._exit(0)
        grandchild_pid, grandchild_status, grandchild_usage = os.wait4(grandchild, 0)
        if grandchild_pid != grandchild or os.waitstatus_to_exitcode(grandchild_status) != 0:
            os._exit(2)
        record = {
            "grandchild_wait4": cpu(grandchild_usage),
            "child_rusage_self": cpu(resource.getrusage(resource.RUSAGE_SELF)),
            "child_rusage_children": cpu(resource.getrusage(resource.RUSAGE_CHILDREN)),
        }
        os.write(write_fd, json.dumps(record).encode("utf-8"))
        os.close(write_fd)
        os._exit(0)

    os.close(write_fd)
    child_pid, child_status, child_usage = os.wait4(child, 0)
    if child_pid != child or os.waitstatus_to_exitcode(child_status) != 0:
        raise RuntimeError("CPU probe child failed")
    child_record = json.loads(os.read(read_fd, 4096))
    os.close(read_fd)
    grandchild = child_record["grandchild_wait4"]
    child_self = child_record["child_rusage_self"]
    parent_wait4 = cpu(child_usage)
    if not grandchild["user_seconds"] > 0 or not grandchild["system_seconds"] > 0:
        raise RuntimeError("probe did not exercise both user and system CPU")
    accounted = {
        field: parent_wait4[field] - child_self[field] - grandchild[field]
        for field in ("user_seconds", "system_seconds")
    }
    if any(abs(value) > 0.02 for value in accounted.values()):
        raise RuntimeError(f"parent wait4 does not contain the nested CPU within 20 ms: {accounted}")
    result = {
        "host": {"system": platform.system(), "machine": platform.machine(), "macos": platform.mac_ver()[0]},
        "work": "grandchild: 600000 arithmetic iterations and 120000 os.stat calls",
        **child_record,
        "parent_wait4_child": parent_wait4,
        "parent_rusage_children": cpu(resource.getrusage(resource.RUSAGE_CHILDREN)),
        "parent_wait4_minus_child_self_minus_grandchild_wait4": accounted,
        "conclusion": "parent wait4 for the child includes the waited grandchild's user and system CPU; summing nested ledgers double counts",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
