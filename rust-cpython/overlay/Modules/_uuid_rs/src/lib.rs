//! UUID algorithms use borrowed inputs and fixed formatting buffers, keeping
//! Rust's allocator and standard-library runtime out of the extension image.
#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::mem::MaybeUninit;
use core::ptr;
use core::slice;
use uuid::Uuid;

type Py_ssize_t = isize;

#[repr(C)]
pub struct PyObject {
    ob_refcnt: Py_ssize_t,
    ob_type: *mut PyTypeObject,
}

#[repr(C)]
pub struct PyTypeObject {
    _opaque: [u8; 0],
}

#[repr(C)]
pub union PyMethodDefFuncPointer {
    PyCFunctionFast: unsafe extern "C" fn(
        slf: *mut PyObject,
        args: *mut *mut PyObject,
        nargs: Py_ssize_t,
    ) -> *mut PyObject,
    void: *mut c_void,
}

#[repr(C)]
pub struct PyMethodDef {
    ml_name: *mut c_char,
    ml_meth: PyMethodDefFuncPointer,
    ml_flags: c_int,
    ml_doc: *mut c_char,
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
pub struct PyModuleDef_Base {
    ob_base: PyObject,
    m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    m_index: Py_ssize_t,
    m_copy: *mut PyObject,
}

#[repr(C)]
pub struct PyModuleDef {
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

#[repr(C)]
struct Py_buffer {
    buf: *mut c_void,
    obj: *mut PyObject,
    len: Py_ssize_t,
    itemsize: Py_ssize_t,
    readonly: c_int,
    ndim: c_int,
    format: *mut c_char,
    shape: *mut Py_ssize_t,
    strides: *mut Py_ssize_t,
    suboffsets: *mut Py_ssize_t,
    internal: *mut c_void,
}

impl PyMethodDef {
    const fn zeroed() -> Self {
        Self {
            ml_name: ptr::null_mut(),
            ml_meth: PyMethodDefFuncPointer { void: ptr::null_mut() },
            ml_flags: 0,
            ml_doc: ptr::null_mut(),
        }
    }
}

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    static mut PyExc_TypeError: *mut PyObject;
    static mut PyExc_ValueError: *mut PyObject;
    fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    fn PyBytes_FromStringAndSize(data: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    fn PyUnicode_FromStringAndSize(data: *const c_char, size: Py_ssize_t) -> *mut PyObject;
    fn PyUnicode_AsUTF8AndSize(object: *mut PyObject, size: *mut Py_ssize_t) -> *const c_char;
    fn PyErr_ExceptionMatches(exception: *mut PyObject) -> c_int;
    fn PyErr_Clear();
    fn PyObject_GetBuffer(object: *mut PyObject, view: *mut Py_buffer, flags: c_int) -> c_int;
    fn PyBuffer_Release(view: *mut Py_buffer);
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

const PYBUF_SIMPLE: c_int = 0;

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        let buffer = unsafe {
            if PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) != 0 {
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

fn fail(exception: *mut PyObject, message: &'static core::ffi::CStr) -> *mut PyObject {
    unsafe {
        PyErr_SetString(exception, message.as_ptr());
    }
    ptr::null_mut()
}

fn type_error(message: &'static core::ffi::CStr) -> *mut PyObject {
    unsafe { fail(PyExc_TypeError, message) }
}

fn value_error(message: &'static core::ffi::CStr) -> *mut PyObject {
    unsafe { fail(PyExc_ValueError, message) }
}

unsafe fn argument(args: *mut *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { *args.add(index) }
}

fn read_uuid(object: *mut PyObject) -> Result<Uuid, ()> {
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

// Ordinary strings expose existing UTF-8 data without an encoded bytes
// allocation. Buffer inputs retain the same validation for private callers.
fn parse_bytes(data: &[u8]) -> *mut PyObject {
    let text = match core::str::from_utf8(data) {
        Ok(text) => text,
        Err(_) => return value_error(c"invalid UUID hexadecimal data"),
    };
    match Uuid::parse_str(text) {
        Ok(value) => return_bytes(value.as_bytes()),
        Err(_) => value_error(c"invalid UUID hexadecimal data"),
    }
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
    let object = unsafe { argument(args, 0) };
    let mut length = 0;
    let text = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if !text.is_null() {
        let data = unsafe { slice::from_raw_parts(text.cast::<u8>(), length as usize) };
        return parse_bytes(data);
    }
    if unsafe { PyErr_ExceptionMatches(PyExc_TypeError) } == 0 {
        return ptr::null_mut();
    }
    unsafe { PyErr_Clear() };
    let buffer = match BorrowedBuffer::from_object(object) {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    parse_bytes(buffer.as_slice())
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
    let mut bytes = [0_u8; 16];
    // Keep the UUID crate's OS entropy backend and fatal error contract,
    // without linking its formatted panic diagnostic into the extension.
    if getrandom::fill(&mut bytes).is_err() {
        unsafe { abort() }
    }
    return_bytes(uuid::Builder::from_random_bytes(bytes).as_uuid().as_bytes())
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
            let mut buffer = Uuid::encode_buffer();
            let text = if simple {
                value.simple().encode_lower(&mut buffer)
            } else {
                value.hyphenated().encode_lower(&mut buffer)
            };
            unsafe {
                PyUnicode_FromStringAndSize(text.as_ptr().cast(), text.len() as Py_ssize_t)
            }
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
        ml_doc: c"Parse hexadecimal UUID digits from str or a UTF-8 buffer".as_ptr() as *mut c_char,
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
        ml_doc: c"Return canonical hyphenated lowercase UUID text as str".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"format_hex".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: format_hex },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return lowercase hexadecimal UUID text as str".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _UUID_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_Base {
            ob_base: PyObject {
                ob_refcnt: STATIC_IMMORTAL_REFCNT,
                ob_type: ptr::null_mut(),
            },
            m_init: None,
            m_index: 0,
            m_copy: ptr::null_mut(),
        },
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
