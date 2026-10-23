from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
TARGET_TRIPLE = "aarch64-apple-darwin"
RTLS_REVISION = "302423b49e494863d07630d50b15a9488ec85ef7"
RTLS_ARCHIVE_SHA256 = "8f188c405d18da8d099e9923722a764f14a93c466c0d1d9c548a42d47540639a"
RUST_VERSION = "1.99.1"
DISABLED_MODULES = ("_ssl", "_hashlib")
HASHING_SOURCE_FILES = (
    "Cargo.lock",
    "Cargo.toml",
    "README.md",
    "REPRODUCE.md",
    "THIRD_PARTY_LICENSES.md",
    "_hashlib.py",
    "build.rs",
    "compare-reference.py",
    "run-tests.sh",
    "src/lib.rs",
    "src/python_ffi.rs",
    "testdrivers/allocation_failures.py",
    "testdrivers/combined_tls.py",
    "testdrivers/public_attributes.py",
    "testdrivers/subinterpreters.py",
    "testdrivers/subinterpreter_worker.py",
)
OPENSSL_ENVIRONMENT = (
    "OPENSSL_INCLUDES",
    "OPENSSL_LDFLAGS",
    "OPENSSL_LIBS",
    "OPENSSL_RPATH",
)


class BuildError(Exception):
    pass


def repository_common_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()).resolve().parent


def require_same_locks(common_root: Path) -> None:
    for name in ("sources.lock.json", "bootstrap.lock.json"):
        if (REPO / name).read_bytes() != (common_root / name).read_bytes():
            raise BuildError(f"{name} differs between this worktree and the shared cache owner")


def require_work_path(path: Path) -> Path:
    path = Path(path).resolve()
    work_root = (REPO / ".work").resolve()
    if not path.is_relative_to(work_root):
        raise BuildError(f"build output must stay under {work_root}: {path}")
    return path


