"""Core conversion preserves all accepted heap algorithms and C API tables."""

import hashlib
from pathlib import Path
import unittest


PREFIX = '''#![no_std]

// The standalone extension aborts if an internal invariant panics. A shared
// carrier supplies its own handler, so statically linked modules omit this.
#[cfg(not(feature = "static-module"))]
unsafe extern "C" {
    fn abort() -> !;
}

#[cfg(not(feature = "static-module"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

'''
ACCEPTED_SOURCE_SHA256 = "77124f1f7b9e562df80941f5356197a6541245830326f97cfd18bed4cf8aca12"


class CoreSourceContractTests(unittest.TestCase):
    def test_only_runtime_prefix_and_namespace_are_changed(self):
        source = (Path(__file__).resolve().parents[1] / "src/lib.rs").read_text()
        self.assertTrue(source.startswith(PREFIX))
        body = source.removeprefix(PREFIX)
        self.assertNotIn("std::", body)
        self.assertEqual(body.count("core::"), 6)
        restored = body.replace("core::", "std::").encode()
        self.assertEqual(hashlib.sha256(restored).hexdigest(), ACCEPTED_SOURCE_SHA256)

    def test_static_feature_adds_no_dependency_or_default_activation(self):
        manifest = (Path(__file__).resolve().parents[1] / "Cargo.toml").read_text()
        self.assertIn('[features]\nstatic-module = []\n\n', manifest)
        self.assertNotIn('default =', manifest)
        self.assertIn('cpython-sys = { path = "../cpython-sys" }', manifest)


if __name__ == '__main__':
    unittest.main()
