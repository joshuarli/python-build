use std::ffi::{c_char, c_int, c_long, c_void};
use std::mem::MaybeUninit;
use std::net::{Ipv4Addr, Ipv6Addr};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, Py_buffer, PyBuffer_Release, PyBytes_FromStringAndSize, Py_NewRef,
    PyErr_CheckSignals, PyErr_Occurred, PyErr_SetFromErrno, PyErr_SetString, PyEval_RestoreThread,
    PyEval_SaveThread, PyExc_OSError,
    PyExc_TypeError, PyExc_ValueError, PyLong_AsLong, PyLong_FromSsize_t,
    PyMethodDef, PyMethodDefFuncPointer, PyABIInfo, PySlot,
    PySlot__bindgen_ty_1, PySlot__bindgen_ty_2, PySlot_INTPTR, PySlot_STATIC,
    Py_mod_abi, Py_mod_name, Py_mod_doc, Py_mod_methods, PyObject, PyObject_GetBuffer,
    PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, Py_ssize_t,
};

unsafe extern "C" {
    fn send(fd: c_int, data: *const c_void, len: usize, flags: c_int) -> isize;
    fn recv(fd: c_int, data: *mut c_void, len: usize, flags: c_int) -> isize;
}

const PYBUF_SIMPLE: c_int = 0;

fn fail(exception: *mut PyObject, message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(exception, message.as_ptr()) };
    ptr::null_mut()
}

fn type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { fail(PyExc_TypeError, message) }
}

fn value_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { fail(PyExc_ValueError, message) }
}

unsafe fn arg(args: *mut *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { *args.add(index) }
}

fn integer(object: *mut PyObject) -> Result<c_long, ()> {
    let value = unsafe { PyLong_AsLong(object) };
    if unsafe { !PyErr_Occurred().is_null() } {
        Err(())
    } else {
        Ok(value)
    }
}

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    fn from_object(object: *mut PyObject) -> Result<Self, ()> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        if unsafe { PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) } != 0 {
            return Err(());
        }
        Ok(Self { view: unsafe { view.assume_init() } })
    }

    fn bytes(&self) -> &[u8] {
        if self.view.len == 0 {
            return &[];
        }
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) };
    }
}

unsafe extern "C" fn parse_address(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"parse_address() takes exactly two arguments");
    }
    let version = match integer(unsafe { arg(args, 0) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let mut len = 0;
    let text = unsafe { PyUnicode_AsUTF8AndSize(arg(args, 1), &mut len) };
    if text.is_null() {
        return ptr::null_mut();
    }
    let text = unsafe { slice::from_raw_parts(text.cast::<u8>(), len as usize) };
    let Ok(text) = std::str::from_utf8(text) else {
        return value_error(c"invalid IP address");
    };
    match version {
        4 => match text.parse::<Ipv4Addr>() {
            Ok(address) => bytes(&address.octets()),
            Err(_) => value_error(c"invalid IPv4 address"),
        },
        6 => match text.parse::<Ipv6Addr>() {
            Ok(address) => bytes(&address.octets()),
            Err(_) => value_error(c"invalid IPv6 address"),
        },
        _ => value_error(c"unknown IP address version"),
    }
}

fn bytes(data: &[u8]) -> *mut PyObject {
    unsafe { PyBytes_FromStringAndSize(data.as_ptr().cast(), data.len() as Py_ssize_t) }
}

unsafe extern "C" fn format_address(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"format_address() takes exactly two arguments");
    }
    let version = match integer(unsafe { arg(args, 0) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let data = match BorrowedBuffer::from_object(unsafe { arg(args, 1) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let text = match (version, data.bytes()) {
        (4, [a, b, c, d]) => Ipv4Addr::new(*a, *b, *c, *d).to_string(),
        (6, address) if address.len() == 16 => {
            Ipv6Addr::from(<[u8; 16]>::try_from(address).unwrap()).to_string()
        }
        _ => return value_error(c"invalid packed IP address"),
    };
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast(), text.len() as Py_ssize_t) }
}

unsafe extern "C" fn socket_send(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"send() takes exactly two arguments");
    }
    let fd = match integer(unsafe { arg(args, 0) }) {
        Ok(value) if (0..=c_int::MAX as c_long).contains(&value) => value as c_int,
        Ok(_) => return value_error(c"invalid socket descriptor"),
        Err(()) => return ptr::null_mut(),
    };
    let data = match BorrowedBuffer::from_object(unsafe { arg(args, 1) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let state = unsafe { PyEval_SaveThread() };
    let result = unsafe { send(fd, data.view.buf, data.view.len as usize, 0) };
    let interrupted = result < 0
        && std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted;
    unsafe { PyEval_RestoreThread(state) };
    if interrupted {
        if unsafe { PyErr_CheckSignals() } != 0 {
            return ptr::null_mut();
        }
        // A negative count is never a successful send; the caller rechecks
        // the descriptor and timeout before retrying after a signal.
        unsafe { PyLong_FromSsize_t(-2) }
    } else if result < 0 {
        unsafe { PyErr_SetFromErrno(PyExc_OSError) }
    } else {
        unsafe { PyLong_FromSsize_t(result as Py_ssize_t) }
    }
}

unsafe extern "C" fn socket_recv(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"recv() takes exactly two arguments");
    }
    let fd = match integer(unsafe { arg(args, 0) }) {
        Ok(value) if (0..=c_int::MAX as c_long).contains(&value) => value as c_int,
        Ok(_) => return value_error(c"invalid socket descriptor"),
        Err(()) => return ptr::null_mut(),
    };
    let len = match integer(unsafe { arg(args, 1) }) {
        Ok(value) if value > 0 => value as usize,
        Ok(_) => return value_error(c"invalid receive buffer size"),
        Err(()) => return ptr::null_mut(),
    };
    let mut data = Vec::<u8>::new();
    if data.try_reserve_exact(len).is_err() {
        return unsafe { cpython_sys::PyErr_NoMemory() };
    }
    let state = unsafe { PyEval_SaveThread() };
    let result = unsafe { recv(fd, data.as_mut_ptr().cast(), len, 0) };
    let interrupted = result < 0
        && std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted;
    unsafe { PyEval_RestoreThread(state) };
    if interrupted {
        if unsafe { PyErr_CheckSignals() } != 0 {
            return ptr::null_mut();
        }
        // None is never a successful receive; the caller rechecks the
        // descriptor and timeout before retrying after a signal.
        unsafe { Py_NewRef(ptr::addr_of_mut!(cpython_sys::_Py_NoneStruct)) }
    } else if result < 0 {
        unsafe { PyErr_SetFromErrno(PyExc_OSError) }
    } else {
        unsafe { PyBytes_FromStringAndSize(data.as_ptr().cast(), result as Py_ssize_t) }
    }
}

