//! Rust option matching over borrowed Python strings.
//! Results use Python allocations directly; no Rust heap or runtime is retained.
#![no_std]

use core::ffi::c_char;
use core::ptr;

use cpython_binding::ffi::{
    PyErr_NoMemory, PyErr_SetString, PyExc_TypeError, PyList_Append, PyList_New, PyMethodDef,
    PyObject, PyObject_IsTrue, PyTuple_GetItem, PyTuple_New, PyTuple_SetItem, PyTuple_Size,
    PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, Py_DecRef, Py_NewRef, Py_ssize_t,
    _Py_NoneStruct,
};
use cpython_binding::{Module, fastcall, method_table_end};
use cpython_binding::module::PER_INTERPRETER_GIL;

// Arguments and configured option strings stay alive for this synchronous scan.
// Borrowing their UTF-8 avoids Rust heap allocations and allocator retention.
unsafe fn read_unicode<'a>(object: *mut PyObject) -> Option<&'a str> {
    let mut length: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if data.is_null() || length < 0 {
        return None;
    }
    let bytes = unsafe { core::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    Some(unsafe { core::str::from_utf8_unchecked(bytes) })
}

unsafe fn new_unicode(text: &str) -> *mut PyObject {
    let Ok(length) = Py_ssize_t::try_from(text.len()) else {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    };
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), length) }
}

unsafe fn new_candidate(
    option: *mut PyObject,
    separator: Option<&str>,
    explicit_argument: Option<&str>,
) -> *mut PyObject {
    let result = unsafe { PyTuple_New(3) };
    if result.is_null() {
        return ptr::null_mut();
    }

    let option = unsafe { Py_NewRef(option) };
    if option.is_null() {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(result, 0, option) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }

    let separator = match separator {
        Some(separator) => unsafe { new_unicode(separator) },
        None => unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
    };
    if separator.is_null() {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(result, 1, separator) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }

    let explicit_argument = match explicit_argument {
        Some(argument) => unsafe { new_unicode(argument) },
        None => unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
    };
    if explicit_argument.is_null() {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(result, 2, explicit_argument) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }

    result
}

unsafe fn append_candidate(
    result: *mut PyObject,
    option: *mut PyObject,
    separator: Option<&str>,
    explicit_argument: Option<&str>,
) -> bool {
    let item = unsafe { new_candidate(option, separator, explicit_argument) };
    if item.is_null() {
        return false;
    }
    let appended = unsafe { PyList_Append(result, item) } >= 0;
    unsafe { Py_DecRef(item) };
    appended
}

unsafe fn scan_option(
    argument: &str,
    options: *mut PyObject,
    count: Py_ssize_t,
    allow_abbrev: bool,
    result: *mut PyObject,
) -> bool {
    if !argument.starts_with('-') {
        return true;
    }
    // Exact options take precedence over both attached values and abbreviations.
    for index in 0..count {
        let object = unsafe { PyTuple_GetItem(options, index) };
        let Some(option) = (unsafe { read_unicode(object) }) else {
            return false;
        };
        if option == argument {
            return unsafe { append_candidate(result, object, None, None) };
        }
    }
    let (prefix, separator, explicit_argument) = match argument.split_once('=') {
        Some((prefix, value)) => (prefix, Some("="), Some(value)),
        None => (argument, None, None),
    };
    if separator.is_some() {
        for index in 0..count {
            let object = unsafe { PyTuple_GetItem(options, index) };
            let Some(option) = (unsafe { read_unicode(object) }) else {
                return false;
            };
            if option == prefix {
                return unsafe { append_candidate(result, object, separator, explicit_argument) };
            }
        }
    }
    if argument.starts_with("--") {
        if allow_abbrev {
            for index in 0..count {
                let object = unsafe { PyTuple_GetItem(options, index) };
                let Some(option) = (unsafe { read_unicode(object) }) else {
                    return false;
                };
                if option.starts_with(prefix)
                    && !unsafe { append_candidate(result, object, separator, explicit_argument) }
                {
                    return false;
                }
            }
        }
        return true;
    }
    let Some(flag) = argument[1..].chars().next() else {
        return true;
    };
    let short_end = 1 + flag.len_utf8();
    let short_option = &argument[..short_end];
    let short_value = &argument[short_end..];
    for index in 0..count {
        let object = unsafe { PyTuple_GetItem(options, index) };
        let Some(option) = (unsafe { read_unicode(object) }) else {
            return false;
        };
        let appended = if option == short_option {
            unsafe { append_candidate(result, object, Some(""), Some(short_value)) }
        } else if allow_abbrev && option.starts_with(prefix) {
            unsafe { append_candidate(result, object, separator, explicit_argument) }
        } else {
            true
        };
        if !appended {
            return false;
        }
    }
    true
}

unsafe extern "C" fn option_candidates(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"option_candidates() takes exactly three arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }
    let Some(argument) = (unsafe { read_unicode(*args) }) else {
        return ptr::null_mut();
    };
    let options = unsafe { *args.add(1) };
    let count = unsafe { PyTuple_Size(options) };
    if count < 0 {
        return ptr::null_mut();
    }
    // Validate every option before truth conversion or matching, including
    // options after an exact match, so malformed tuples keep raising errors.
    for index in 0..count {
        let object = unsafe { PyTuple_GetItem(options, index) };
        if object.is_null() || unsafe { read_unicode(object) }.is_none() {
            return ptr::null_mut();
        }
    }
    let allow_abbrev = unsafe { PyObject_IsTrue(*args.add(2)) };
    if allow_abbrev < 0 {
        return ptr::null_mut();
    }
    let result = unsafe { PyList_New(0) };
    if result.is_null() {
        return ptr::null_mut();
    }
    if !unsafe { scan_option(argument, options, count, allow_abbrev != 0, result) } {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    result
}

static MODULE_METHODS: [PyMethodDef; 2] = [
    fastcall(
        c"option_candidates",
        option_candidates,
        c"Find configured option tokens using Rust option matching",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_argparse_rs",
    c"Rust option-token scanner used by argparse",
    &MODULE_METHODS,
).with_slots(&PER_INTERPRETER_GIL);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__argparse_rs() -> *mut PyObject {
    MODULE.init()
}
