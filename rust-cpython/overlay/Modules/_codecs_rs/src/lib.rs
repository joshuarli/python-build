use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, METH_O, PyBytes_AsStringAndSize, PyBytes_FromStringAndSize, Py_DecRef,
    PyErr_Clear, PyErr_SetString, PyExc_TypeError, PyLong_FromSsize_t, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init, Py_NewRef,
    PyObject, PyObject_IsTrue, PyTuple_New, PyTuple_SetItem, PyUnicode_AsUTF8AndSize,
    PyUnicode_FromStringAndSize, Py_ssize_t, _Py_NoneStruct,
};

const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

fn none() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe extern "C" fn encode_utf8(
    _module: *mut PyObject,
    input: *mut PyObject,
) -> *mut PyObject {
    let mut length = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(input, &mut length) };
    if data.is_null() {
        // Surrogates and other unsupported inputs retain CPython's codec errors.
        unsafe { PyErr_Clear() };
        return none();
    }
    unsafe { PyBytes_FromStringAndSize(data, length) }
}

unsafe extern "C" fn decode_utf8(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"decode_utf8 expects data and final".as_ptr()) };
        return ptr::null_mut();
    }
    let mut data = ptr::null_mut();
    let mut length = 0;
    if unsafe { PyBytes_AsStringAndSize(*args, &mut data, &mut length) } != 0 {
        return ptr::null_mut();
    }
    let final_flag = unsafe { PyObject_IsTrue(*args.add(1)) };
    if final_flag < 0 {
        return ptr::null_mut();
    }
    let bytes = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    let consumed = match std::str::from_utf8(bytes) {
        Ok(_) => bytes.len(),
        Err(error) if final_flag == 0 && error.error_len().is_none() => error.valid_up_to(),
        Err(_) => return none(),
    };
    let decoded = unsafe {
        PyUnicode_FromStringAndSize(data, consumed as Py_ssize_t)
    };
    if decoded.is_null() {
        return ptr::null_mut();
    }
    let count = unsafe { PyLong_FromSsize_t(consumed as Py_ssize_t) };
    if count.is_null() {
        unsafe { Py_DecRef(decoded) };
        return ptr::null_mut();
    }
    let pair = unsafe { PyTuple_New(2) };
    if pair.is_null() {
        unsafe { Py_DecRef(decoded); Py_DecRef(count) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(pair, 0, decoded) } != 0 {
        unsafe { Py_DecRef(count); Py_DecRef(pair) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(pair, 1, count) } != 0 {
        unsafe { Py_DecRef(pair) };
        return ptr::null_mut();
    }
    pair
}

#[repr(C)]
struct ModuleSlot {
    slot: c_int,
    value: *mut c_void,
}

unsafe impl Sync for ModuleSlot {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

unsafe impl Sync for ModuleDef {}

static METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"encode_utf8".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: encode_utf8 },
        ml_flags: METH_O,
        ml_doc: c"Encode valid UTF-8 text; return None for CPython fallback.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decode_utf8".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decode_utf8 },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Decode valid UTF-8 chunks; return None for CPython fallback.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static SLOTS: [ModuleSlot; 2] = [
    ModuleSlot { slot: PY_MOD_MULTIPLE_INTERPRETERS, value: 2usize as *mut c_void },
    ModuleSlot { slot: 0, value: ptr::null_mut() },
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_codecs_rs".as_ptr() as *mut _,
        m_doc: c"Rust UTF-8 conversion for registered codecs.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: METHODS.as_ptr() as *mut _,
        m_slots: SLOTS.as_ptr() as *mut _,
        m_traverse: None,
        m_clear: None,
        m_free: None,
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__codecs_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.ffi.get()) }
}