struct ModuleSlots([PySlot; 6]);
unsafe impl Sync for ModuleSlots {}

// The non-stable ABI is the locked CPython 3.16.0a0 GIL build. The loader
// checks major/minor and GIL compatibility; the source lock pins the revision.
static ABI_INFO: PyABIInfo = PyABIInfo {
    abiinfo_major_version: 1, abiinfo_minor_version: 0, flags: 2,
    build_version: 0x031000a0, abi_version: 0x031000a0,
};

#[cfg(not(target_pointer_width = "64"))]
compile_error!("socket slot export requires the supported 64-bit CPython ABI");

const _: () = {
    assert!(std::mem::size_of::<PySlot>() == 16);
    assert!(std::mem::align_of::<PySlot>() == 8);
    assert!(std::mem::offset_of!(PySlot, sl_id) == 0);
    assert!(std::mem::offset_of!(PySlot, sl_flags) == 2);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_1) == 4);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_2) == 8);
    assert!(std::mem::size_of::<PyABIInfo>() == 12);
    assert!(std::mem::align_of::<PyABIInfo>() == 4);
};

const fn data_slot(id: u32, value: *mut c_void) -> PySlot {
    PySlot { sl_id: id as u16, sl_flags: PySlot_INTPTR as u16,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: value } }
}

// Method objects retain these definitions after slot copying. The immutable
// array lives for the process, so its pointer has static ownership.
const fn static_data_slot(id: u32, value: *mut c_void) -> PySlot {
    let mut slot = data_slot(id, value);
    slot.sl_flags |= PySlot_STATIC as u16;
    slot
}

// The non-limited compatibility macro is function-like and not generated
// by bindgen; the native header oracle checks this identifier's exact value.
const MODULE_MULTIPLE_INTERPRETERS_SLOT: u16 = 86;

static METHODS: [PyMethodDef; 5] = [
    PyMethodDef {
        ml_name: c"parse_address".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: parse_address },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse an IPv4 or IPv6 address into network-order bytes".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"format_address".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: format_address },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Format network-order IPv4 or IPv6 bytes".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"send".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: socket_send },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Send bytes through a borrowed blocking socket descriptor".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"recv".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: socket_recv },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Receive bytes through a borrowed blocking socket descriptor".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    data_slot(Py_mod_abi, &ABI_INFO as *const PyABIInfo as *mut c_void),
    data_slot(Py_mod_name, c"_socket_rs".as_ptr() as *mut c_void),
    data_slot(Py_mod_doc, c"Rust address conversion and blocking socket I/O".as_ptr() as *mut c_void),
    static_data_slot(Py_mod_methods, METHODS.as_ptr() as *mut c_void),
    PySlot { sl_id: MODULE_MULTIPLE_INTERPRETERS_SLOT, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_uint64: 2 } },
    PySlot { sl_id: 0, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: ptr::null_mut() } },
]);

#[unsafe(no_mangle)]
pub extern "C" fn PyModExport__socket_rs() -> *mut PySlot {
    MODULE_SLOTS.0.as_ptr() as *mut PySlot
}
