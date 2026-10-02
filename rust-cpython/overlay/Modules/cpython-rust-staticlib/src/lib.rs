#![no_std]

pub use _asyncio_rs::PyInit__asyncio_rs;
pub use _bisect_rs::PyInit__bisect_rs;
pub use _codecs_rs::PyInit__codecs_rs;
pub use _concurrent_futures_rs::PyInit__concurrent_futures_rs;
pub use _contextlib_rs::PyInit__contextlib_rs;
pub use _heapq_rs::PyInit__heapq_rs;
pub use _html_parser_rs::PyInit__html_parser_rs;
pub use _itertools_rs::PyInit__itertools_rs;
pub use _posixpath_rs::PyInit__posixpath_rs;
pub use _random_rs::PyInit__random_rs;
pub use _ssl_rs::PyInit__ssl_rs;
pub use _tempfile_rs::PyInit__tempfile_rs;

mod io;

// Static helpers exclude their standalone panic handlers. The final target
// archive owns one fatal handler; the Rust test harness owns its own runtime.
#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    unsafe { cpython_sys::Py_FatalError(c"panic in a CPython Rust helper".as_ptr()) }
}

// Prebuilt core objects retain an exception-personality reference even when
// this archive aborts on panic. No foreign exception may unwind through a Rust
// helper; preserve the platform's full callback ABI and terminate if invoked.
#[cfg(all(not(test), panic = "abort"))]
#[unsafe(no_mangle)]
unsafe extern "C" fn rust_eh_personality(
    _version: core::ffi::c_int,
    _actions: core::ffi::c_int,
    _exception_class: u64,
    _exception_object: *mut core::ffi::c_void,
    _context: *mut core::ffi::c_void,
) -> core::ffi::c_int {
    unsafe { cpython_sys::Py_FatalError(c"unexpected unwind in a CPython Rust helper".as_ptr()) }
}
