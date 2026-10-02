use core::ffi::{c_int, c_void};
use core::ptr;
use core::slice;

const SEEN_CR: c_int = 1;
const SEEN_LF: c_int = 2;
const SEEN_CRLF: c_int = 4;

// All pointers originate in live CPython buffers held by the caller. The C
// boundary checks lengths and keeps those buffers alive across each call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn _PyRust_io_buffer_transfer(
    dst: *mut c_void,
    dst_len: isize,
    src: *const c_void,
    src_len: isize,
) -> isize {
    if dst_len <= 0 || src_len <= 0 {
        return 0;
    }
    let count = dst_len.min(src_len) as usize;
    unsafe { ptr::copy_nonoverlapping(src.cast::<u8>(), dst.cast::<u8>(), count) };
    count as isize
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn _PyRust_io_line_length(data: *const c_void, len: isize) -> isize {
    if len <= 0 {
        return -1;
    }
    let bytes = unsafe { slice::from_raw_parts(data.cast::<u8>(), len as usize) };
    bytes.iter().position(|&byte| byte == b'\n').map_or(-1, |i| i as isize + 1)
}

unsafe fn read_codepoint(data: *const c_void, kind: c_int, index: usize) -> u32 {
    match kind {
        1 => unsafe { *data.cast::<u8>().add(index) as u32 },
        2 => unsafe { *data.cast::<u16>().add(index) as u32 },
        4 => unsafe { *data.cast::<u32>().add(index) },
        _ => unreachable!("CPython Unicode kind must be 1, 2, or 4"),
    }
}

unsafe fn write_codepoint(data: *mut c_void, kind: c_int, index: usize, value: u32) {
    match kind {
        1 => unsafe { *data.cast::<u8>().add(index) = value as u8 },
        2 => unsafe { *data.cast::<u16>().add(index) = value as u16 },
        4 => unsafe { *data.cast::<u32>().add(index) = value },
        _ => unreachable!("CPython Unicode kind must be 1, 2, or 4"),
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn _PyRust_io_text_newline_flags(
    data: *const c_void,
    kind: c_int,
    len: isize,
) -> c_int {
    let mut flags = 0;
    for index in 0..len as usize {
        match unsafe { read_codepoint(data, kind, index) } {
            10 => flags |= SEEN_LF,
            13 => flags |= SEEN_CR,
            _ => {}
        }
        if flags == (SEEN_CR | SEEN_LF) {
            break;
        }
    }
    flags
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn _PyRust_io_translate_newlines(
    src: *const c_void,
    dst: *mut c_void,
    kind: c_int,
    len: isize,
    seen: *mut c_int,
) -> isize {
    let mut input = 0usize;
    let mut output = 0usize;
    let mut newlines = 0;
    while input < len as usize {
        let ch = unsafe { read_codepoint(src, kind, input) };
        input += 1;
        if ch == 13 {
            if input < len as usize && unsafe { read_codepoint(src, kind, input) } == 10 {
                input += 1;
                newlines |= SEEN_CRLF;
            } else {
                newlines |= SEEN_CR;
            }
            unsafe { write_codepoint(dst, kind, output, 10) };
        } else {
            if ch == 10 {
                newlines |= SEEN_LF;
            }
            unsafe { write_codepoint(dst, kind, output, ch) };
        }
        output += 1;
    }
    unsafe { *seen |= newlines };
    output as isize
}
