//! ASCII paragraph wrapping and shortening for `textwrap`.
//!
//! The crate is `no_std`, declares the few C-API entry points it uses, and
//! builds results straight from the argument's UTF-8 view (a stack buffer,
//! with a `PyMem` fallback, for shortening): Rust `std` and the textwrap
//! crate add hundreds of KiB of mapped image and first-call heap pages.
#![no_std]

use core::ffi::{c_char, c_void};
use core::ptr;

use cpython_binding::ffi::{
    PyErr_NoMemory, PyErr_Occurred, PyList_New, PyList_SetItem, PyLong_AsLongLong, PyMem_Free,
    PyMem_Malloc, PyMethodDef, PyObject, PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, Py_DecRef, Py_ssize_t,
};
use cpython_binding::{Exception, Module, fastcall, method_table_end, raise};

/// Borrow the UTF-8 view of a `str` argument; ASCII strings are viewed in
/// place, so no copy is made.
unsafe fn read_unicode<'a>(arg: *mut PyObject) -> Option<&'a [u8]> {
    let mut size: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(arg, &mut size) };
    if data.is_null() {
        return None;
    }
    if size < 0 {
        raise(Exception::TypeError, c"text has a negative encoded length");
        return None;
    }
    Some(unsafe { core::slice::from_raw_parts(data.cast::<u8>(), size as usize) })
}

unsafe fn read_width(arg: *mut PyObject) -> Option<usize> {
    let width = unsafe { PyLong_AsLongLong(arg) };
    if width == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return None;
    }
    if width <= 0 {
        raise(Exception::ValueError, c"width must be positive");
        return None;
    }
    Some(width as usize)
}

unsafe fn new_unicode(text: &[u8]) -> *mut PyObject {
    if text.len() > isize::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t) }
}

fn is_printable(byte: u8) -> bool {
    (b'!'..=b'~').contains(&byte)
}

fn is_ascii_space(byte: u8) -> bool {
    byte == b' ' || (b'\t'..=b'\r').contains(&byte)
}

fn is_plain_ascii_paragraph(text: &[u8], width: usize) -> bool {
    if text.is_empty()
        || text[0] == b' '
        || text[text.len() - 1] == b' '
        || text.windows(2).any(|pair| pair == b"  ")
        || !text
            .iter()
            .all(|&byte| byte == b' ' || (is_printable(byte) && byte != b'-'))
    {
        return false;
    }
    text.split(|&byte| byte == b' ').all(|word| word.len() <= width)
}

/// End of the space-delimited word that starts at `start`.
fn word_end(text: &[u8], mut start: usize) -> usize {
    while start < text.len() && text[start] != b' ' {
        start += 1;
    }
    start
}

/// End of the greedy line that starts at `start`: words joined by single
/// spaces while the line stays within `width`, so every line is a slice of
/// `text`. The first word is known to fit.
fn line_end(text: &[u8], start: usize, width: usize) -> usize {
    let mut end = word_end(text, start);
    while end < text.len() {
        let next_end = word_end(text, end + 1);
        if next_end - start > width {
            break;
        }
        end = next_end;
    }
    end
}

