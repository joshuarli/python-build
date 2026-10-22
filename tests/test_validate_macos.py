from __future__ import annotations

import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from buildsys.macho import (
    CPU_TYPE_ARM64,
    LC_BUILD_VERSION,
    LC_ID_DYLIB,
    LC_LOAD_DYLIB,
    LC_RPATH,
    MH_DYLIB,
    MH_EXECUTE,
)
from buildsys.product import PRODUCT
from buildsys.targets import TARGETS
from buildsys.validate_macos import macho_checks, run_validation, version_and_abi


def _command(command: int, payload: bytes) -> bytes:
    return struct.pack("<II", command, 8 + len(payload)) + payload


def _padded(value: str) -> bytes:
    raw = value.encode() + b"\x00"
    return raw + b"\x00" * (-len(raw) % 8)


def _dylib_command(command: int, value: str) -> bytes:
    return _command(command, struct.pack("<IIII", 24, 0, 0x10000, 0x10000) + _padded(value))


def _rpath_command(value: str) -> bytes:
    return _command(LC_RPATH, struct.pack("<I", 12) + _padded(value))


def _build_version_command(platform: int = 1, minos: tuple[int, int] = (26, 0)) -> bytes:
    packed = (minos[0] << 16) | (minos[1] << 8)
    return _command(LC_BUILD_VERSION, struct.pack("<IIII", platform, packed, packed, 0))


def _image(commands: list[bytes], filetype: int) -> bytes:
    body = b"".join(commands)
    header = struct.pack(
        "<IiiIIIII", 0xFEEDFACF, CPU_TYPE_ARM64, 0, filetype,
        len(commands), len(body), 0x00200000, 0,
    )
    return header + body


class MachOValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.install = Path(self.temporary.name) / "python"
        self.bin = self.install / "bin"
        self.lib = self.install / "lib"
        self.bin.mkdir(parents=True)
        self.lib.mkdir()
        self.python = PRODUCT.interpreter(self.install)
        self.libpython = self.lib / f"lib{PRODUCT.shared_library_stem}.dylib"
        self._write_images()
        self.signature = patch(
            "buildsys.validate_macos.macho.signature_status",
            return_value=(True, ""),
        )
        self.signature.start()
        self.addCleanup(self.signature.stop)

    def _write_images(
        self,
        *,
        platform: int = 1,
        minos: tuple[int, int] = (26, 0),
        dependency: str | None = None,
        rpath: str = "@loader_path/../lib",
    ) -> None:
        executable_commands = [_build_version_command(platform, minos)]
        if dependency is None:
            dependency = f"@rpath/{self.libpython.name}"
        executable_commands.extend((
            _dylib_command(LC_LOAD_DYLIB, dependency),
            _dylib_command(LC_LOAD_DYLIB, "/usr/lib/libSystem.B.dylib"),
            _rpath_command(rpath),
        ))
        self.python.write_bytes(_image(executable_commands, MH_EXECUTE))
        self.libpython.write_bytes(_image([
            _build_version_command(platform, minos),
            _dylib_command(LC_ID_DYLIB, f"@rpath/{self.libpython.name}"),
            _dylib_command(LC_LOAD_DYLIB, "/usr/lib/libSystem.B.dylib"),
            _rpath_command("@loader_path"),
        ], MH_DYLIB))

    def _report(self) -> dict:
        return macho_checks(self.install, TARGETS["aarch64-apple-darwin"])

    def test_valid_product_images_have_resolved_paths_and_platform(self) -> None:
        report = self._report()

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["image_count"], 2)
        self.assertEqual(report["missing_product_images"], [])

    def test_non_macos_platform_fails(self) -> None:
        self._write_images(platform=2)

        report = self._report()

        self.assertFalse(report["ok"])
        self.assertTrue(report["platform_mismatches"])

    def test_wrong_minimum_os_fails(self) -> None:
        self._write_images(minos=(25, 0))

        report = self._report()

        self.assertFalse(report["ok"])
        self.assertTrue(report["minos_mismatches"])

    def test_unexpected_dependency_fails(self) -> None:
        self._write_images(dependency="/opt/homebrew/lib/libpython.dylib")

        report = self._report()

        self.assertFalse(report["ok"])
        self.assertTrue(report["unexpected_dependencies"])

    def test_unresolved_rpath_dependency_fails(self) -> None:
        self._write_images(dependency="@rpath/libmissing.dylib")

        report = self._report()

        self.assertFalse(report["ok"])
        self.assertTrue(report["unresolved_dependencies"])

    def test_external_runpath_fails(self) -> None:
        self._write_images(rpath="@loader_path/../../../opt/homebrew/lib")

        report = self._report()

        self.assertFalse(report["ok"])
        self.assertTrue(report["unexpected_rpaths"])

    def test_rpath_dependency_symlink_cannot_escape_install(self) -> None:
        external = Path(self.temporary.name) / "external.dylib"
        external.write_bytes(_image([_build_version_command()], MH_DYLIB))
        self.libpython.unlink()
        self.libpython.symlink_to(external)

        report = self._report()

        self.assertFalse(report["ok"])
        self.assertTrue(report["unresolved_dependencies"])
        self.assertTrue(report["missing_product_images"])

    def test_universal_image_fails_closed(self) -> None:
        (self.lib / "universal.dylib").write_bytes(b"\xca\xfe\xba\xbe" + b"\x00" * 32)

        report = self._report()

        self.assertFalse(report["ok"])
        self.assertEqual(report["universal_images"], ["lib/universal.dylib"])

    def test_missing_product_images_fail(self) -> None:
        self.python.unlink()

        report = self._report()

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["missing_product_images"],
            [str(PRODUCT.interpreter(self.install).relative_to(self.install))],
        )


