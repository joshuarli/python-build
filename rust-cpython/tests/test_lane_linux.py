from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

LANE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(LANE.parent), str(LANE)]

import lane_linux  # noqa: E402
from buildsys.inputs import Cache, Input, InputError  # noqa: E402
from buildsys.llvm import LINUX_X86_64_LAYOUT, MACOS_AARCH64_LAYOUT  # noqa: E402


class ToolchainLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.toolchain = lane_linux.load_linux_toolchain(
            LANE / "linux-toolchain.lock.json", Path("/cache")
        )

    def test_llvm_matches_the_macos_release_and_source_commit(self) -> None:
        mac = json.loads((LANE.parent / "bootstrap.lock.json").read_text())["macos_toolchain"]
        mac_provenance = mac["llvm"]["archive"]["provenance"]
        self.assertEqual(self.toolchain.llvm_version, mac["llvm"]["version"])
        self.assertEqual(self.toolchain.llvm_release_tag, mac_provenance["release_tag"])
        self.assertEqual(self.toolchain.llvm_source_commit, mac_provenance["source_commit"])
        self.assertEqual(self.toolchain.llvm_workflow, mac_provenance["workflow"])
        self.assertEqual(
            self.toolchain.llvm_prefix,
            Path("/cache/llvm/toolchains") / f"23.1.2-{self.toolchain.llvm_archive_sha256}",
        )

    def test_inputs_are_digest_pinned_for_the_linux_target(self) -> None:
        for item in (self.toolchain.llvm_input(), self.toolchain.llvm_attestation_input(),
                     self.toolchain.icu_input()):
            self.assertEqual(item.target, lane_linux.TARGET)
            self.assertRegex(item.sha256, r"^[0-9a-f]{64}$")
            self.assertIsNotNone(item.size)

    def test_environment_scrubs_search_paths_and_leaves_linker_to_clang(self) -> None:
        with patch.dict("os.environ", {"LD_PRELOAD": "x", "LD": "/usr/bin/ld", "RUSTFLAGS": "-C x"}):
            env = self.toolchain.env()
        self.assertNotIn("LD_PRELOAD", env)
        self.assertNotIn("LD", env)
        self.assertNotIn("RUSTFLAGS", env)
        self.assertEqual(env["CC"], "/cache/llvm/toolchains/"
                         f"23.1.2-{self.toolchain.llvm_archive_sha256}/bin/clang")


class LayoutTests(unittest.TestCase):
    def test_linux_layout_takes_only_the_needed_runtimes(self) -> None:
        runtime = "lib/clang/23/lib/x86_64-unknown-linux-gnu/"
        self.assertTrue(LINUX_X86_64_LAYOUT.selected("bin/ld.lld"))
        self.assertTrue(LINUX_X86_64_LAYOUT.selected(runtime + "libclang_rt.profile.a"))
        self.assertTrue(LINUX_X86_64_LAYOUT.selected("lib/clang/23/include/stdint.h"))
        self.assertFalse(LINUX_X86_64_LAYOUT.selected(runtime + "libclang_rt.asan.a"))
        self.assertFalse(LINUX_X86_64_LAYOUT.selected("bin/clangd"))
        self.assertFalse(LINUX_X86_64_LAYOUT.selected("lib/libLTO.so"))

    def test_macos_layout_is_unchanged(self) -> None:
        self.assertTrue(MACOS_AARCH64_LAYOUT.selected("lib/libLTO.dylib"))
        self.assertTrue(MACOS_AARCH64_LAYOUT.selected("lib/clang/23/lib/darwin/libclang_rt.osx.a"))
        self.assertFalse(MACOS_AARCH64_LAYOUT.selected("bin/ld.lld"))


class SealedRunTests(unittest.TestCase):
    def test_commands_run_in_fresh_user_and_network_namespaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sealed = lane_linux.SealedRun(write_paths=[Path(temporary)])
            with patch.object(lane_linux.subprocess, "run") as run:
                sealed.run(["true"], cwd=Path(temporary), env={})
        argv = run.call_args.args[0]
        self.assertEqual(argv[:5], [lane_linux.UNSHARE, "--user", "--map-root-user", "--net", "--"])
        self.assertEqual(argv[5:], ["true"])

    def test_sealed_environment_drops_proxy_settings(self) -> None:
        env = lane_linux.SealedRun().environment({"HTTPS_PROXY": "http://proxy", "CC": "clang"})
        self.assertNotIn("HTTPS_PROXY", env)
        self.assertEqual(env["CC"], "clang")


class FetchSourceTests(unittest.TestCase):
    def _input(self, url: str) -> Input:
        return Input(name="archive", version="1", url=url, sha256="0" * 64, size=1,
                     role="build-source", target=lane_linux.TARGET)

    def test_only_codeload_archives_are_reconstructed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Cache(Path(temporary))
            with patch.object(cache, "fetch", side_effect=OSError("blocked")):
                with self.assertRaisesRegex(InputError, "download failed"):
                    lane_linux.fetch_source(cache, self._input("https://example.com/a.tar.gz"))

    def test_reconstruction_must_match_the_pinned_digest(self) -> None:
        url = "https://codeload.github.com/owner/repo/tar.gz/" + "a" * 40
        with tempfile.TemporaryDirectory() as temporary:
            cache = Cache(Path(temporary))
            fake = Path(temporary) / "fake.tar.gz"
            fake.write_bytes(b"x")
            with (
                patch.object(cache, "fetch", side_effect=OSError("blocked")),
                patch.object(lane_linux, "_git_archive", return_value=fake),
            ):
                with self.assertRaisesRegex(InputError, "digest"):
                    lane_linux.fetch_source(cache, self._input(url))


class ElfParsingTests(unittest.TestCase):
    def test_dynamic_section_parsing(self) -> None:
        sample = (
            "  0x0000000000000001 (NEEDED)             Shared library: [libpython3.16.so.1.0]\n"
            "  0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]\n"
            "  0x000000000000001d (RUNPATH)            Library runpath: [$ORIGIN/../lib]\n"
        )
        with patch.object(lane_linux, "_readelf", return_value=sample):
            dynamic = lane_linux.elf_dynamic(None, Path("python3.16"))  # type: ignore[arg-type]
        self.assertEqual(dynamic, {"needed": ["libpython3.16.so.1.0", "libc.so.6"],
                                   "rpaths": ["$ORIGIN/../lib"]})


if __name__ == "__main__":
    unittest.main()