def load_dependency_driver():
    path = REPO / "build" / "deps.py"
    spec = importlib.util.spec_from_file_location("python_build_deps_driver", path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load existing dependency recipes from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sandbox_environment(
    run_dir: Path,
    locked,
    rust_bin: Path | None = None,
    kache_bin: Path | None = None,
) -> dict[str, str]:
    from buildsys.sandbox import SealedRun

    tool_directories = [str(locked.llvm_prefix / "bin")]
    if rust_bin is not None:
        tool_directories.append(str(rust_bin))
    if kache_bin is not None:
        tool_directories.append(str(kache_bin))
    tool_directories.extend(
        str(tool.parent)
        for tool in (locked.make, locked.pkgconf)
        if tool is not None
    )
    tool_directories.extend(("/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    sealed = SealedRun(write_paths=[run_dir], home=run_dir / "home")
    return sealed.environment({"PATH": ":".join(dict.fromkeys(tool_directories))})


def network_boundary(run_dir: Path) -> dict:
    from buildsys.sandbox import network_boundary_selftest

    report = network_boundary_selftest(Path(sys.executable), run_dir / "network-boundary")
    if not report["ok"]:
        raise BuildError(f"sandbox network boundary failed: {report}")
    return report


def source_inputs(cache, pins: dict, names: tuple[str, ...]) -> dict[str, Path]:
    missing = sorted(set(names) - pins.keys())
    if missing:
        raise BuildError("missing locked source entries: " + ", ".join(missing))
    return {name: cache.require(pins[name]) for name in names}


def is_openssl_dependency(dependency: str) -> bool:
    name = Path(dependency).name.lower()
    return name.startswith(("libssl", "libcrypto")) or "openssl" in name


def build_dependencies(run_dir: Path, dependency_prefix: Path, cache, pins, target, toolchain) -> tuple[str, ...]:
    from buildsys.deporder import dependency_order
    from buildsys.recipes import BuildError as RecipeBuildError
    from buildsys.recipes import Recipe, build_recipe

    driver = load_dependency_driver()
    names = tuple(
        name
        for name in dependency_order(target)
        if name not in {"pkgconf", "openssl"}
    )
    if "openssl" in names:
        raise BuildError("the no-OpenSSL dependency graph includes openssl")
    entries = source_inputs(cache, pins, names)
    dependency_prefix.mkdir(parents=True)
    dependency_work = run_dir / "dependency-work"
    dependency_work.mkdir()
    logs = run_dir / "logs" / "dependencies"
    for name in names:
        recipe = Recipe(
            name=name,
            layout=driver.RECIPE_LAYOUTS[name],
            configure_args=driver.configure_args(name, dependency_prefix, target),
            configure_env=driver.configure_environment(name, target),
            make_targets=driver.make_targets(name),
            cflags=driver.cflags_for(name, target),
            log_path=logs / name,
        )
        print(f"BUILD dependency {name} {pins[name].version}", flush=True)
        try:
            build_recipe(
                recipe,
                entries[name],
                dependency_work,
                dependency_prefix,
                toolchain=toolchain,
            )
        except RecipeBuildError as error:
            raise BuildError(f"dependency {name} failed: {error}") from error
        driver.special_install(
            name,
            dependency_work / name,
            dependency_prefix,
            logs / f"{name}-special.log",
        )
    if (dependency_prefix / "lib" / "libssl.a").exists() or (
        dependency_prefix / "lib" / "libcrypto.a"
    ).exists():
        raise BuildError("the dependency prefix contains an OpenSSL archive")
    if (dependency_prefix / "include" / "openssl").exists():
        raise BuildError("the dependency prefix contains OpenSSL headers")
    return names


def build_cpython(
    run_dir: Path,
    prefix: Path,
    dependency_prefix: Path,
    cpython_blob: Path,
    cache_root: Path,
    target,
    toolchain,
) -> Path:
    from buildsys.ca_bundle import CABundleError, install_fallback_ca_bundle
    from buildsys.cpython import configuration
    from buildsys.inputs import safe_extract
    from buildsys.patches import apply_patch_set
    from buildsys.recipes import run

    source_root = run_dir / "cpython-source"
    source = safe_extract(cpython_blob, source_root) / "Python-3.15.1"
    apply_patch_set(source, REPO / "patches" / "cpython")
    build_directory = run_dir / "cpython-build"
    build_directory.mkdir()
    args, environment = configuration(dependency_prefix, target)
    args = [
        argument
        for argument in args
        if argument not in {"--enable-optimizations"}
        and not argument.startswith("--with-openssl")
    ]
    if any(argument.startswith("--with-openssl") for argument in args):
        raise BuildError("CPython configure arguments still enable OpenSSL")
    for name in OPENSSL_ENVIRONMENT:
        environment.pop(name, None)
    environment.pop("PROFILE_TASK", None)
    environment.pop("PYTHONHASHSEED", None)
    environment.update(
        {
            "SOURCE_DATE_EPOCH": "1704067200",
            "PKG_CONFIG": "pkg-config",
        }
    )
    env = toolchain.env(environment)
    configure = source / "configure"
    run(
        [str(configure), f"--prefix={prefix}", *args],
        cwd=build_directory,
        env=env,
        log=run_dir / "logs" / "cpython-configure.log",
    )
    setup_local = build_directory / "Modules" / "Setup.local"
    setup_local.parent.mkdir(parents=True, exist_ok=True)
    setup_local.write_text("*disabled*\n" + "".join(f"{name}\n" for name in DISABLED_MODULES))
    if tuple(setup_local.read_text().splitlines()[1:]) != DISABLED_MODULES:
        raise BuildError("Modules/Setup.local does not disable the required modules")
    print("BUILD CPython 3.15.1 without PGO and OpenSSL modules", flush=True)
    run(
        [toolchain.make, "-j", str(toolchain.jobs)],
        cwd=build_directory,
        env=env,
        log=run_dir / "logs" / "cpython-build.log",
    )
    run(
        [toolchain.make, "install"],
        cwd=build_directory,
        env=env,
        log=run_dir / "logs" / "cpython-install.log",
    )
    try:
        install_fallback_ca_bundle(
            prefix,
            cache_root=cache_root,
            lock_path=REPO / "sources.lock.json",
        )
    except CABundleError as error:
        raise BuildError(f"cannot install the locked CA fallback: {error}") from error
    return prefix


def verify_base_prefix(prefix: Path, run_dir: Path) -> None:
    from buildsys import macho
    from buildsys.product import PRODUCT

    binary = PRODUCT.interpreter(prefix)
    library = PRODUCT.stdlib(prefix)
    for name in ("_ssl", "_hashlib"):
        extensions = list((library / "lib-dynload").glob(f"{name}*"))
        if extensions:
            raise BuildError(f"{name} was built into the no-OpenSSL prefix: {extensions}")
    images = macho.find_machos(prefix)
    linked = {
        image: dependency
        for image in images
        for dependency in macho.dependencies(image)
        if is_openssl_dependency(dependency)
    }
    if linked:
        raise BuildError(f"the no-OpenSSL prefix links OpenSSL: {linked}")
    private = run_dir / "private"
    for path in private.rglob("*"):
        if is_openssl_dependency(path.name):
            raise BuildError(f"the private dependency graph contains OpenSSL: {path}")
    result = subprocess.run(
        [
            str(binary),
            "-I",
            "-S",
            "-B",
            "-c",
            "import importlib.util, sys; "
            "assert sys.version_info[:3] == (3, 15, 1); "
            "assert importlib.util.find_spec('_ssl') is None; "
            "assert importlib.util.find_spec('_hashlib') is None",
        ],
        cwd=run_dir,
        env={"HOME": str(run_dir / "home"), "TMPDIR": str(run_dir / "tmp")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise BuildError(
            "the installed CPython base failed its no-OpenSSL import check: "
            f"{result.stdout}{result.stderr}"
        )


def rust_toolchain() -> tuple[Path, Path, Path]:
    rustup_home = Path(
        os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup"))
    )
    tool_bin = rustup_home / "toolchains" / f"{RUST_VERSION}-aarch64-apple-darwin" / "bin"
    cargo = tool_bin / "cargo"
    rustc = tool_bin / "rustc"
    kache = Path(shutil.which("kache") or "")
    if not cargo.is_file() or not rustc.is_file() or not kache.is_file():
        raise BuildError(
            f"Rust {RUST_VERSION} and kache must already be installed before the offline build"
        )
    result = subprocess.run(
        [str(rustc), "--version"], capture_output=True, text=True, check=True
    )
    if result.stdout.split()[1] != RUST_VERSION:
        raise BuildError(f"expected Rust {RUST_VERSION}, found {result.stdout.strip()}")
    return cargo, rustc, kache


def validate_adapter_sources(rtls_source: Path, hashing_source: Path) -> tuple[Path, Path]:
    rtls_source = Path(rtls_source).resolve()
    hashing_source = Path(hashing_source).resolve()
    if not rtls_source.is_dir():
        raise BuildError(f"RTLS checkout does not exist: {rtls_source}")
    if not hashing_source.is_dir():
        raise BuildError(f"hashing lane does not exist: {hashing_source}")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=rtls_source,
        capture_output=True,
        text=True,
        check=True,
    )
    if result.stdout.strip() != RTLS_REVISION:
        raise BuildError(
            f"RTLS checkout must be {RTLS_REVISION}, found {result.stdout.strip()}"
        )
    hashing_source_digest(hashing_source)
    rtls_manifest = rtls_source / "rust" / "Cargo.toml"
    if not rtls_manifest.is_file():
        raise BuildError(f"RTLS Rust manifest is missing: {rtls_manifest}")
    return rtls_source, hashing_source


def hashing_source_digest(source: Path) -> str:
    source = Path(source).resolve()
    if not source.is_dir():
        raise BuildError(f"hashing source directory does not exist: {source}")
    actual_files = set()
    for path in source.rglob("*"):
        relative = path.relative_to(source).as_posix()
        if path.is_symlink():
            raise BuildError(f"hashing source contains a symlink: {relative}")
        if path.is_file():
            actual_files.add(relative)
        elif not path.is_dir():
            raise BuildError(f"hashing source contains a special file: {relative}")
    expected_files = set(HASHING_SOURCE_FILES)
    missing = sorted(expected_files - actual_files)
    unexpected = sorted(actual_files - expected_files)
    if missing or unexpected:
        raise BuildError(
            f"hashing source file set differs from its replay contract: "
            f"missing={missing}, unexpected={unexpected}"
        )
    digest = hashlib.sha256()
    for relative in HASHING_SOURCE_FILES:
        path = source / relative
        name = relative.encode("utf-8")
        size = path.stat().st_size
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as source_file:
            while block := source_file.read(1024 * 1024):
                digest.update(block)
    return digest.hexdigest()


def stage_hashing_source(source: Path, run_dir: Path, inputs: Path) -> Path:
    source = Path(source).resolve()
    run_dir = Path(run_dir).resolve()
    inputs = Path(inputs).resolve()
    destination = run_dir / "hashing-build"
    checksum = inputs / "hashing-source.sha256"
    if destination.exists() or destination.is_symlink() or checksum.exists() or checksum.is_symlink():
        raise BuildError("refusing to replace a staged hashing source snapshot")
    before = hashing_source_digest(source)
    with tempfile.TemporaryDirectory(dir=run_dir, prefix=".hashing-source-") as temporary:
        staged = Path(temporary) / "hashing-build"
        staged.mkdir()
        for relative in HASHING_SOURCE_FILES:
            source_file = source / relative
            staged_file = staged / relative
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, staged_file)
        staged_digest = hashing_source_digest(staged)
        after = hashing_source_digest(source)
        if before != after or staged_digest != before:
            raise BuildError("hashing source changed while its fetch snapshot was created")
        os.replace(staged, destination)
    checksum.write_text(before + "\n", encoding="ascii")
    return destination


def verify_hashing_source_snapshot(run_dir: Path, source: Path | None = None) -> Path:
    run_dir = Path(run_dir).resolve()
    snapshot = run_dir / "hashing-build"
    checksum = run_dir / "inputs" / "hashing-source.sha256"
    if checksum.is_symlink() or not checksum.is_file():
        raise BuildError(f"hashing source snapshot digest is missing: {checksum}")
    expected = checksum.read_text(encoding="ascii").strip()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise BuildError(f"hashing source snapshot digest is invalid: {checksum}")
    staged_digest = hashing_source_digest(snapshot)
    if staged_digest != expected:
        raise BuildError("staged hashing source changed after fetch; fetch again into a fresh run directory")
    if source is not None and hashing_source_digest(source) != expected:
        raise BuildError("hashing source changed after fetch; fetch again into a fresh run directory")
    return snapshot


def rtls_source_digest(source: Path) -> str:
    source = Path(source)
    try:
        root_metadata = source.lstat()
    except OSError as error:
        raise BuildError(f"prepared RTLS source is missing: {source}: {error}") from error
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise BuildError(f"prepared RTLS source is not a real directory: {source}")
    paths = [source, *source.rglob("*")]
    paths.sort(key=lambda path: "." if path == source else path.relative_to(source).as_posix())
    digest = hashlib.sha256()
    for path in paths:
        relative = "." if path == source else path.relative_to(source).as_posix()
        try:
            metadata = path.lstat()
        except OSError as error:
            raise BuildError(f"cannot inspect prepared RTLS source {relative}: {error}") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise BuildError(f"prepared RTLS source contains a symlink: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            kind = b"d"
        elif stat.S_ISREG(metadata.st_mode):
            kind = b"f"
        else:
            raise BuildError(f"prepared RTLS source contains a special file: {relative}")
        name = relative.encode("utf-8")
        digest.update(kind)
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(stat.S_IMODE(metadata.st_mode).to_bytes(4, "big"))
        if kind == b"d":
            continue
        digest.update(metadata.st_size.to_bytes(8, "big"))
        try:
            with path.open("rb") as source_file:
                read_size = 0
                while block := source_file.read(1024 * 1024):
                    digest.update(block)
                    read_size += len(block)
            after = path.lstat()
        except OSError as error:
            raise BuildError(f"cannot read prepared RTLS source {relative}: {error}") from error
        if (
            read_size != metadata.st_size
            or not stat.S_ISREG(after.st_mode)
            or after.st_ino != metadata.st_ino
            or after.st_size != metadata.st_size
            or stat.S_IMODE(after.st_mode) != stat.S_IMODE(metadata.st_mode)
        ):
            raise BuildError(f"prepared RTLS source changed while hashing: {relative}")
    return digest.hexdigest()


def record_rtls_source_snapshot(
    run_dir: Path,
    *,
    expected_digest: str | None = None,
) -> Path:
    run_dir = Path(run_dir).resolve()
    source = run_dir / "rtls-build"
    inputs = run_dir / "inputs"
    checksum = inputs / "rtls-source.sha256"
    if inputs.is_symlink() or not inputs.is_dir():
        raise BuildError(f"prepared Rust input directory is missing or unsafe: {inputs}")
    if checksum.exists() or checksum.is_symlink():
        raise BuildError(f"refusing to replace an RTLS source digest: {checksum}")
    digest = rtls_source_digest(source)
    if expected_digest is not None and digest != expected_digest:
        raise BuildError("prepared RTLS source changed during Cargo fetch")
    try:
        with checksum.open("x", encoding="ascii") as output:
            output.write(digest + "\n")
    except OSError as error:
        raise BuildError(f"cannot record prepared RTLS source digest {checksum}: {error}") from error
    return checksum


def verify_rtls_source_snapshot(run_dir: Path) -> Path:
    run_dir = Path(run_dir).resolve()
    source = run_dir / "rtls-build"
    inputs = run_dir / "inputs"
    checksum = inputs / "rtls-source.sha256"
    if inputs.is_symlink() or not inputs.is_dir():
        raise BuildError(f"prepared Rust input directory is missing or unsafe: {inputs}")
    if checksum.is_symlink() or not checksum.is_file():
        raise BuildError(f"prepared RTLS source digest is missing: {checksum}")
    expected_bytes = checksum.read_bytes()
    if len(expected_bytes) != 65 or expected_bytes[-1:] != b"\n":
        raise BuildError(f"prepared RTLS source digest is invalid: {checksum}")
    try:
        expected = expected_bytes[:-1].decode("ascii")
    except UnicodeDecodeError as error:
        raise BuildError(f"prepared RTLS source digest is invalid: {checksum}") from error
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise BuildError(f"prepared RTLS source digest is invalid: {checksum}")
    actual = rtls_source_digest(source)
    if actual != expected:
        raise BuildError("prepared RTLS source changed after fetch; fetch again into a fresh run directory")
    return source


def load_webpki_helper():
    path = REPO / "research" / "rtls-graviola" / "prepare_webpki.py"
    spec = importlib.util.spec_from_file_location("rtls_prepare_webpki", path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load pinned webpki preparation helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rustls_helper():
    path = REPO / "research" / "rtls-graviola" / "prepare_rustls.py"
    spec = importlib.util.spec_from_file_location("rtls_prepare_rustls", path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load pinned rustls preparation helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_rust_license_helper():
    path = REPO / "research" / "rtls-graviola" / "rust_licenses.py"
    spec = importlib.util.spec_from_file_location("rtls_rust_licenses", path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load Rust license helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_rtls_patch(checkout: Path, name: str) -> None:
    from buildsys.patches import PatchError, apply_patch

    patch = REPO / "research" / "rtls-graviola" / name
    try:
        apply_patch(checkout, patch)
    except PatchError as error:
        raise BuildError(f"cannot apply {name} to the pinned RTLS source: {error}") from error


def fetch_rust_inputs(
    run_dir: Path,
    rtls_source: Path,
    hashing_source: Path,
    cargo: Path,
) -> None:
    from buildsys.inputs import safe_extract

    rtls_source, hashing_source = validate_adapter_sources(rtls_source, hashing_source)
    checkout = run_dir / "rtls-build"
    if checkout.exists() or checkout.is_symlink():
        raise BuildError(f"refusing to replace prepared RTLS checkout: {checkout}")
    inputs = run_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    checksum = inputs / "rtls-source.sha256"
    if inputs.is_symlink() or checksum.exists() or checksum.is_symlink():
        raise BuildError(f"refusing to replace a staged RTLS source digest: {checksum}")
    source_archive = inputs / "rtls-source.tar"
    with source_archive.open("wb") as output:
        result = subprocess.run(
            ["git", "archive", "--format=tar", RTLS_REVISION],
            cwd=rtls_source,
            stdout=output,
            stderr=subprocess.PIPE,
            text=True,
        )
    if result.returncode:
        raise BuildError(f"cannot archive pinned RTLS source: {result.stderr[-4000:]}")
    with source_archive.open("rb") as archive:
        archive_digest = hashlib.file_digest(archive, "sha256").hexdigest()
    if archive_digest != RTLS_ARCHIVE_SHA256:
        raise BuildError(
            "the pinned RTLS source archive differs from the verified bytes: "
            f"expected {RTLS_ARCHIVE_SHA256}, found {archive_digest}"
        )
    safe_extract(source_archive, checkout)
    apply_rtls_patch(checkout, "rtls-graviola.patch")
    hashing_build = stage_hashing_source(hashing_source, run_dir, inputs)
    helper = load_webpki_helper()
    webpki_archive = inputs / f"rustls-webpki-{helper.VERSION}.crate"
    helper.fetch(webpki_archive)
    helper.prepare(webpki_archive, checkout)
    rustls_helper = load_rustls_helper()
    rustls_archive = inputs / f"rustls-{rustls_helper.RUSTLS_VERSION}.crate"
    rustls_helper.fetch_archive(rustls_archive)
    rustls_helper.prepare(rustls_archive, checkout)
    prepared_digest = rtls_source_digest(checkout)
    cargo_home = run_dir / "cargo-home"
    cargo_home.mkdir(parents=True, exist_ok=True)
    target_dir = run_dir / "cargo-fetch-target"
    (run_dir / "tmp").mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "CARGO_HOME": str(cargo_home),
            "CARGO_TARGET_DIR": str(target_dir),
            "TMPDIR": str(run_dir / "tmp"),
        }
    )
    environment.pop("CARGO_NET_OFFLINE", None)
    manifests = (
        ("RTLS", checkout / "rust" / "Cargo.toml"),
        ("hashing", hashing_build / "Cargo.toml"),
    )
    for name, manifest in manifests:
        result = subprocess.run(
            [str(cargo), "fetch", "--locked", "--manifest-path", str(manifest)],
            cwd=manifest.parent,
            env=environment,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise BuildError(
                f"Cargo fetch failed for {name}: "
                f"{(result.stdout + result.stderr)[-4000:]}"
            )
        print(f"FETCHED Rust inputs for {name}", flush=True)
    record_rtls_source_snapshot(run_dir, expected_digest=prepared_digest)


def require_fetched_rust_inputs(
    run_dir: Path,
    hashing_source: Path | None = None,
) -> tuple[Path, Path]:
    checkout = run_dir / "rtls-build"
    hashing_build = run_dir / "hashing-build"
    cargo_home = run_dir / "cargo-home"
    required = (
        checkout / "rust" / "Cargo.lock",
        checkout / "webpki" / "Cargo.toml",
        checkout / "rustls" / "Cargo.toml",
        run_dir / "inputs" / "rtls-source.sha256",
        hashing_build / "Cargo.lock",
        hashing_build / "Cargo.toml",
        cargo_home / "registry",
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        raise BuildError(
            "offline Rust inputs are incomplete; run the separate --phase fetch first: "
            + ", ".join(str(path) for path in missing)
        )
    checkout = verify_rtls_source_snapshot(run_dir)
    hashing_build = verify_hashing_source_snapshot(run_dir, hashing_source)
    return checkout, hashing_build


def build_rust_extension(
    cargo: Path,
    rustc: Path,
    kache: Path,
    manifest: Path,
    cargo_home: Path,
    target_dir: Path,
    run_dir: Path,
    name: str,
    python: Path,
    target,
    toolchain,
    jobs: int,
    *,
    rtls: bool,
) -> Path:
    from buildsys.recipes import BuildError as RecipeBuildError, run

    cpu_flag = target.cpu_baseline_cflag
    if not cpu_flag.startswith("-mcpu="):
        raise BuildError(f"unsupported Rust CPU baseline flag: {cpu_flag}")
    rustflags = ["-C", f"target-cpu={cpu_flag.removeprefix('-mcpu=')}"]
    if rtls:
        rustflags.extend(("-C", "link-arg=-undefined", "-C", "link-arg=dynamic_lookup"))
    environment = os.environ.copy()
    linker_environment_key = (
        f"CARGO_TARGET_{target.triple.upper().replace('-', '_')}_LINKER"
    )
    for key in tuple(environment):
        if key in {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTFLAGS"} or (
            key.startswith("CARGO_TARGET_")
            and key.endswith(("_RUSTFLAGS", "_LINKER"))
        ):
            environment.pop(key)
    environment.update(
        {
            "CARGO_HOME": str(cargo_home),
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TARGET_DIR": str(target_dir),
            "CC": toolchain.cc,
            "CXX": toolchain.cxx,
            "AR": toolchain.ar,
            "RANLIB": toolchain.ranlib,
            "MACOSX_DEPLOYMENT_TARGET": target.deployment_target,
            "PYO3_PYTHON": str(python),
            "RUSTFLAGS": " ".join(rustflags),
            "RUSTC": str(rustc),
            "RUSTC_WRAPPER": str(kache),
            "SDKROOT": toolchain.sdkroot,
            "TMPDIR": str(run_dir / "tmp"),
        }
    )
    environment[linker_environment_key] = toolchain.cc
    if rtls:
        environment["PYO3_BUILD_EXTENSION_MODULE"] = "1"
    else:
        environment["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"
    log = run_dir / "logs" / f"{name}-cargo.log"
    try:
        run(
            [
                str(cargo),
                "build",
                "--verbose",
                "--jobs",
                str(jobs),
                "--offline",
                "--locked",
                "--manifest-path",
                str(manifest),
            ],
            cwd=manifest.parent,
            env=environment,
            log=log,
        )
    except RecipeBuildError as error:
        raise BuildError(f"Rust {name} extension build failed: {error}") from error
    extension_name = "lib_rustls.dylib" if rtls else "lib_hashlib_graviola.dylib"
    extension = target_dir / "debug" / extension_name
    if not extension.is_file():
        raise BuildError(f"Rust {name} extension is missing: {extension}")
    return extension


def install_adapters(
    prefix: Path,
    run_dir: Path,
    rtls_source: Path,
    hashing_source: Path,
    cargo_home: Path,
    cargo: Path,
    rustc: Path,
    kache: Path,
    target,
    toolchain,
    jobs: int,
) -> None:
    from buildsys import macho
    from buildsys.product import PRODUCT

    stdlib = PRODUCT.stdlib(prefix)
    dynload = stdlib / "lib-dynload"
    rtls_package = stdlib / "rtls"
    if not (stdlib / "ssl.py").is_file():
        raise BuildError(f"candidate standard-library ssl.py is missing: {stdlib / 'ssl.py'}")
    for path in (stdlib / "_ssl.py", stdlib / "_ssl_metadata.py", stdlib / "_hashlib.py"):
        if path.exists() or path.is_symlink():
            raise BuildError(f"refusing to overwrite candidate module: {path}")
    if rtls_package.exists():
        raise BuildError(f"refusing to overwrite candidate RTLS package: {rtls_package}")
    (run_dir / "tmp").mkdir(parents=True, exist_ok=True)
    rtls_manifest = rtls_source / "rust" / "Cargo.toml"
    hashlib_manifest = hashing_source / "Cargo.toml"
    license_helper = load_rust_license_helper()
    try:
        license_report = license_helper.install_rust_licenses(
            prefix,
            {"rtls": rtls_manifest, "hashing": hashlib_manifest},
            {"rtls": rtls_source, "hashing": hashing_source},
            cargo_home,
            cargo,
            run_dir / "tmp",
        )
    except license_helper.LicenseCollectionError as error:
        raise BuildError(f"cannot install Rust license notices: {error}") from error
    print(
        "INSTALL Rust dependency license notices "
        f"({license_report['packages']} packages, {license_report['notices']} files)",
        flush=True,
    )
    rtls_extension = build_rust_extension(
        cargo,
        rustc,
        kache,
        rtls_manifest,
        cargo_home,
        run_dir / "cargo-target" / "rtls",
        run_dir,
        "rtls",
        PRODUCT.interpreter(prefix),
        target,
        toolchain,
        jobs,
        rtls=True,
    )
    hashing_extension = build_rust_extension(
        cargo,
        rustc,
        kache,
        hashlib_manifest,
        cargo_home,
        run_dir / "cargo-target" / "hashing",
        run_dir,
        "hashing",
        PRODUCT.interpreter(prefix),
        target,
        toolchain,
        jobs,
        rtls=False,
    )
    shutil.copytree(
        rtls_source / "src" / "rtls",
        rtls_package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copyfile(
        hashing_source / "_hashlib.py",
        stdlib / "_hashlib.py",
    )
    installed_rtls = rtls_package / "_rustls.abi3.so"
    shutil.copyfile(rtls_extension, installed_rtls)
    macho.set_install_name(installed_rtls, "@rpath/_rustls.abi3.so")
    shutil.copyfile(
        hashing_extension,
        dynload / "_hashlib_graviola.abi3.so",
    )
    shutil.copyfile(
        REPO / "research" / "rtls-graviola" / "ssl_facade.py",
        stdlib / "ssl.py",
    )
    shutil.copyfile(
        REPO / "research" / "rtls-graviola" / "ssl_native_compat.py",
        stdlib / "_ssl.py",
    )
    shutil.copyfile(
        REPO / "research" / "rtls-graviola" / "ssl_metadata.py",
        stdlib / "_ssl_metadata.py",
    )


def relocate_candidate(
    prefix: Path,
    run_dir: Path,
    locked,
    toolchain,
    cargo: Path,
    rustc: Path,
    kache: Path,
) -> Path:
    from buildsys import macho
    from buildsys.relocate import RelocationError, macho_relocate

    libraries = sorted((prefix / "lib").glob("libpython3*.dylib"))
    if not libraries:
        raise BuildError(f"no CPython shared library found under {prefix / 'lib'}")
    install_name = macho.dylib_id(libraries[0])
    if install_name is None:
        raise BuildError(f"CPython shared library has no Mach-O identity: {libraries[0]}")
    configure_prefix = Path(install_name).parent.parent
    if not Path(install_name).is_absolute() or Path(install_name).parent.name != "lib":
        configure_prefix = prefix.resolve()
    else:
        configure_prefix = configure_prefix.resolve()

    command_paths = tuple(
        Path(path)
        for path in (
            toolchain.cc,
            toolchain.cxx,
            toolchain.ar,
            toolchain.ranlib,
            toolchain.ld,
            toolchain.nm,
            toolchain.strip,
            toolchain.make,
            locked.llvm_profdata,
            locked.pkgconf,
            cargo,
            rustc,
            kache,
        )
        if path
    ) + tuple(
        repository_common_root() / ".cache" / "llvm" / "toolchains"
        / locked.llvm_prefix.name / "bin" / Path(path).name
        for path in (
            toolchain.cc,
            toolchain.cxx,
            toolchain.ar,
            toolchain.ranlib,
            toolchain.ld,
            toolchain.nm,
            toolchain.strip,
            locked.llvm_profdata,
        )
        if path
    )
    build_directories = (
        "private",
        "cpython-source",
        "cpython-build",
        "cargo-home",
        "cargo-target",
        "rtls-build",
    )
    builder_paths = (
        run_dir / "private",
        run_dir / "cpython-source",
        run_dir / "cpython-build",
        run_dir / "cargo-home",
        run_dir / "cargo-target",
        run_dir / "rtls-build",
        locked.llvm_prefix,
        locked.sdkroot,
        *(configure_prefix.parent / directory for directory in build_directories),
    )
    try:
        macho_relocate(
            prefix,
            run_dir / "private",
            configure_prefix=str(configure_prefix),
            builder_paths=builder_paths,
            command_paths=command_paths,
        )
    except RelocationError as error:
        raise BuildError(f"cannot relocate OpenSSL-free candidate: {error}") from error
    relocated = run_dir / "relocated prefix"
    if relocated.exists():
        raise BuildError(f"refusing to replace relocated candidate: {relocated}")
    shutil.copytree(prefix, relocated, symlinks=True)
    return relocated


def verify_overlay_prefix(prefix: Path, run_dir: Path, target) -> None:
    from buildsys import macho
    from buildsys.product import PRODUCT

    binary = PRODUCT.interpreter(prefix)
    stdlib = PRODUCT.stdlib(prefix)
    dynload = stdlib / "lib-dynload"
    for name in ("_ssl", "_hashlib"):
        extensions = [
            path
            for pattern in (
                f"{name}.cpython-*.so",
                f"{name}.abi3.so",
                f"{name}.so",
                f"{name}.dylib",
            )
            for path in dynload.glob(pattern)
        ]
        if extensions:
            raise BuildError(f"candidate contains a native {name} extension: {extensions}")
    required = (
        stdlib / "ssl.py",
        stdlib / "_ssl.py",
        stdlib / "_ssl_metadata.py",
        stdlib / "_hashlib.py",
        dynload / "_hashlib_graviola.abi3.so",
        stdlib / "rtls" / "_rustls.abi3.so",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise BuildError("candidate overlay is incomplete: " + ", ".join(missing))
    images = macho.find_machos(prefix)
    linked = {
        image: dependency
        for image in images
        for dependency in macho.dependencies(image)
        if is_openssl_dependency(dependency)
    }
    if linked:
        raise BuildError(f"the overlaid prefix links OpenSSL: {linked}")
    cargo_target = str(run_dir / "cargo-target")
    cargo_loads = {
        image: dependency
        for image in images
        for dependency in macho.dependencies(image)
        if cargo_target in dependency
    }
    cargo_ids = {
        image: install_name
        for image in images
        if (install_name := macho.dylib_id(image)) is not None
        and cargo_target in install_name
    }
    if cargo_loads or cargo_ids:
        raise BuildError(
            f"installed extensions retain Cargo target paths: loads={cargo_loads}, ids={cargo_ids}"
        )
    if macho.dylib_id(stdlib / "rtls" / "_rustls.abi3.so") != "@rpath/_rustls.abi3.so":
        raise BuildError("installed RTLS extension has an unexpected Mach-O identity")
    builder_references = {
        image: value
        for image in images
        for value in (
            *macho.dependencies(image),
            macho.dylib_id(image) or "",
            *macho.rpaths(image),
        )
        if str(run_dir) in value
    }
    if builder_references:
        raise BuildError(f"relocated candidate retains builder paths: {builder_references}")
    floor_mismatches = {}
    for image in images:
        version = macho.build_version(image)
        if version is None or version.minos != target.deployment_target:
            floor_mismatches[image] = version.minos if version else None
    if floor_mismatches:
        raise BuildError(
            f"candidate deployment floors differ from {target.deployment_target}: {floor_mismatches}"
        )
    result = subprocess.run(
        [
            str(binary),
            "-I",
            "-S",
            "-B",
            "-c",
            "import hashlib, importlib.util, ssl, sys, _hashlib, _ssl; "
            f"assert sys.prefix == {str(prefix)!r}; "
            "assert _ssl.__file__.endswith('_ssl.py'); "
            "assert _ssl._RUSTLS_BACKEND is True; "
            "assert _hashlib.__file__.endswith('_hashlib.py'); "
            "assert importlib.util.find_spec('_hashlib_graviola') is not None; "
            "assert ssl.SSLContext; assert hashlib.sha256(b'candidate').digest()",
        ],
        cwd=run_dir,
        env={"HOME": str(run_dir / "home"), "TMPDIR": str(run_dir / "tmp")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise BuildError(
            "installed no-OpenSSL adapters failed their import check: "
            f"{result.stdout}{result.stderr}"
        )


def build_base(run_dir: Path, cache_root: Path, target, toolchain) -> Path:
    from buildsys.bootstrap import lto_smoke_test
    from buildsys.inputs import Cache, InputError, load_lock
    from buildsys.targets import native_target

    if target.triple != TARGET_TRIPLE or platform.system() != "Darwin" or platform.machine() != "arm64":
        raise BuildError("this research build supports native macOS arm64 only")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "tmp").mkdir(exist_ok=True)
    print("CHECK ThinLTO toolchain fixture", flush=True)
    lto_smoke_test(toolchain, run_dir / "logs" / "lto-smoke")
    pins = {entry.name: entry for entry in load_lock(REPO / "sources.lock.json")}
    cache = Cache(cache_root)
    from buildsys.deporder import dependency_order

    dependencies = tuple(
        name for name in dependency_order(target) if name not in {"pkgconf", "openssl"}
    )
    try:
        inputs = source_inputs(cache, pins, (*dependencies, "cpython", "certifi-ca"))
    except InputError as error:
        raise BuildError(f"locked source input is unavailable: {error}") from error
    dependency_prefix = run_dir / "private"
    build_dependencies(run_dir, dependency_prefix, cache, pins, target, toolchain)
    prefix = run_dir / "prefix"
    build_cpython(
        run_dir,
        prefix,
        dependency_prefix,
        inputs["cpython"],
        cache_root,
        target,
        toolchain,
    )
    enforce_candidate_exclusions(prefix)
    verify_base_prefix(prefix, run_dir)
    print(f"OK no-OpenSSL CPython base -> {prefix}", flush=True)
    return prefix


def enforce_candidate_exclusions(prefix: Path) -> dict:
    from buildsys.product import PRODUCT
    from buildsys.scope import ScopeError, enforce_exclusions, verify_exclusions

    test_suite = PRODUCT.stdlib(prefix) / "test"
    if not test_suite.is_dir():
        raise BuildError(f"CPython prerelease test suite is missing: {test_suite}")
    try:
        report = enforce_exclusions(prefix)
    except ScopeError as error:
        raise BuildError(f"cannot enforce no-OpenSSL prefix exclusions: {error}") from error
    remaining = verify_exclusions(prefix)
    if remaining:
        raise BuildError(
            "no-OpenSSL prefix retains deliberately excluded components: "
            + ", ".join(remaining)
        )
    if not test_suite.is_dir():
        raise BuildError(f"CPython prerelease test suite was removed: {test_suite}")
    print(
        f"PRUNE excluded CPython components ({len(report['removed'])} entries)",
        flush=True,
    )
    return report


def positive_jobs(value: str) -> int:
    try:
        jobs = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if jobs < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return jobs


def main(argv: list[str] | None = None) -> int:
    from buildsys.bootstrap import BootstrapError, load_macos_toolchain, toolchain_for
    from buildsys.inputs import InputError
    from buildsys.patches import PatchError
    from buildsys.sandbox import SealedRun, available
    from buildsys.targets import UnsupportedTargetError, native_target

    parser = argparse.ArgumentParser(
        description="Build a native macOS CPython prefix without OpenSSL"
    )
    parser.add_argument("--phase", choices=("fetch", "base", "overlay", "all"), default="base")
    parser.add_argument("--jobs", type=positive_jobs, default=2)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--prefix", type=Path)
    parser.add_argument("--rtls-source", type=Path)
    parser.add_argument(
        "--hashing-source",
        type=Path,
        default=REPO / "research" / "rtls-graviola" / "hashing",
    )
    parser.add_argument("--inside-sandbox", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cargo-bin", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--rustc-bin", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--kache-bin", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12):
        print("FAIL no-OpenSSL build: run with Python 3.12 or newer", file=sys.stderr)
        return 2
    try:
        common_root = repository_common_root()
        require_same_locks(common_root)
        target = native_target()
        if target.triple != TARGET_TRIPLE:
            raise BuildError(f"target must be {TARGET_TRIPLE}, found {target.triple}")
        locked = load_macos_toolchain(common_root / "bootstrap.lock.json")
        toolchain = (
            locked.toolchain(jobs=args.jobs)
            if args.inside_sandbox or args.phase in {"fetch", "overlay"}
            else toolchain_for(target, common_root / "bootstrap.lock.json", jobs=args.jobs)
        )
    except (
        BootstrapError,
        BuildError,
        UnsupportedTargetError,
        subprocess.SubprocessError,
        OSError,
    ) as error:
        print(f"FAIL no-OpenSSL build: {error}", file=sys.stderr)
        return 1
    try:
        if args.phase == "fetch" and not args.inside_sandbox:
            if args.prefix is not None or args.rtls_source is None:
                raise BuildError("--phase fetch requires --rtls-source and does not accept --prefix")
            work_parent = REPO / ".work" / "tmp"
            work_parent.mkdir(parents=True, exist_ok=True)
            run_dir = require_work_path(
                args.run_dir
                if args.run_dir is not None
                else Path(tempfile.mkdtemp(prefix="openssl-free-fetch-", dir=work_parent))
            )
            run_dir.mkdir(parents=True, exist_ok=True)
            rtls_source, hashing_source = validate_adapter_sources(
                args.rtls_source,
                args.hashing_source,
            )
            cargo, _, _ = rust_toolchain()
            fetch_rust_inputs(run_dir, rtls_source, hashing_source, cargo)
            print(f"FETCHED no-OpenSSL Rust inputs -> {run_dir}")
            return 0

        if args.phase in {"all", "overlay"} and args.inside_sandbox:
            cargo, rustc, kache = args.cargo_bin, args.rustc_bin, args.kache_bin
            if not all(path is not None and path.is_file() for path in (cargo, rustc, kache)):
                raise BuildError("sealed Rust build tools were not provided")
        elif args.phase in {"all", "overlay"}:
            if args.rtls_source is None:
                raise BuildError(f"--phase {args.phase} requires --rtls-source")
            args.rtls_source, args.hashing_source = validate_adapter_sources(
                args.rtls_source,
                args.hashing_source,
            )
            cargo, rustc, kache = rust_toolchain()
        else:
            cargo = rustc = kache = None

        if args.inside_sandbox:
            run_dir = require_work_path(args.run_dir)
            target = native_target()
            cache_root = common_root / ".cache"
            if args.phase == "base":
                prefix = build_base(run_dir, cache_root, target, toolchain)
            elif args.phase == "all":
                prefix = build_base(run_dir, cache_root, target, toolchain)
            elif args.phase == "overlay":
                prefix = require_work_path(args.prefix)
                if not prefix.is_dir():
                    raise BuildError(f"candidate prefix does not exist: {prefix}")
                enforce_candidate_exclusions(prefix)
                verify_base_prefix(prefix, run_dir)
            else:
                raise BuildError(f"unsupported sandbox phase: {args.phase}")
            if args.phase in {"all", "overlay"}:
                if cargo is None or rustc is None or kache is None:
                    raise BuildError("Rust build tools were not passed into the sealed process")
                rtls_build, hashing_build = require_fetched_rust_inputs(run_dir)
                install_adapters(
                    prefix,
                    run_dir,
                    rtls_build,
                    hashing_build,
                    run_dir / "cargo-home",
                    cargo,
                    rustc,
                    kache,
                    target,
                    toolchain,
                    args.jobs,
                )
                prefix = relocate_candidate(
                    prefix,
                    run_dir,
                    locked,
                    toolchain,
                    cargo,
                    rustc,
                    kache,
                )
                verify_overlay_prefix(prefix, run_dir, target)
                print(f"OK relocated no-OpenSSL candidate -> {prefix}", flush=True)
            print(f"NO_OPENSSL_PREFIX={prefix}", flush=True)
            return 0

        if args.phase == "overlay":
            if args.prefix is None:
                raise BuildError("--phase overlay requires --prefix")
            prefix = require_work_path(args.prefix)
            run_dir = require_work_path(args.run_dir or prefix.parent)
            if prefix.parent != run_dir:
                raise BuildError("--phase overlay requires --prefix to be directly under --run-dir")
            if not prefix.is_dir():
                raise BuildError(f"candidate prefix does not exist: {prefix}")
        else:
            if args.prefix is not None:
                raise BuildError(f"--prefix is only valid with --phase overlay")
            work_parent = REPO / ".work" / "tmp"
            work_parent.mkdir(parents=True, exist_ok=True)
            run_dir = require_work_path(
                args.run_dir
                if args.run_dir is not None
                else Path(tempfile.mkdtemp(prefix="openssl-free-cpython-", dir=work_parent))
            )
            prefix = run_dir / "prefix"
        run_dir.mkdir(parents=True, exist_ok=True)
        if args.phase in {"all", "overlay"}:
            require_fetched_rust_inputs(run_dir, args.hashing_source)
        if not available():
            raise BuildError("sandbox-exec is unavailable")
        boundary = network_boundary(run_dir)
        print(
            f"SEAL network denied; boundary check passed: {boundary['probe']}",
            flush=True,
        )
        sealed = SealedRun(write_paths=[run_dir], home=run_dir / "home")
        env = sandbox_environment(
            run_dir,
            locked,
            cargo.parent if cargo is not None else None,
            kache.parent if kache is not None else None,
        )
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--inside-sandbox",
            "--phase",
            args.phase,
            "--run-dir",
            str(run_dir),
            "--jobs",
            str(args.jobs),
        ]
        if args.phase == "overlay":
            command.extend(("--prefix", str(prefix)))
        if args.phase in {"all", "overlay"}:
            command.extend((
                "--cargo-bin", str(cargo),
                "--rustc-bin", str(rustc),
                "--kache-bin", str(kache),
            ))
        log = run_dir / f"driver-{args.phase}.log"
        result = sealed.run(command, cwd=REPO, env=env, log=log)
        output = log.read_text() if log.exists() else ""
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        if result.returncode:
            print(f"FAIL no-OpenSSL build: sealed run exited {result.returncode}", file=sys.stderr)
            print(f"Logs: {run_dir / 'logs'}", file=sys.stderr)
            return result.returncode
        after = network_boundary(run_dir / "network-boundary-after")
        print(f"SEAL post-build network boundary passed: {after['probe']}", flush=True)
        print(f"Build output: {run_dir}")
        return 0
    except (
        BuildError,
        BootstrapError,
        InputError,
        OSError,
        PatchError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(f"FAIL no-OpenSSL build: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
