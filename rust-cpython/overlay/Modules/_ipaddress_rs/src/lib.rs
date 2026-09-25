use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int};
use std::mem::MaybeUninit;
use std::net::{Ipv4Addr, Ipv6Addr};
use std::ptr;
use std::slice;
use std::str;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_buffer;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyLong_AsLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyBuffer_Release;
use cpython_sys::Py_ssize_t;

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

    fn bytes(&self) -> &[u8] {
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

fn set_type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

fn set_value_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) };
    ptr::null_mut()
}

fn bytes_from_slice(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

unsafe fn parse_address(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    ipv6: bool,
) -> *mut PyObject {
    if nargs != 1 {
        return if ipv6 {
            set_type_error(c"parse_ipv6() takes exactly one argument")
        } else {
            set_type_error(c"parse_ipv4() takes exactly one argument")
        };
    }

    let argument = unsafe { &**args };
    let mut size = 0;
    let text = unsafe { PyUnicode_AsUTF8AndSize(argument.as_raw(), &mut size) };
    if text.is_null() {
        return ptr::null_mut();
    }
    if size < 0 {
        return set_value_error(c"address length cannot be negative");
    }
    let bytes = unsafe { slice::from_raw_parts(text.cast::<u8>(), size as usize) };
    let text = unsafe { str::from_utf8_unchecked(bytes) };

    if ipv6 {
        match text.parse::<Ipv6Addr>() {
            Ok(address) => bytes_from_slice(&address.octets()),
            Err(_) => set_value_error(c"invalid IPv6 address"),
        }
    } else {
        match text.parse::<Ipv4Addr>() {
            Ok(address) => bytes_from_slice(&address.octets()),
            Err(_) => set_value_error(c"invalid IPv4 address"),
        }
    }
}

/// Parse standard IPv4 text and return its four network-order octets.
/// Invalid input raises ValueError so the Python boundary can retain its
/// detailed CPython-compatible validation message.
unsafe extern "C" fn parse_ipv4(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { parse_address(args, nargs, false) }
}

/// Parse standard IPv6 text and return its sixteen network-order octets.
/// Invalid input raises ValueError so the Python boundary can retain its
/// detailed CPython-compatible validation message.
unsafe extern "C" fn parse_ipv6(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { parse_address(args, nargs, true) }
}

/// Return the network and broadcast addresses as concatenated network-order
/// octets. The width is inferred from the packed IPv4 or IPv6 input.
unsafe extern "C" fn network_bounds(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return set_type_error(c"network_bounds() takes exactly two arguments");
    }

    let address_object = unsafe { &**args };
    let buffer = match BorrowedBuffer::from_object(address_object) {
        Ok(buffer) => buffer,
        Err(()) => return ptr::null_mut(),
    };
    let address = buffer.bytes();
    let width = address.len();
    let bits = match width {
        4 => 32,
        16 => 128,
        _ => return set_value_error(c"packed address must contain 4 or 16 bytes"),
    };

    let prefix_object = unsafe { *args.add(1) };
    let prefix = unsafe { PyLong_AsLong(prefix_object) };
    if unsafe { !PyErr_Occurred().is_null() } {
        return ptr::null_mut();
    }
    if prefix < 0 || prefix > bits {
        return set_value_error(c"prefix length is outside the address width");
    }

    let value = if width == 4 {
        u32::from_be_bytes(address.try_into().unwrap()) as u128
    } else {
        u128::from_be_bytes(address.try_into().unwrap())
    };
    let all_bits = if bits == 32 {
        u32::MAX as u128
    } else {
        u128::MAX
    };
    let mask = if prefix == 0 {
        0
    } else {
        all_bits << (bits - prefix)
    };
    let network = value & mask;
    let broadcast = network | (all_bits ^ mask);

    let mut result = [0_u8; 32];
    if width == 4 {
        result[..4].copy_from_slice(&(network as u32).to_be_bytes());
        result[4..8].copy_from_slice(&(broadcast as u32).to_be_bytes());
    } else {
        result[..16].copy_from_slice(&network.to_be_bytes());
        result[16..].copy_from_slice(&broadcast.to_be_bytes());
    }
    bytes_from_slice(&result[..width * 2])
}

pub extern "C" fn _ipaddress_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _ipaddress_rs_free(_object: *mut std::ffi::c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _IPADDRESS_RS_MODULE_METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"parse_ipv4".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_ipv4,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse an IPv4 address string".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"parse_ipv6".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: parse_ipv6,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse an IPv6 address string".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"network_bounds".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: network_bounds,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Calculate an address network range".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _IPADDRESS_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_ipaddress_rs".as_ptr() as *mut _,
        m_doc: c"Rust address parsing and network range calculations".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_IPADDRESS_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_ipaddress_rs_clear),
        m_free: Some(_ipaddress_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__ipaddress_rs() -> *mut PyObject {
    _IPADDRESS_RS_MODULE.init_multi_phase()
}