class ProductVersionValidationTests(unittest.TestCase):
    def test_stale_cpython_version_and_abi_fail(self) -> None:
        stale_version = [
            PRODUCT.version[0], PRODUCT.version[1] - 1, PRODUCT.version[2]
        ]
        stale_abi = f"cpython-{PRODUCT.version[0]}{PRODUCT.version[1] - 1}"
        info = {
            "version": stale_version,
            "version_string": ".".join(str(part) for part in stale_version),
            "platform": "darwin",
            "machine": "arm64",
            "implementation": "cpython",
            "cache_tag": stale_abi,
            "python_platform": (
                f"macosx-{TARGETS['aarch64-apple-darwin'].deployment_target}-arm64"
            ),
            "soabi": f"{stale_abi}-darwin",
            "ext_suffix": f".{stale_abi}-darwin.so",
            "gil_enabled": True,
            "free_threaded": False,
            "lto": True,
            "pgo": True,
            "tail_call": False,
            "shared_libpython": True,
            "INSTSONAME": f"lib{PRODUCT.shared_library_stem}.dylib",
        }
        outputs = (
            json.dumps(info),
            "|",
        )
        completed = [
            subprocess.CompletedProcess([], 0, output, "") for output in outputs
        ]
        with patch(
            "buildsys.validate_macos.run_product_process",
            side_effect=completed,
        ):
            report = version_and_abi(
                Path("/install/bin") / PRODUCT.interpreter_name,
                TARGETS["aarch64-apple-darwin"],
                cwd=Path("/work"),
            )

        self.assertFalse(report["ok"])
        self.assertFalse(report["version_ok"])
        self.assertFalse(report["abi_ok"])
        self.assertEqual(report["expected_version"], list(PRODUCT.version))
        self.assertTrue(report["shared_library_ok"])

    def test_wrong_shared_libpython_name_fails(self) -> None:
        info = {
            "version": list(PRODUCT.version),
            "version_string": PRODUCT.version_string,
            "platform": "darwin",
            "machine": "arm64",
            "implementation": "cpython",
            "cache_tag": PRODUCT.abi_tag.replace("cp", "cpython-"),
            "python_platform": "macosx-26.0-arm64",
            "soabi": f"cpython-{PRODUCT.abi_tag[2:]}-darwin",
            "ext_suffix": f".cpython-{PRODUCT.abi_tag[2:]}-darwin.so",
            "gil_enabled": True,
            "free_threaded": False,
            "lto": True,
            "pgo": True,
            "tail_call": False,
            "shared_libpython": True,
            "INSTSONAME": (
                f"libpython{PRODUCT.version[0]}.{PRODUCT.version[1] - 1}.dylib"
            ),
        }
        completed = [
            subprocess.CompletedProcess([], 0, json.dumps(info), ""),
            subprocess.CompletedProcess([], 0, "|", ""),
        ]
        with patch(
            "buildsys.validate_macos.run_product_process",
            side_effect=completed,
        ):
            report = version_and_abi(
                Path("/install/bin") / PRODUCT.interpreter_name,
                TARGETS["aarch64-apple-darwin"],
                cwd=Path("/work"),
            )

        self.assertFalse(report["ok"])
        self.assertFalse(report["shared_library_ok"])
        self.assertEqual(
            report["expected_instsoname"],
            f"lib{PRODUCT.shared_library_stem}.dylib",
        )

    def test_missing_interpreter_still_produces_mandatory_failed_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = run_validation(
                root,
                root / "validation",
                TARGETS["aarch64-apple-darwin"],
            )

        self.assertFalse(report["ok"])
        self.assertFalse(report["aggregate"]["ok"])
        self.assertIn("version_and_abi", report["aggregate"]["failed"])
        self.assertEqual(
            report["aggregate"]["required_check_count"],
            report["aggregate"]["check_count"],
        )


if __name__ == "__main__":
    unittest.main()
