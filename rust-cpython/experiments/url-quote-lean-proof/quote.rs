//! Exact-byte percent quoting for the guarded urllib.parse overlay.
//!
//! A null output requests the required length. The C caller then allocates an
//! exact-size ASCII Unicode object and calls again to fill it. Exact CPython
//! bytes inputs stay owned by the caller throughout both passes.
#![no_std]

use core::panic::PanicInfo;

unsafe extern "C" {
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &PanicInfo<'_>) -> ! {
    // A Rust panic must never unwind across the CPython C boundary. Normal
    // bounds and capacity failures return -1; this handles only broken Rust
    // invariants, for which continuing with a partly filled object is unsafe.
    unsafe { abort() }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn quote_ascii(
    input: *const u8,
    input_len: usize,
    safe: *const u8,
    safe_len: usize,
    output: *mut u8,
    capacity: usize,
) -> isize {
    if input.is_null() || safe.is_null() || input_len > isize::MAX as usize / 3 {
        return -1;
    }
    if output.is_null() && capacity != 0 {
        return -1;
    }

    let mut allowed = [0_u8; 128];
    for c in b'A'..=b'Z' { allowed[c as usize] = 1; }
    for c in b'a'..=b'z' { allowed[c as usize] = 1; }
    for c in b'0'..=b'9' { allowed[c as usize] = 1; }
    for c in b"_.-~" { allowed[*c as usize] = 1; }
    for i in 0..safe_len {
        // C supplies a live exact-bytes buffer of safe_len bytes.
        let c = unsafe { *safe.add(i) };
        if c < 128 { allowed[c as usize] = 1; }
    }

    let hex = b"0123456789ABCDEF";
    let mut written = 0_usize;
    for i in 0..input_len {
        // C supplies a live exact-bytes buffer of input_len bytes.
        let c = unsafe { *input.add(i) };
        let literal = c < 128 && allowed[c as usize] != 0;
        let width = if literal { 1 } else { 3 };
        if !output.is_null() && (written > capacity || capacity - written < width) {
            return -1;
        }
        if !output.is_null() {
            // The capacity check above proves each write is within the
            // PyUnicode_New(result_len, 127) one-byte payload.
            unsafe {
                if literal {
                    *output.add(written) = c;
                } else {
                    *output.add(written) = b'%';
                    *output.add(written + 1) = hex[(c >> 4) as usize];
                    *output.add(written + 2) = hex[(c & 15) as usize];
                }
            }
        }
        written += width;
    }
    written as isize
}
