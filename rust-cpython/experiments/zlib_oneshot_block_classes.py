"""Classify the first DEFLATE block of checked-in one-shot zlib workloads."""

import collections
import hashlib
import importlib.util
import json
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = Path(__file__).resolve().parent
WORKLOAD = ROOT / "benchmarks" / "workloads" / "zlib.py"
KINDS = ("stored", "fixed", "dynamic", "reserved")


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify(stream: bytes, decoded: bytes) -> tuple[str, bool]:
    if len(stream) < 7 or zlib.decompress(stream) != decoded:
        raise ValueError("invalid zlib fixture")
    cmf, flg = stream[:2]
    if cmf & 15 != 8 or (cmf * 256 + flg) % 31:
        raise ValueError("invalid zlib header")
    if flg & 32:
        raise ValueError("preset dictionary needs a different block offset")
    first = stream[2]
    return KINDS[(first >> 1) & 3], bool(first & 1)


def main() -> None:
    sources = {}
    groups = {}
    for name in ("zlib_oneshot_smallblobs", "zlib_oneshot_mixedblobs"):
        path = EXPERIMENTS / f"{name}.py"
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        module = load(path)
        for index in range(module.ROWS):
            decoded = module.payload(index)
            stream = zlib.compress(decoded, 6)
            category = module.CATEGORIES[index % len(module.CATEGORIES)] if hasattr(module, "CATEGORIES") else "smallblobs"
            key = f"{name}/{category}"
            group = groups.setdefault(key, {"classes": collections.Counter(), "final_first_block": collections.Counter(), "rust_at_8192_bytes": 0, "compressed_lengths": [], "decoded_lengths": []})
            kind, final = classify(stream, decoded)
            group["classes"][kind] += 1
            group["final_first_block"][str(final).lower()] += 1
            group["rust_at_8192_bytes"] += len(stream) >= 8192
            group["compressed_lengths"].append(len(stream))
            group["decoded_lengths"].append(len(decoded))
    sources[str(WORKLOAD.relative_to(ROOT))] = hashlib.sha256(WORKLOAD.read_bytes()).hexdigest()
    workload = load(WORKLOAD)
    for name, decoded, stream in workload._encoded_cases():
        kind, final = classify(stream, decoded)
        groups[f"zlib_decode_1m/{name}"] = {
            "classes": {kind: 1}, "final_first_block": {str(final).lower(): 1},
            "rust_at_8192_bytes": int(len(stream) >= 8192),
            "compressed_lengths": [len(stream)], "decoded_lengths": [len(decoded)],
            "stream_sha256": hashlib.sha256(stream).hexdigest(),
        }
    for group in groups.values():
        for key in ("compressed_lengths", "decoded_lengths"):
            lengths = group.pop(key)
            group[key] = {"min": min(lengths), "max": max(lengths)}
    print(json.dumps({"recipe": "python3 rust-cpython/experiments/zlib_oneshot_block_classes.py", "host_zlib": zlib.ZLIB_RUNTIME_VERSION, "sources_sha256": sources, "groups": groups}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
