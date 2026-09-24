//! Exact-byte percent quoting kernel for the guarded urllib.parse experiment.
//!
//! The C caller supplies live CPython byte buffers and an output allocation of
//! at least three bytes per input byte. No Python API is called from Rust.

const HEX: &[u8; 16] = b"0123456789ABCDEF";

#[unsafe(no_mangle)]
pub unsafe extern "C" fn quote_ascii(
    input: *const u8,
    input_len: usize,
    safe: *const u8,
    safe_len: usize,
    output: *mut u8,
    capacity: usize,
) -> isize {
    if input.is_null() || safe.is_null() || output.is_null() || input_len > isize::MAX as usize / 3 {
        return -1;
    }
    let input = unsafe { std::slice::from_raw_parts(input, input_len) };
    let safe = unsafe { std::slice::from_raw_parts(safe, safe_len) };
    let output = unsafe { std::slice::from_raw_parts_mut(output, capacity) };
    let mut allowed = [false; 128];
    for c in b'A'..=b'Z' { allowed[c as usize] = true; }
    for c in b'a'..=b'z' { allowed[c as usize] = true; }
    for c in b'0'..=b'9' { allowed[c as usize] = true; }
    for c in b"_.-~" { allowed[*c as usize] = true; }
    for c in safe { if *c < 128 { allowed[*c as usize] = true; } }

    let mut written = 0;
    for &c in input {
        let literal = c < 128 && allowed[c as usize];
        let width = if literal { 1 } else { 3 };
        if output.len() - written < width { return -1; }
        if literal {
            output[written] = c;
        } else {
            output[written] = b'%';
            output[written + 1] = HEX[(c >> 4) as usize];
            output[written + 2] = HEX[(c & 15) as usize];
        }
        written += width;
    }
    written as isize
}