unsafe fn wrap_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 2 {
        raise(Exception::TypeError, c"wrap() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(text) = (unsafe { read_unicode(*args) }) else {
        return ptr::null_mut();
    };
    let Some(width) = (unsafe { read_width(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if !is_plain_ascii_paragraph(text, width) {
        raise(Exception::ValueError, c"text is outside the supported wrapping domain");
        return ptr::null_mut();
    }

    let mut count = 0_usize;
    let mut start = 0;
    loop {
        let end = line_end(text, start, width);
        count += 1;
        if end == text.len() {
            break;
        }
        start = end + 1;
    }
    let result = unsafe { PyList_New(count as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }
    start = 0;
    for index in 0..count {
        let end = line_end(text, start, width);
        let item = unsafe { new_unicode(&text[start..end]) };
        if item.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyList_SetItem(result, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        start = end + 1;
    }
    result
}

/// Next ASCII-whitespace-delimited word at or after `pos`, as `(start, end)`.
fn next_word(text: &[u8], mut pos: usize) -> Option<(usize, usize)> {
    while pos < text.len() && is_ascii_space(text[pos]) {
        pos += 1;
    }
    if pos == text.len() {
        return None;
    }
    let start = pos;
    while pos < text.len() && !is_ascii_space(text[pos]) {
        pos += 1;
    }
    Some((start, pos))
}

/// The default-option ASCII domain: printable text without hyphens, a
/// placeholder of whitespace and printable bytes that fits after its leading
/// whitespace is trimmed, and no word wider than `width`.
fn shorten_domain_ok(text: &[u8], width: usize, placeholder: &[u8]) -> bool {
    if !text
        .iter()
        .all(|&byte| is_ascii_space(byte) || (is_printable(byte) && byte != b'-'))
        || !placeholder
            .iter()
            .all(|&byte| is_ascii_space(byte) || is_printable(byte))
        || placeholder.len() - leading_space(placeholder) > width
    {
        return false;
    }
    let mut pos = 0;
    while let Some((start, end)) = next_word(text, pos) {
        if end - start > width {
            return false;
        }
        pos = end;
    }
    true
}

fn leading_space(text: &[u8]) -> usize {
    let mut skip = 0;
    while skip < text.len() && is_ascii_space(text[skip]) {
        skip += 1;
    }
    skip
}

const STACK_BYTES: usize = 1024;

unsafe fn shorten_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 3 {
        raise(Exception::TypeError, c"shorten() takes exactly three arguments");
        return ptr::null_mut();
    }
    let Some(text) = (unsafe { read_unicode(*args) }) else {
        return ptr::null_mut();
    };
    let Some(width) = (unsafe { read_width(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    let Some(placeholder) = (unsafe { read_unicode(*args.add(2)) }) else {
        return ptr::null_mut();
    };
    if !shorten_domain_ok(text, width, placeholder) {
        raise(Exception::ValueError, c"text is outside the supported shortening domain");
        return ptr::null_mut();
    }

    // Length of the whitespace-normalized text.
    let mut total = 0_usize;
    let mut pos = 0;
    while let Some((start, end)) = next_word(text, pos) {
        total += (end - start) + usize::from(total != 0);
        pos = end;
    }
    if total <= width {
        return unsafe { join_words(text, usize::MAX, b"") };
    }

    // Longest word prefix whose length plus the placeholder fits in `width`
    // (prefix lengths grow with each word, so stop once one exceeds `width`).
    let mut kept = 0_usize;
    let mut count = 0_usize;
    let mut length = 0_usize;
    pos = 0;
    while let Some((start, end)) = next_word(text, pos) {
        length += (end - start) + usize::from(count != 0);
        if length > width {
            break;
        }
        count += 1;
        if length.saturating_add(placeholder.len()) <= width {
            kept = count;
        }
        pos = end;
    }
    if kept == 0 {
        return unsafe { new_unicode(&placeholder[leading_space(placeholder)..]) };
    }
    unsafe { join_words(text, kept, placeholder) }
}

/// Join the first `limit` words of `text` with single spaces and append
/// `suffix`, building the result in a stack buffer (heap when it is large).
unsafe fn join_words(text: &[u8], limit: usize, suffix: &[u8]) -> *mut PyObject {
    let mut size = suffix.len();
    let mut words = 0_usize;
    let mut pos = 0;
    while words < limit {
        let Some((start, end)) = next_word(text, pos) else {
            break;
        };
        size += (end - start) + usize::from(words != 0);
        words += 1;
        pos = end;
    }

    let mut stack = [0_u8; STACK_BYTES];
    let mut heap: *mut u8 = ptr::null_mut();
    let buffer: *mut u8 = if size <= STACK_BYTES {
        stack.as_mut_ptr()
    } else {
        heap = unsafe { PyMem_Malloc(size) }.cast::<u8>();
        if heap.is_null() {
            unsafe { PyErr_NoMemory() };
            return ptr::null_mut();
        }
        heap
    };

    let mut used = 0_usize;
    pos = 0;
    for written in 0..words {
        let Some((start, end)) = next_word(text, pos) else {
            break;
        };
        if written != 0 {
            unsafe { *buffer.add(used) = b' ' };
            used += 1;
        }
        unsafe { ptr::copy_nonoverlapping(text.as_ptr().add(start), buffer.add(used), end - start) };
        used += end - start;
        pos = end;
    }
    unsafe { ptr::copy_nonoverlapping(suffix.as_ptr(), buffer.add(used), suffix.len()) };
    used += suffix.len();

    let result = unsafe { new_unicode(core::slice::from_raw_parts(buffer, used)) };
    if !heap.is_null() {
        unsafe { PyMem_Free(heap.cast::<c_void>()) };
    }
    result
}

unsafe extern "C" fn wrap(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { wrap_impl(args, nargs) }
}

unsafe extern "C" fn shorten(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { shorten_impl(args, nargs) }
}

static METHODS: [PyMethodDef; 3] = [
    fastcall(
        c"wrap",
        wrap,
        c"Wrap a supported ASCII paragraph.",
    ),
    fastcall(
        c"shorten",
        shorten,
        c"Shorten supported ASCII text.",
    ),
    method_table_end(),
];

static MODULE: Module =
    Module::new(c"_textwrap_rs", c"Rust text wrapping helpers.", &METHODS);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__textwrap_rs() -> *mut PyObject {
    MODULE.init()
}
