use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int};
use std::mem::{self, MaybeUninit};
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyBytes_AsString;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyBytes_Type;
use cpython_sys::PyDict_Contains;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyLong_AsLong;
use cpython_sys::PyLong_AsSsize_t;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_NewRef;
use cpython_sys::Py_TYPE;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::PyTuple_GetItem;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyTuple_Size;
use cpython_sys::PyUnicode_Concat;
use cpython_sys::Py_buffer;
use cpython_sys::Py_ssize_t;
use cpython_sys::_PyBytes_Resize;
use cpython_sys::_Py_NoneStruct;
use libz_rs_sys::{
    Z_BUF_ERROR, Z_FINISH, Z_MEM_ERROR, Z_NO_FLUSH, Z_OK, Z_STREAM_END, inflate, inflateEnd,
    inflateInit2_, z_stream, zlibVersion,
};

const PYBUF_SIMPLE: c_int = 0;

/// A borrowed `Py_buffer` over the caller's object; zlib reads it in place.
struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    fn from_object(object: *mut PyObject) -> Option<Self> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        unsafe {
            if PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) != 0 {
                return None;
            }
            Some(Self { view: view.assume_init() })
        }
    }

    fn bytes(&self) -> &[u8] {
        if self.view.len <= 0 {
            return &[];
        }
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
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


/// One-shot raw inflate of `input` into a new `bytes`, sized from `hint` (the
/// archive's recorded uncompressed size) and grown if the stream is longer.
/// `None` (no exception set) means the stream is invalid or truncated.
unsafe fn inflate_raw(input: &[u8], hint: usize) -> Result<Option<*mut PyObject>, ()> {
    let mut z = Box::new(z_stream::default());
    let init = unsafe {
        inflateInit2_(&mut *z, -15, zlibVersion(), mem::size_of::<z_stream>() as c_int)
    };
    if init == Z_MEM_ERROR {
        unsafe { PyErr_NoMemory() };
        return Err(());
    }
    if init != Z_OK {
        return Ok(None);
    }
    let mut cap = hint.max(1);
    let mut object = unsafe { PyBytes_FromStringAndSize(ptr::null(), cap as Py_ssize_t) };
    if object.is_null() {
        unsafe { inflateEnd(&mut *z) };
        return Err(());
    }
    let mut len = 0usize;
    let mut offset = 0usize;
    let outcome = loop {
        let chunk = (input.len() - offset).min(u32::MAX as usize);
        z.next_in = unsafe { input.as_ptr().add(offset) };
        z.avail_in = chunk as u32;
        let last = offset + chunk == input.len();
        let mut end = false;
        let mut failed = false;
        loop {
            if len == cap {
                let Some(bigger) = cap.checked_mul(2).filter(|&c| c <= Py_ssize_t::MAX as usize)
                else {
                    unsafe { PyErr_NoMemory() };
                    unsafe { inflateEnd(&mut *z) };
                    unsafe { Py_DecRef(object) };
                    return Err(());
                };
                if unsafe { _PyBytes_Resize(&mut object, bigger as Py_ssize_t) } != 0 {
                    unsafe { inflateEnd(&mut *z) };
                    return Err(());
                }
                cap = bigger;
            }
            let room = (cap - len).min(u32::MAX as usize);
            z.next_out = unsafe { PyBytes_AsString(object).cast::<u8>().add(len) };
            z.avail_out = room as u32;
            let err = unsafe { inflate(&mut *z, if last { Z_FINISH } else { Z_NO_FLUSH }) };
            len += room - z.avail_out as usize;
            match err {
                Z_STREAM_END => {
                    end = true;
                    break;
                }
                Z_OK | Z_BUF_ERROR => {
                    if z.avail_out != 0 {
                        // Input exhausted (or stuck) without finishing.
                        failed = last;
                        break;
                    }
                }
                Z_MEM_ERROR => {
                    unsafe { PyErr_NoMemory() };
                    unsafe { inflateEnd(&mut *z) };
                    unsafe { Py_DecRef(object) };
                    return Err(());
                }
                _ => {
                    failed = true;
                    break;
                }
            }
        }
        if end {
            break true;
        }
        if failed || last {
            break false;
        }
        offset += chunk;
    };
    unsafe { inflateEnd(&mut *z) };
    if !outcome {
        unsafe { Py_DecRef(object) };
        return Ok(None);
    }
    if len != cap && unsafe { _PyBytes_Resize(&mut object, len as Py_ssize_t) } != 0 {
        return Err(());
    }
    Ok(Some(object))
}

unsafe extern "C" fn decompress_zip_data(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !(2..=3).contains(&nargs) {
        set_type_error(c"decompress_zip_data() takes two or three arguments");
        return ptr::null_mut();
    }
    let compression = unsafe { PyLong_AsLong(*args) };
    if !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if compression != 0 && compression != 8 {
        return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
    }
    let hint = if nargs == 3 {
        let value = unsafe { PyLong_AsSsize_t(*args.add(2)) };
        if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        value.max(0) as usize
    } else {
        0
    };
    let raw = unsafe { *args.add(1) };
    if compression == 0 {
        // Stored data is already the payload: hand back the bytes object.
        if unsafe { Py_TYPE(raw) } == ptr::addr_of_mut!(PyBytes_Type) {
            return unsafe { Py_NewRef(raw) };
        }
        let Some(input) = BorrowedBuffer::from_object(raw) else {
            return ptr::null_mut();
        };
        return unsafe { bytes_from_slice(input.bytes()) };
    }
    let Some(input) = BorrowedBuffer::from_object(raw) else {
        return ptr::null_mut();
    };
    let input = input.bytes();
    // DEFLATE cannot expand more than 1032:1, so a larger recorded size is bogus.
    let ceiling = input.len().saturating_mul(1032).saturating_add(64);
    let hint = if hint == 0 { input.len().saturating_mul(4) } else { hint };
    match unsafe { inflate_raw(input, hint.clamp(1, ceiling)) } {
        Ok(Some(object)) => object,
        Ok(None) => unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
        Err(()) => ptr::null_mut(),
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
