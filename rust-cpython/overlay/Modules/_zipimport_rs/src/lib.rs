use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int};
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyDict_Contains;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyLong_AsLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::Py_NewRef;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::PyTuple_GetItem;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyTuple_Size;
use cpython_sys::PyUnicode_Concat;
use cpython_sys::Py_buffer;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;
use flate2::{Decompress, FlushDecompress, Status};

const PYBUF_SIMPLE: c_int = 0;
const OUTPUT_CHUNK_SIZE: usize = 64 * 1024;

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        unsafe {
            if PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) != 0 {
                return Err(());
            }
            Ok(Self {
                view: view.assume_init(),
            })
        }
    }

    fn copy_bytes(&self) -> Option<Vec<u8>> {
        if self.view.len < 0 {
            unsafe { PyErr_SetString(cpython_sys::PyExc_ValueError, c"buffer length cannot be negative".as_ptr()) };
            return None;
        }
        if self.view.len == 0 {
            return Some(Vec::new());
        }
        let bytes = unsafe {
            slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize)
        };
        Some(bytes.to_vec())
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

fn set_type_error(message: &'static std::ffi::CStr) {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) }
}

unsafe fn read_buffer(argument: *mut PyObject) -> Option<Vec<u8>> {
    let buffer = match BorrowedBuffer::from_object(argument) {
        Ok(buffer) => buffer,
        Err(()) => return None,
    };
    buffer.copy_bytes()
}

unsafe fn bytes_from_slice(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe {
        PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t)
    }
}

unsafe extern "C" fn module_matches(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        set_type_error(c"module_matches() takes exactly three arguments");
        return ptr::null_mut();
    }
    let files = unsafe { *args };
    let path = unsafe { *args.add(1) };
    let search_order = unsafe { *args.add(2) };
    let count = unsafe { PyTuple_Size(search_order) };
    if count < 0 {
        return ptr::null_mut();
    }

    let result = unsafe { PyTuple_New(count) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for index in 0..count {
        let entry = unsafe { PyTuple_GetItem(search_order, index) };
        if entry.is_null() {
            unsafe { cpython_sys::Py_DecRef(result) };
            return ptr::null_mut();
        }
        let suffix = unsafe { PyTuple_GetItem(entry, 0) };
        if suffix.is_null() {
            unsafe { cpython_sys::Py_DecRef(result) };
            return ptr::null_mut();
        }
        let candidate = unsafe { PyUnicode_Concat(path, suffix) };
        if candidate.is_null() {
            unsafe { cpython_sys::Py_DecRef(result) };
            return ptr::null_mut();
        }
        let found = unsafe { PyDict_Contains(files, candidate) };
        unsafe { cpython_sys::Py_DecRef(candidate) };
        if found < 0 {
            unsafe { cpython_sys::Py_DecRef(result) };
            return ptr::null_mut();
        }
        let matched = unsafe { PyBool_FromLong(if found == 0 { 0 } else { 1 }) };
        if matched.is_null() {
            unsafe { cpython_sys::Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(result, index, matched) } != 0 {
            unsafe {
                cpython_sys::Py_DecRef(matched);
                cpython_sys::Py_DecRef(result);
            }
            return ptr::null_mut();
        }
    }

    result
}

unsafe extern "C" fn is_directory(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        set_type_error(c"is_directory() takes exactly three arguments");
        return ptr::null_mut();
    }
    let files = unsafe { *args };
    let path = unsafe { *args.add(1) };
    let separator = unsafe { *args.add(2) };
    let candidate = unsafe { PyUnicode_Concat(path, separator) };
    if candidate.is_null() {
        return ptr::null_mut();
    }
    let found = unsafe { PyDict_Contains(files, candidate) };
    unsafe { cpython_sys::Py_DecRef(candidate) };
    if found < 0 {
        return ptr::null_mut();
    }
    unsafe { PyBool_FromLong(if found == 0 { 0 } else { 1 }) }
}

unsafe extern "C" fn decompress_zip_data(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"decompress_zip_data() takes exactly two arguments");
        return ptr::null_mut();
    }
    let compression = unsafe { PyLong_AsLong(*args) };
    if !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if compression != 0 && compression != 8 {
        return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
    }
    let Some(raw_data) = (unsafe { read_buffer(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if compression == 0 {
        return unsafe { bytes_from_slice(&raw_data) };
    }

    let mut decompressor = Decompress::new(false);
    let mut consumed = 0usize;
    let mut output = Vec::new();
    loop {
        let mut chunk = [0u8; OUTPUT_CHUNK_SIZE];
        let before_in = decompressor.total_in();
        let before_out = decompressor.total_out();
        let status = match decompressor.decompress(
            &raw_data[consumed..],
            &mut chunk,
            FlushDecompress::Finish,
        ) {
            Ok(status) => status,
            Err(_) => return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
        };
        let used = (decompressor.total_in() - before_in) as usize;
        let written = (decompressor.total_out() - before_out) as usize;
        consumed += used;
        if output.try_reserve(written).is_err() {
            unsafe { PyErr_NoMemory() };
            return ptr::null_mut();
        }
        output.extend_from_slice(&chunk[..written]);

        if status == Status::StreamEnd {
            return unsafe { bytes_from_slice(&output) };
        }
        if used == 0 && written == 0 {
            return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
        }
    }
}

pub extern "C" fn _zipimport_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _zipimport_rs_free(_object: *mut std::ffi::c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static MODULE_METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"module_matches".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: module_matches },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Match ZIP import candidates against an archive directory.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompress_zip_data".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompress_zip_data },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Extract stored or DEFLATE-compressed ZIP module data.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"is_directory".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: is_directory },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Check whether an archive contains a directory path.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_zipimport_rs".as_ptr() as *mut _,
        m_doc: c"Rust ZIP import discovery and payload extraction.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_zipimport_rs_clear),
        m_free: Some(_zipimport_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub unsafe extern "C" fn PyInit__zipimport_rs() -> *mut PyObject {
    MODULE.init()
}
