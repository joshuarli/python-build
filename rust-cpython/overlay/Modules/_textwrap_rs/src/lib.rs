//! ASCII paragraph wrapping and shortening for `textwrap`.
//!
//! The crate is `no_std`, declares the few C-API entry points it uses, and
//! builds results straight from the argument's UTF-8 view (a stack buffer,
//! with a `PyMem` fallback, for shortening): Rust `std` and the textwrap
//! crate add hundreds of KiB of mapped image and first-call heap pages.
#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{CStr, c_char, c_int, c_void};
use core::ptr;

type Py_ssize_t = isize;

#[repr(C)]
struct PyObject {
    ob_refcnt: Py_ssize_t,
    ob_type: *mut PyTypeObject,
}

#[repr(C)]
struct PyTypeObject {
    _opaque: [u8; 0],
}

#[repr(C)]
union PyMethodDefFuncPointer {
    PyCFunctionFast: unsafe extern "C" fn(
        slf: *mut PyObject,
        args: *mut *mut PyObject,
        nargs: Py_ssize_t,
    ) -> *mut PyObject,
    void: *mut c_void,
}

#[repr(C)]
struct PyMethodDef {
    ml_name: *mut c_char,
    ml_meth: PyMethodDefFuncPointer,
    ml_flags: c_int,
    ml_doc: *mut c_char,
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
struct PyModuleDef_Base {
    ob_base: PyObject,
    m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    m_index: Py_ssize_t,
    m_copy: *mut PyObject,
}

#[repr(C)]
struct PyModuleDef {
    m_base: PyModuleDef_Base,
    m_name: *const c_char,
    m_doc: *const c_char,
    m_size: Py_ssize_t,
    m_methods: *mut PyMethodDef,
    m_slots: *mut c_void,
    m_traverse: Option<unsafe extern "C" fn(*mut PyObject, *mut c_void, *mut c_void) -> c_int>,
    m_clear: Option<extern "C" fn(*mut PyObject) -> c_int>,
    m_free: Option<extern "C" fn(*mut c_void)>,
}

const METH_FASTCALL: c_int = 0x0080;
/// `_Py_IMMORTAL_INITIAL_REFCNT | ((_Py_STATICALLY_ALLOCATED_FLAG |
/// _Py_IMMORTAL_FLAGS) << 48)` for the 64-bit GIL-enabled build.
const STATIC_IMMORTAL_REFCNT: Py_ssize_t = (3_isize << 30) | (5_isize << 48);

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    static mut PyExc_TypeError: *mut PyObject;
    static mut PyExc_ValueError: *mut PyObject;

    fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    fn PyErr_NoMemory() -> *mut PyObject;
    fn PyErr_Occurred() -> *mut PyObject;
    fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    fn PyList_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyList_SetItem(list: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
    fn PyLong_AsLongLong(object: *mut PyObject) -> i64;
    fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t) -> *const c_char;
    fn PyUnicode_FromStringAndSize(text: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    fn Py_DecRef(object: *mut PyObject);
    fn PyMem_Malloc(size: usize) -> *mut c_void;
    fn PyMem_Free(pointer: *mut c_void);
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

fn set_type_error(message: &'static CStr) {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
}

fn set_value_error(message: &'static CStr) {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) };
}

/// Borrow the UTF-8 view of a `str` argument; ASCII strings are viewed in
/// place, so no copy is made.
unsafe fn read_unicode<'a>(arg: *mut PyObject) -> Option<&'a [u8]> {
    let mut size: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(arg, &mut size) };
    if data.is_null() {
        return None;
    }
    if size < 0 {
        set_type_error(c"text has a negative encoded length");
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
        set_value_error(c"width must be positive");
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
    matches!(byte, b' ' | b'\t' | b'\n' | 0x0c | b'\r')
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
        set_type_error(c"wrap() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(text) = (unsafe { read_unicode(*args) }) else {
        return ptr::null_mut();
    };
    let Some(width) = (unsafe { read_width(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if !is_plain_ascii_paragraph(text, width) {
        set_value_error(c"text is outside the supported wrapping domain");
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

const STACK_BYTES: usize = 1024;

unsafe fn shorten_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 3 {
        set_type_error(c"shorten() takes exactly three arguments");
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
    if !text.is_ascii()
        || text.contains(&b'-')
        || !placeholder
            .iter()
            .all(|&byte| is_ascii_space(byte) || is_printable(byte))
    {
        set_value_error(c"text is outside the supported shortening domain");
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
        let mut skip = 0;
        while skip < placeholder.len() && is_ascii_space(placeholder[skip]) {
            skip += 1;
        }
        return unsafe { new_unicode(&placeholder[skip..]) };
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

pub extern "C" fn _textwrap_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _textwrap_rs_free(_obj: *mut c_void) {}

struct ModuleDef(UnsafeCell<PyModuleDef>);

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.0.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"wrap".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: wrap },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Wrap a supported ASCII paragraph.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"shorten".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: shorten },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Shorten supported ASCII text.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: ptr::null_mut(),
        ml_meth: PyMethodDefFuncPointer { void: ptr::null_mut() },
        ml_flags: 0,
        ml_doc: ptr::null_mut(),
    },
];

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_Base {
        ob_base: PyObject {
            ob_refcnt: STATIC_IMMORTAL_REFCNT,
            ob_type: ptr::null_mut(),
        },
        m_init: None,
        m_index: 0,
        m_copy: ptr::null_mut(),
    },
    m_name: c"_textwrap_rs".as_ptr() as *mut _,
    m_doc: c"Rust text wrapping helpers.".as_ptr() as *mut _,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut _,
    m_slots: ptr::null_mut(),
    m_traverse: None,
    m_clear: Some(_textwrap_rs_clear),
    m_free: Some(_textwrap_rs_free),
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__textwrap_rs() -> *mut PyObject {
    MODULE.init()
}
