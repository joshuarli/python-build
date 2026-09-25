"""Sample the workload child separately from the uninstrumented speed runs."""

import json
import os
import subprocess
import tempfile
import time

from measure import ARCHIVE, DATA, RUNNER, WORK, TIME_FIELD, kernel_field


def attempt(name, side):
    mode = "candidate" if side == "candidate" else "control"
    command = ["/usr/bin/time", "-l", str(WORK / side / "stage/bin/python3.16"),
               str(RUNNER), mode, str(ARCHIVE), "--loops", "3"]
    environment = os.environ.copy()
    for key in tuple(environment):
        if key == "PYTHONPATH" or key == "PYTHONPYCACHEPREFIX" or key.startswith("DYLD_"):
            environment.pop(key)
    environment.update(PYTHONHASHSEED="1", PYTHONNOUSERSITE="1",
                       PYTHONMALLOC="default", PYTHONDONTWRITEBYTECODE="1")
    samples = []
    sampled_pids = set()
    with tempfile.TemporaryFile(mode="w+t") as out, tempfile.TemporaryFile(mode="w+t") as err:
        process = subprocess.Popen(command, stdout=out, stderr=err, env=environment)
        while process.poll() is None:
            listed = subprocess.run(["ps", "-axo", "pid=,ppid=,rss=,comm="],
                                    capture_output=True, text=True, check=True)
            for line in listed.stdout.splitlines():
                fields = line.split(None, 3)
                if len(fields) == 4 and int(fields[1]) == process.pid:
                    sampled_pids.add(int(fields[0]))
                    samples.append({"rss_bytes": int(fields[2]) * 1024})
            time.sleep(0.02)
        returncode = process.wait()
        out.seek(0)
        err.seek(0)
        stdout, raw = out.read(), err.read()
    timing = TIME_FIELD.search(raw)
    record = {"id": name, "side": side, "returncode": returncode,
              "samples": samples, "sampled_peak_rss_bytes": max(
                  (sample["rss_bytes"] for sample in samples), default=None),
              "sampled_process_count": len(sampled_pids)}
    if timing:
        record.update(user_seconds=float(timing.group(2)),
                      system_seconds=float(timing.group(3)),
                      kernel_peak_rss_bytes=kernel_field(raw, "maximum resident set size"),
                      peak_footprint_bytes=kernel_field(raw, "peak memory footprint"),
                      swaps=kernel_field(raw, "swaps"))
    if returncode == 0:
        record["output"] = json.loads(stdout)
    else:
        record["failure"] = {"stdout": stdout[-2000:], "stderr": raw[-2000:]}
    return record


def main():
    evidence = json.loads(DATA.read_text())
    evidence["memory_method"] = "20 ms external ps RSS samples of the direct Python child of /usr/bin/time; kernel lifetime peak RSS and physical footprint from time -l"
    evidence["memory_attempts"] = []
    evidence["memory_pairs"] = []
    try:
        for number in range(1, 4):
            sides = ["control", "candidate"]
            if number % 2 == 0:
                sides.reverse()
            ids = []
            for index, side in enumerate(sides, 1):
                name = f"memory-{number:02d}-{index:02d}-{side}"
                record = attempt(name, side)
                evidence["memory_attempts"].append(record)
                ids.append(name)
                if record["returncode"] != 0 or not record["samples"]:
                    raise RuntimeError(f"failed memory attempt: {name}")
                output = record["output"]
                if (output["digest"], output["members"], output["regular_files"],
                        output["regular_bytes"]) != (
                        "4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805",
                        6539, 6031, 136064031):
                    raise ValueError(f"mismatched output: {name}")
            evidence["memory_pairs"].append({"number": number, "attempts": ids})
    finally:
        DATA.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
