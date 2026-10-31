use std::ffi::{c_int, c_long, c_void};
use std::net::{Ipv4Addr, Ipv6Addr};
use std::ptr;
use std::slice;

use cpython_binding::ffi::{
    PyBytes_FromStringAndSize, PyErr_Occurred, PyLong_FromSsize_t, PyMethodDef,
    PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, Py_NewRef, Py_ssize_t, PyErr_NoMemory,
    PyObject, _Py_NoneStruct,
};
use cpython_binding::ffi_ext::{
    PyErr_CheckSignals, PyErr_SetFromErrno, PyEval_RestoreThread, PyEval_SaveThread,
    PyExc_OSError, PyLong_AsLong,
};
use cpython_binding::module::PER_INTERPRETER_GIL;
use cpython_binding::{
    Borrowed, Buffer, Exception, Module, fastcall, method_table_end, raise,
};

unsafe extern "C" {
    fn send(fd: c_int, data: *const c_void, len: usize, flags: c_int) -> isize;
    fn recv(fd: c_int, data: *mut c_void, len: usize, flags: c_int) -> isize;
}

fn type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    raise(Exception::TypeError, message);
    ptr::null_mut()
}

fn value_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    raise(Exception::ValueError, message);
    ptr::null_mut()
}

fn acquire(object: *mut PyObject) -> Result<Buffer, ()> {
    Buffer::acquire(unsafe { Borrowed::from_raw(object) }).map_err(|_| ())
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
    let data = match acquire(unsafe { arg(args, 1) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let text = match (version, data.as_bytes()) {
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
    let data = match acquire(unsafe { arg(args, 1) }) {
        Ok(value) => value,
        Err(()) => return ptr::null_mut(),
    };
    let state = unsafe { PyEval_SaveThread() };
    let result = unsafe { send(fd, data.as_bytes().as_ptr().cast(), data.as_bytes().len(), 0) };
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
        return unsafe { PyErr_NoMemory() };
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
        unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
    } else if result < 0 {
        unsafe { PyErr_SetFromErrno(PyExc_OSError) }
    } else {
        unsafe { PyBytes_FromStringAndSize(data.as_ptr().cast(), result as Py_ssize_t) }
    }
}

static METHODS: [PyMethodDef; 5] = [
    fastcall(
        c"parse_address",
        parse_address,
        c"Parse an IPv4 or IPv6 address into network-order bytes",
    ),
    fastcall(
        c"format_address",
        format_address,
        c"Format network-order IPv4 or IPv6 bytes",
    ),
    fastcall(
        c"send",
        socket_send,
        c"Send bytes through a borrowed blocking socket descriptor",
    ),
    fastcall(
        c"recv",
        socket_recv,
        c"Receive bytes through a borrowed blocking socket descriptor",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_socket_rs",
    c"Rust address conversion and blocking socket I/O",
    &METHODS,
)
.with_slots(&PER_INTERPRETER_GIL);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__socket_rs() -> *mut PyObject {
    MODULE.init()
}
