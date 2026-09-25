use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::Py_buffer;
use cpython_sys::Py_ssize_t;
use uuid::Uuid;

const PYBUF_SIMPLE: c_int = 0;

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    fn from_object(object: &PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        let buffer = unsafe {
            if PyObject_GetBuffer(object.as_raw(), view.as_mut_ptr(), PYBUF_SIMPLE) != 0 {
                return Err(());
            }
            Self {
                view: view.assume_init(),
            }
        };
        Ok(buffer)
    }

    fn as_slice(&self) -> &[u8] {
        if self.view.len <= 0 {
            return &[];
        }
        unsafe {
            slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize)
        }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe {
            PyBuffer_Release(&mut self.view);
        }
    }
}

fn fail(exception: *mut PyObject, message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe {
        PyErr_SetString(exception, message.as_ptr());
    }
    ptr::null_mut()
}

fn type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { fail(PyExc_TypeError, message) }
}

fn value_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { fail(PyExc_ValueError, message) }
}

unsafe fn argument<'a>(args: *mut *mut PyObject, index: usize) -> &'a PyObject {
    unsafe { &**args.add(index) }
}

fn read_uuid(object: &PyObject) -> Result<Uuid, ()> {
    let buffer = BorrowedBuffer::from_object(object)?;
    match Uuid::from_slice(buffer.as_slice()) {
        Ok(value) => Ok(value),
        Err(_) => {
            unsafe {
                PyErr_SetString(
                    PyExc_ValueError,
                    c"UUID data must contain exactly 16 bytes".as_ptr(),
                );
            }
            Err(())
        }
    }
}

fn return_bytes(bytes: &[u8]) -> *mut PyObject {
    unsafe { PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

/// # Safety
/// `args` contains `nargs` valid Python object pointers supplied by CPython.
pub unsafe extern "C" fn parse_hex(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"parse_hex() takes exactly one argument");
    }
    let text = match BorrowedBuffer::from_object(unsafe { argument(args, 0) }) {
        Ok(buffer) => match std::str::from_utf8(buffer.as_slice()) {
            Ok(text) => text.to_owned(),
            Err(_) => return value_error(c"invalid UUID hexadecimal data"),
        },
        Err(()) => return ptr::null_mut(),
    };
    match Uuid::parse_str(&text) {
        Ok(value) => return_bytes(value.as_bytes()),
        Err(_) => value_error(c"invalid UUID hexadecimal data"),
    }
}

/// # Safety
/// `args` contains `nargs` valid Python object pointers supplied by CPython.
pub unsafe extern "C" fn normalize(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"normalize() takes exactly one argument");
    }
    match read_uuid(unsafe { argument(args, 0) }) {
        Ok(value) => return_bytes(value.as_bytes()),
        Err(()) => ptr::null_mut(),
    }
}

/// # Safety
/// `args` contains `nargs` valid Python object pointers supplied by CPython.
pub unsafe extern "C" fn set_version(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"set_version() takes exactly two arguments");
    }
    let version = match BorrowedBuffer::from_object(unsafe { argument(args, 1) }) {
        Ok(buffer) => match buffer.as_slice() {
            [version @ 1..=8] => *version,
            _ => return value_error(c"illegal UUID version number"),
        },
        Err(()) => return ptr::null_mut(),
    };
    let mut value = match read_uuid(unsafe { argument(args, 0) }) {
        Ok(value) => *value.as_bytes(),
        Err(()) => return ptr::null_mut(),
    };
    value[6] = (value[6] & 0x0f) | (version << 4);
    value[8] = (value[8] & 0x3f) | 0x80;
    return_bytes(&value)
}

fn name_uuid(args: *mut *mut PyObject, nargs: Py_ssize_t, version: u8) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"name UUID generator takes exactly one argument");
    }
    let buffer = match BorrowedBuffer::from_object(unsafe { argument(args, 0) }) {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let data = buffer.as_slice();
    if data.len() < 16 {
        return value_error(c"namespace UUID data must contain 16 bytes");
    }
    let namespace = match Uuid::from_slice(&data[..16]) {
        Ok(value) => value,
        Err(_) => return value_error(c"namespace UUID data must contain 16 bytes"),
    };
    let value = match version {
        3 => Uuid::new_v3(&namespace, &data[16..]),
        5 => Uuid::new_v5(&namespace, &data[16..]),
        _ => unreachable!(),
    };
    return_bytes(value.as_bytes())
}

/// # Safety
/// `args` contains `nargs` valid Python object pointers supplied by CPython.
pub unsafe extern "C" fn uuid3(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    name_uuid(args, nargs, 3)
}

/// # Safety
/// `args` contains `nargs` valid Python object pointers supplied by CPython.
pub unsafe extern "C" fn uuid4(
    _module: *mut PyObject,
    _args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 0 {
        return type_error(c"uuid4() takes no arguments");
    }
    return_bytes(Uuid::new_v4().as_bytes())
}

/// # Safety
/// `args` contains `nargs` valid Python object pointers supplied by CPython.
pub unsafe extern "C" fn uuid5(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    name_uuid(args, nargs, 5)
}

fn formatted(args: *mut *mut PyObject, nargs: Py_ssize_t, simple: bool) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"format() takes exactly one argument");
    }
    match read_uuid(unsafe { argument(args, 0) }) {
        Ok(value) => {
            let text = if simple {
                value.simple().to_string()
            } else {
                value.hyphenated().to_string()
            };
            return_bytes(text.as_bytes())
        }
        Err(()) => ptr::null_mut(),
    }
}

/// # Safety
/// `args` contains `nargs` valid Python object pointers supplied by CPython.
pub unsafe extern "C" fn format(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    formatted(args, nargs, false)
}

/// # Safety
/// `args` contains `nargs` valid Python object pointers supplied by CPython.
pub unsafe extern "C" fn format_hex(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    formatted(args, nargs, true)
}

pub extern "C" fn _uuid_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _uuid_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _UUID_RS_MODULE_METHODS: [PyMethodDef; 9] = [
    PyMethodDef {
        ml_name: c"parse_hex".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: parse_hex },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse 32 hexadecimal UUID digits".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"normalize".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: normalize },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Validate and normalize a 16-byte UUID".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"set_version".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: set_version },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Set the UUID variant and version bits".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"uuid3".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: uuid3 },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Generate a version 3 name UUID".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"uuid4".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: uuid4 },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Generate a random version 4 UUID".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"uuid5".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: uuid5 },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Generate a version 5 name UUID".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"format".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: format },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Format a UUID using canonical hyphenated lowercase text".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"format_hex".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: format_hex },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Format a UUID as lowercase hexadecimal text".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _UUID_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_uuid_rs".as_ptr() as *mut _,
        m_doc: c"Rust UUID parsing, formatting, and generation".as_ptr() as *mut _,
        m_size: 0,
        m_methods: _UUID_RS_MODULE_METHODS.as_ptr() as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_uuid_rs_clear),
        m_free: Some(_uuid_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__uuid_rs() -> *mut PyObject {
    _UUID_RS_MODULE.init_multi_phase()
}
