use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBytes_AsString;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::Py_ssize_t;
use form_urlencoded::parse as parse_form_query;
use percent_encoding::{percent_decode, percent_encode_byte};

unsafe extern "C" {
    fn PyBytes_Size(object: *mut PyObject) -> Py_ssize_t;
    fn PyList_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyList_SetItem(list: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
    fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, item: *mut PyObject) -> c_int;
}

unsafe fn bytes_argument<'a>(object: *mut PyObject) -> Result<&'a [u8], ()> {
    let length = unsafe { PyBytes_Size(object) };
    if length < 0 {
        return Err(());
    }
    let data = unsafe { PyBytes_AsString(object) };
    if data.is_null() {
        return Err(());
    }
    Ok(unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) })
}

fn set_argument_error(message: &'static std::ffi::CStr) {
    unsafe {
        PyErr_SetString(PyExc_TypeError, message.as_ptr());
    }
}

unsafe fn bytes_object(value: &[u8]) -> *mut PyObject {
    unsafe { PyBytes_FromStringAndSize(value.as_ptr().cast(), value.len() as Py_ssize_t) }
}

fn make_pairs_object(pairs: &[(Vec<u8>, Vec<u8>)]) -> *mut PyObject {
    let list = unsafe { PyList_New(pairs.len() as Py_ssize_t) };
    if list.is_null() {
        return ptr::null_mut();
    }

    for (index, (name, value)) in pairs.iter().enumerate() {
        let tuple = unsafe { PyTuple_New(2) };
        if tuple.is_null() {
            unsafe { Py_DecRef(list) };
            return ptr::null_mut();
        }

        let name_object = unsafe { bytes_object(name) };
        if name_object.is_null() {
            unsafe {
                Py_DecRef(tuple);
                Py_DecRef(list);
            }
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, 0, name_object) } != 0 {
            unsafe {
                Py_DecRef(tuple);
                Py_DecRef(list);
            }
            return ptr::null_mut();
        }

        let value_object = unsafe { bytes_object(value) };
        if value_object.is_null() {
            unsafe {
                Py_DecRef(tuple);
                Py_DecRef(list);
            }
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, 1, value_object) } != 0 {
            unsafe {
                Py_DecRef(tuple);
                Py_DecRef(list);
            }
            return ptr::null_mut();
        }

        if unsafe { PyList_SetItem(list, index as Py_ssize_t, tuple) } != 0 {
            unsafe { Py_DecRef(list) };
            return ptr::null_mut();
        }
    }
    list
}

unsafe extern "C" fn quote_from_bytes(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_argument_error(c"quote_from_bytes() takes exactly two arguments");
        return ptr::null_mut();
    }
    let input = match unsafe { bytes_argument(*args) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let safe = match unsafe { bytes_argument(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };

    let mut encoded = String::with_capacity(input.len());
    for byte in input {
        let always_safe = byte.is_ascii_alphanumeric() || matches!(*byte, b'_' | b'.' | b'-' | b'~');
        if always_safe || safe.contains(byte) {
            encoded.push(char::from(*byte));
        } else {
            encoded.push_str(percent_encode_byte(*byte));
        }
    }
    unsafe { bytes_object(encoded.as_bytes()) }
}

unsafe extern "C" fn unquote_to_bytes(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_argument_error(c"unquote_to_bytes() takes exactly one argument");
        return ptr::null_mut();
    }
    let input = match unsafe { bytes_argument(*args) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let decoded = percent_decode(input).collect::<Vec<_>>();
    unsafe { bytes_object(&decoded) }
}

fn split_query(query: &[u8], separator: &[u8]) -> Vec<(Vec<u8>, Vec<u8>)> {
    if separator.is_empty() {
        return Vec::new();
    }
    let mut pairs = Vec::new();
    let mut remaining = query;
    loop {
        let boundary = remaining
            .windows(separator.len())
            .position(|window| window == separator);
        let (field, rest) = match boundary {
            Some(index) => (&remaining[..index], Some(&remaining[index + separator.len()..])),
            None => (remaining, None),
        };
        if !field.is_empty() {
            let equals = field.iter().position(|byte| *byte == b'=');
            let (name, value) = match equals {
                Some(index) => (&field[..index], &field[index + 1..]),
                None => (field, &[][..]),
            };
            pairs.push((name.to_vec(), value.to_vec()));
        }
        match rest {
            Some(next) => remaining = next,
            None => break,
        }
    }
    pairs
}

unsafe extern "C" fn parse_qsl(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_argument_error(c"parse_qsl() takes exactly two arguments");
        return ptr::null_mut();
    }
    let query = match unsafe { bytes_argument(*args) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let separator = match unsafe { bytes_argument(*args.add(1)) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    make_pairs_object(&split_query(query, separator))
}

unsafe extern "C" fn parse_qsl_utf8(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_argument_error(c"parse_qsl_utf8() takes exactly one argument");
        return ptr::null_mut();
    }
    let query = match unsafe { bytes_argument(*args) } {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let pairs = parse_form_query(query)
        .map(|(name, value)| (name.into_owned().into_bytes(), value.into_owned().into_bytes()))
        .collect::<Vec<_>>();
    make_pairs_object(&pairs)
}

extern "C" fn _urllib_parse_rs_clear(_module: *mut PyObject) -> c_int {
    0
}

extern "C" fn _urllib_parse_rs_free(_module: *mut std::ffi::c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static MODULE_METHODS: [PyMethodDef; 5] = [
    PyMethodDef {
        ml_name: c"quote_from_bytes".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: quote_from_bytes,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Percent-encode bytes with a dynamic safe set".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"unquote_to_bytes".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: unquote_to_bytes,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Decode valid percent escapes without interpreting text".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"parse_qsl".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_qsl,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Split query fields and retain their percent-encoded byte pairs".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"parse_qsl_utf8".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_qsl_utf8,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse UTF-8 form query fields".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_urllib_parse_rs".as_ptr() as *mut _,
        m_doc: c"Rust percent-encoding and query parsing for urllib.parse".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_urllib_parse_rs_clear),
        m_free: Some(_urllib_parse_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__urllib_parse_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
