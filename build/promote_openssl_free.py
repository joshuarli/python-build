"""Promote a qualified OpenSSL-free candidate into the official dist layout.

The research archive qualifier already writes the official archive and manifest
names when asked. This driver copies those bytes under dist/<triple>/,
attaches the sealed runtime evidence for Linux, and revalidates the result
with the same uvmirror gates the release assembly uses.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from buildsys.targets import TARGETS  # noqa: E402
from buildsys.uvmirror import (  # noqa: E402
    UvMirrorError,
    record_runtime_container,
    validate_artifact,
)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote a qualified OpenSSL-free candidate to dist/<triple>/"
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--triple", required=True, choices=sorted(TARGETS))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--archive-name", required=True)
    parser.add_argument("--manifest-name", required=True)
    args = parser.parse_args(argv)

    target = TARGETS[args.triple]
    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"FAIL promote: run directory does not exist: {run_dir}", file=sys.stderr)
        return 1
    archive_src = run_dir / "qualification" / "archive" / args.archive_name
    manifest_src = run_dir / "qualification" / "archive" / args.manifest_name
    for path in (archive_src, manifest_src):
        if path.is_symlink() or not path.is_file():
            print(f"FAIL promote: missing qualified file: {path}", file=sys.stderr)
            return 1

    out = args.dist / args.triple
    if out.exists() or out.is_symlink():
        print(f"FAIL promote: refusing to overwrite {out}", file=sys.stderr)
        return 1
    out.mkdir(parents=True)
    shutil.copyfile(archive_src, out / args.archive_name)
    shutil.copyfile(manifest_src, out / "artifact.json")

    try:
        manifest = json.loads((out / "artifact.json").read_text())
        if manifest.get("archive", {}).get("filename") != args.archive_name:
            raise UvMirrorError("promoted manifest names a different archive file")
        if _sha256(out / args.archive_name) != manifest["archive"]["sha256"]:
            raise UvMirrorError("promoted archive bytes do not match the manifest")

        if target.family == "linux-musl":
            runtime_receipt = json.loads(
                (run_dir / "docker-runtime.json").read_text()
            )
            probe = runtime_receipt.get("runtime_probe", {})
            smoke = {
                "ok": probe.get("ok") is True,
                "target": args.triple,
                "archive": args.archive_name,
                "archive_sha256": runtime_receipt.get("archive_sha256"),
                "python": manifest["product"]["version"],
            }
            (out / "runtime-smoke.json").write_text(json.dumps(smoke, indent=2) + "\n")
            record_runtime_container(out, args.triple, args.revision, "native")
            (out / "runtime-smoke.json").unlink()

        validate_artifact(out, args.triple, args.revision)
    except (OSError, json.JSONDecodeError, UvMirrorError, KeyError) as error:
        print(f"FAIL promote: {error}", file=sys.stderr)
        return 1
    print(f"OK promote {args.triple} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
