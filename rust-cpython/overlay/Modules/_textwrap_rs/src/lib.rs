use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyList_New;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyLong_AsLongLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::Py_ssize_t;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;

fn set_type_error(message: &'static std::ffi::CStr) {
    unsafe {
        PyErr_SetString(PyExc_TypeError, message.as_ptr());
    }
}

fn set_value_error(message: &'static std::ffi::CStr) {
    unsafe {
        PyErr_SetString(PyExc_ValueError, message.as_ptr());
    }
}

unsafe fn read_unicode(arg: *mut PyObject) -> Option<String> {
    let mut size: Py_ssize_t = 0;
    let ptr = unsafe { PyUnicode_AsUTF8AndSize(arg, &mut size) };
    if ptr.is_null() {
        return None;
    }
    if size < 0 {
        set_type_error(c"text has a negative encoded length");
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(ptr.cast::<u8>(), size as usize) };
    // PyUnicode_AsUTF8AndSize returns a valid UTF-8 view of the Python string.
    let text = unsafe { std::str::from_utf8_unchecked(bytes) };
    Some(text.to_owned())
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

fn is_plain_ascii_paragraph(text: &str, width: usize) -> bool {
    if text.is_empty()
        || text.contains('-')
        || text.starts_with(' ')
        || text.ends_with(' ')
        || text.as_bytes().windows(2).any(|pair| pair == b"  ")
        || !text
            .bytes()
            .all(|byte| byte == b' ' || (b'!'..=b'~').contains(&byte))
    {
        return false;
    }
    text.split(' ').all(|word| word.len() <= width)
}

fn wrap_paragraph(text: &str, width: usize) -> Vec<String> {
    let mut wrapped = text.to_owned();
    textwrap::fill_inplace(&mut wrapped, width);
    wrapped.split('\n').map(str::to_owned).collect()
}

fn shorten_paragraph(text: &str, width: usize, placeholder: &str) -> String {
    let words = text.split_ascii_whitespace().collect::<Vec<_>>();
    let normalized = words.join(" ");
    if normalized.len() <= width {
        return normalized;
    }

    let mut kept = Vec::new();
    let mut kept_len = 0;
    for word in words {
        let candidate_len = if kept.is_empty() {
            word.len()
        } else {
            kept_len + 1 + word.len()
        };
        if candidate_len <= width {
            kept.push(word);
            kept_len = candidate_len;
        } else {
            break;
        }
    }

    while !kept.is_empty() {
        let prefix = kept.join(" ");
        if prefix.len() + placeholder.len() <= width {
            return prefix + placeholder;
        }
        kept.pop();
    }
    placeholder.trim_start().to_owned()
}

unsafe fn new_unicode(text: &str) -> *mut PyObject {
    if text.len() > isize::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t) }
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
    if !is_plain_ascii_paragraph(&text, width) {
        set_value_error(c"text is outside the supported wrapping domain");
        return ptr::null_mut();
    }

    let lines = wrap_paragraph(&text, width);
    if lines.len() > isize::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let result = unsafe { PyList_New(lines.len() as Py_ssize_t) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for (index, line) in lines.iter().enumerate() {
        let item = unsafe { new_unicode(line) };
        if item.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyList_SetItem(result, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

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
        || text.contains('-')
        || !placeholder
            .bytes()
            .all(|byte| byte.is_ascii_whitespace() || (b'!'..=b'~').contains(&byte))
    {
        set_value_error(c"text is outside the supported shortening domain");
        return ptr::null_mut();
    }

    let result = shorten_paragraph(&text, width, &placeholder);
    unsafe { new_unicode(&result) }
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

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _TEXTWRAP_RS_MODULE_METHODS: [PyMethodDef; 3] = {
    [
        PyMethodDef {
            ml_name: c"wrap".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer {
                PyCFunctionFast: wrap,
            },
            ml_flags: METH_FASTCALL,
            ml_doc: c"Wrap a supported ASCII paragraph.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"shorten".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer {
                PyCFunctionFast: shorten,
            },
            ml_flags: METH_FASTCALL,
            ml_doc: c"Shorten supported ASCII text.".as_ptr() as *mut c_char,
        },
        PyMethodDef::zeroed(),
    ]
};

pub static _TEXTWRAP_RS_MODULE: ModuleDef = {
    ModuleDef {
        ffi: UnsafeCell::new(PyModuleDef {
            m_base: PyModuleDef_HEAD_INIT,
            m_name: c"_textwrap_rs".as_ptr() as *mut _,
            m_doc: c"Rust text wrapping helpers.".as_ptr() as *mut _,
            m_size: 0,
            m_methods: &_TEXTWRAP_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
            m_slots: ptr::null_mut(),
            m_traverse: None,
            m_clear: Some(_textwrap_rs_clear),
            m_free: Some(_textwrap_rs_free),
        }),
    }
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__textwrap_rs() -> *mut PyObject {
    _TEXTWRAP_RS_MODULE.init_multi_phase()
}
