"""Two independent, cache-busted sealed builds compared file-by-file (plan 8.3).

Both builds are clean — the Linux targets use `docker build --no-cache` on
the `sealed` stage, macOS runs `build/sealed.py` from a cleared work tree —
so reusing compiled objects across the two runs cannot masquerade as
reproducibility; only the immutable `.cache/objects` downloads are shared,
which plan 8.3 explicitly allows.

On macOS the raw comparison is not the answer on its own: every Mach-O
carries an ad-hoc signature covering the whole image, so the per-link
LC_UUID propagates into the signature and makes identical code look
different. The report therefore separates signature metadata from compiled
content per image rather than leaving the reader to guess which they have.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from buildsys.inputs import canonical_json  # noqa: E402
from buildsys import macho  # noqa: E402
from buildsys.bootstrap import load_macos_toolchain  # noqa: E402
from buildsys.reproduce import compare_trees, macho_difference  # noqa: E402
from buildsys.targets import target_for_triple  # noqa: E402


def _method(platform: str) -> str:
    return (
        f"Two independent `docker build --platform {platform} --no-cache "
        "--target sealed` runs (cache fully busted, offline dependency+"
        "CPython build both times), staged installs extracted and compared "
        "file-by-file before stripping/packaging."
    )


def _build_sealed(tag: str, platform: str) -> None:
    subprocess.run(
        ["docker", "build", "--platform", platform, "--target", "sealed",
         "--no-cache", "-t", tag, "."],
        cwd=REPO, check=True,
    )


def _extract_staged(tag: str, dest: Path) -> Path:
    container = subprocess.run(
        ["docker", "create", tag], capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        subprocess.run(
            ["docker", "cp", f"{container}:/work/build/stage/cpython-staged/install", str(dest)],
            check=True,
        )
    finally:
        subprocess.run(["docker", "rm", container], capture_output=True)
    return dest


def _reproduce_macos(target) -> int:
    """Two clean sealed builds on this machine, compared file-by-file.

    The first tree is set aside before the rebuild wipes the staging area, so
    the comparison is between two *complete* builds rather than between a
    build and leftovers of itself. Only `.cache/objects` is shared, which
    plan 8.3 explicitly permits.
    """
    import shutil

    stage = REPO / "build" / "stage" / "cpython-staged" / "install"
    if not stage.is_dir():
        print("FAIL reproduce: no staged install; run a build first")
        return 1
    work = REPO / "build" / "reproduce-work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    first = work / "first"
    shutil.copytree(stage, first, symlinks=True)

    for stale in ("work", "stage", "prefix"):
        shutil.rmtree(REPO / "build" / stale, ignore_errors=True)
    print("BUILD sealed (clean, rebuilds dependencies and CPython)", flush=True)
    result = subprocess.run([sys.executable, "build/sealed.py"], cwd=REPO)
    if result.returncode != 0:
        print("FAIL reproduce: sealed rebuild failed")
        return 1

    second = work / "second"
    shutil.copytree(stage, second, symlinks=True)

    # Separate "the hashes differ" from "the compiled code differs". Every
    # Mach-O on Apple Silicon carries an ad-hoc signature covering the whole
    # image, so the per-link LC_UUID propagates into the signature and makes a
    # raw comparison say nothing about whether the code is reproducible.
    def analyse(first_tree: Path, second_tree: Path) -> dict:
        result = compare_trees(first_tree, second_tree)
        images = {}
        for relative in result["content_differs"]:
            a, b = first_tree / relative, second_tree / relative
            if not (a.is_file() and b.is_file()
                    and macho.is_macho(a) and macho.is_macho(b)):
                continue
            images[relative] = macho_difference(a, b)
        identical = [n for n, d in images.items()
                     if d.get("compiled_content_identical")]
        result["macho_analysis"] = {
            "images_differing": len(images),
            "images_whose_compiled_content_is_identical": len(identical),
            "images_with_content_differences":
                sorted(set(images) - set(identical))[:20],
            "total_compiled_content_bytes": sum(
                d.get("compiled_content_bytes", 0) for d in images.values()
            ),
            "max_compiled_content_bytes": max(
                (d.get("compiled_content_bytes", 0) for d in images.values()),
                default=0,
            ),
            "interpretation": (
                "A differing image whose signature-metadata bytes account for "
                "the entire difference has identical compiled content; only "
                "its LC_UUID and the ad-hoc signature covering it differ. "
                "Anything with residual bytes differs in compiled content and "
                "is a real reproducibility finding."
            ),
        }
        return result

    # Compare before stripping, then again after. The unstripped trees carry
    # the linker's N_OSO STABS entries, which record each object file's mtime
    # for staleness checking and therefore legitimately differ between builds;
    # the stripped trees are what actually ships, so that is the comparison
    # that answers "is the artifact reproducible".
    report = analyse(first, second)
    strip = load_macos_toolchain(REPO / "bootstrap.lock.json").llvm_prefix / "bin" / "llvm-strip"
    for tree in (first, second):
        for image in macho.find_machos(tree):
            subprocess.run([str(strip), "--strip-debug", str(image)],
                           capture_output=True, check=True)
            macho.sign_adhoc(image)
    stripped = analyse(first, second)
    report["stripped"] = {
        "files_compared": stripped["files_compared"],
        "content_differs": stripped["content_differs"],
        "byte_identical": stripped["byte_identical"],
        "macho_analysis": stripped["macho_analysis"],
        "note": (
            "The comparison that describes the shipped artifact. Entries "
            "above are the unstripped trees, which additionally differ in "
            "per-object build timestamps that --strip-debug removes."
        ),
    }
    report["method"] = (
        "Two independent sealed `sandbox-exec` builds on this machine, each "
        "rebuilding every native dependency and CPython from a cleared work "
        "tree; only the immutable downloaded inputs are shared. The staged "
        "installs are compared file-by-file twice: as built, and again after "
        "the same `--strip-debug` pass that packaging applies, because the "
        "stripped form is what ships."
    )
    report["target"] = target.triple
    report["macos_signing_note"] = (
        "On Apple Silicon every Mach-O carries an ad-hoc code signature that "
        "covers the whole image, and each link stamps a fresh LC_UUID. Any "
        "difference at all therefore propagates into the signature bytes, so "
        "a raw hash comparison overstates the change. Suppressing the UUID is "
        "not an option on macOS 26: `-Wl,-no_uuid` produces a binary dyld "
        "refuses to load ('missing LC_UUID load command'), verified here. "
        "What remains is reported per image as signature metadata versus "
        "compiled content."
    )
    dist = REPO / "dist" / target.triple
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "reproducibility.json").write_text(canonical_json(report) + "\n")
    print(f"OK    reproduce -> byte_identical={report['byte_identical']} "
          f"({len(report['content_differs'])} of {report['files_compared']} files differ)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    target = target_for_triple(args.target)
    if target.is_macos:
        return _reproduce_macos(target)
    tags = (f"python-build-m1:reproduce-a-{target.alpine_arch}",
            f"python-build-m1:reproduce-b-{target.alpine_arch}")

    work = REPO / "build" / "reproduce-work" / target.alpine_arch
    if work.exists():
        import shutil
        shutil.rmtree(work)
    work.mkdir(parents=True)

    trees = []
    for tag in tags:
        print(f"BUILD {tag} (--no-cache, sealed, {target.docker_platform})", flush=True)
        _build_sealed(tag, target.docker_platform)
        dest = work / tag.split(":")[-1] / "install"
        trees.append(_extract_staged(tag, dest))

    report = compare_trees(trees[0], trees[1])
    report["method"] = _method(target.docker_platform)
    report["target"] = target.triple
    dist = REPO / "dist" / target.triple
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "reproducibility.json").write_text(canonical_json(report) + "\n")
    print(f"OK    reproduce -> byte_identical={report['byte_identical']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
