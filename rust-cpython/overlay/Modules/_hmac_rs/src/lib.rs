#![no_std]

mod ffi;

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::mem::{MaybeUninit, align_of, size_of};
use core::ptr;
use core::slice;

use ffi::METH_O;
use ffi::METH_VARARGS;
use ffi::PyCapsule_GetPointer;
use ffi::PyCapsule_IsValid;
use ffi::PyCapsule_New;
use ffi::PyErr_Clear;
use ffi::PyErr_NoMemory;
use ffi::PyErr_SetString;
use ffi::PyExc_TypeError;
use ffi::PyExc_ValueError;
use ffi::PyBytes_FromStringAndSize;
use ffi::Py_IncRef;
use ffi::Py_buffer;
use ffi::PyBuffer_Release;
use ffi::PyMethodDef;
use ffi::PyMethodDefFuncPointer;
use ffi::PyModuleDef;
use ffi::PyModuleDef_HEAD_INIT;
use ffi::PyModuleDef_Init;
use ffi::PyObject;
use ffi::PyObject_GetBuffer;
use ffi::PyTuple_GetItem;
use ffi::PyTuple_Size;
use ffi::PyUnicode_AsUTF8AndSize;
use ffi::PyUnicode_FromStringAndSize;
use ffi::Py_ssize_t;

use hmac::{Hmac, KeyInit, Mac, SimpleHmac};
use md5::Md5;
use sha1::Sha1;
use sha2::{Sha224, Sha256, Sha384, Sha512, Sha512_224, Sha512_256};
use sha3::{Sha3_224, Sha3_256, Sha3_384, Sha3_512};

const PYBUF_SIMPLE: c_int = 0;
const CAPSULE_NAME: &core::ffi::CStr = c"_hmac_rs.HMACState";
const HEX: &[u8; 16] = b"0123456789abcdef";

#[derive(Clone)]
enum HmacState {
    Md5(Hmac<Md5>),
    Sha1(Hmac<Sha1>),
    Sha224(Hmac<Sha224>),
    Sha256(Hmac<Sha256>),
    Sha384(Hmac<Sha384>),
    Sha512(Hmac<Sha512>),
    Sha512_224(Hmac<Sha512_224>),
    Sha512_256(Hmac<Sha512_256>),
    Sha3_224(SimpleHmac<Sha3_224>),
    Sha3_256(SimpleHmac<Sha3_256>),
    Sha3_384(SimpleHmac<Sha3_384>),
    Sha3_512(SimpleHmac<Sha3_512>),
}

impl HmacState {
    fn new(name: &[u8], key: &[u8]) -> Option<Self> {
        match name {
            b"md5" => Hmac::<Md5>::new_from_slice(key).ok().map(Self::Md5),
            b"sha1" => Hmac::<Sha1>::new_from_slice(key).ok().map(Self::Sha1),
            b"sha224" => Hmac::<Sha224>::new_from_slice(key).ok().map(Self::Sha224),
            b"sha256" => Hmac::<Sha256>::new_from_slice(key).ok().map(Self::Sha256),
            b"sha384" => Hmac::<Sha384>::new_from_slice(key).ok().map(Self::Sha384),
            b"sha512" => Hmac::<Sha512>::new_from_slice(key).ok().map(Self::Sha512),
            b"sha512_224" => Hmac::<Sha512_224>::new_from_slice(key)
                .ok()
                .map(Self::Sha512_224),
            b"sha512_256" => Hmac::<Sha512_256>::new_from_slice(key)
                .ok()
                .map(Self::Sha512_256),
            b"sha3_224" => SimpleHmac::<Sha3_224>::new_from_slice(key).ok().map(Self::Sha3_224),
            b"sha3_256" => SimpleHmac::<Sha3_256>::new_from_slice(key).ok().map(Self::Sha3_256),
            b"sha3_384" => SimpleHmac::<Sha3_384>::new_from_slice(key).ok().map(Self::Sha3_384),
            b"sha3_512" => SimpleHmac::<Sha3_512>::new_from_slice(key).ok().map(Self::Sha3_512),
            _ => None,
        }
    }

    fn update(&mut self, data: &[u8]) {
        match self {
            Self::Md5(mac) => mac.update(data),
            Self::Sha1(mac) => mac.update(data),
            Self::Sha224(mac) => mac.update(data),
            Self::Sha256(mac) => mac.update(data),
            Self::Sha384(mac) => mac.update(data),
            Self::Sha512(mac) => mac.update(data),
            Self::Sha512_224(mac) => mac.update(data),
            Self::Sha512_256(mac) => mac.update(data),
            Self::Sha3_224(mac) => mac.update(data),
            Self::Sha3_256(mac) => mac.update(data),
            Self::Sha3_384(mac) => mac.update(data),
            Self::Sha3_512(mac) => mac.update(data),
        }
    }

    fn digest(&self, output: &mut [u8; 64]) -> usize {
        macro_rules! finalize {
            ($mac:expr) => {{
                let digest = $mac.clone().finalize().into_bytes();
                let size = digest.len();
                output[..size].copy_from_slice(&digest);
                size
            }};
        }
        match self {
            Self::Md5(mac) => finalize!(mac),
            Self::Sha1(mac) => finalize!(mac),
            Self::Sha224(mac) => finalize!(mac),
            Self::Sha256(mac) => finalize!(mac),
            Self::Sha384(mac) => finalize!(mac),
            Self::Sha512(mac) => finalize!(mac),
            Self::Sha512_224(mac) => finalize!(mac),
            Self::Sha512_256(mac) => finalize!(mac),
            Self::Sha3_224(mac) => finalize!(mac),
            Self::Sha3_256(mac) => finalize!(mac),
            Self::Sha3_384(mac) => finalize!(mac),
            Self::Sha3_512(mac) => finalize!(mac),
        }
    }
}

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    unsafe fn from_object(object: *mut PyObject) -> Option<Self> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        if unsafe { PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) } != 0 {
            return None;
        }
        Some(Self {
            view: unsafe { view.assume_init() },
        })
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

fn set_type_error(message: &'static core::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

fn set_value_error(message: &'static core::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) };
    ptr::null_mut()
}

// The caller retains the arguments tuple, including this immutable Unicode
// object, until all borrowed key/data buffers have been released.
unsafe fn read_name<'a>(object: *mut PyObject) -> Option<&'a [u8]> {
    let mut size: Py_ssize_t = 0;
    let name = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if name.is_null() {
        return None;
    }
    if size < 0 {
        set_value_error(c"digest name has a negative encoded length");
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(name.cast::<u8>(), size as usize) };
    Some(bytes)
}

unsafe fn tuple_item(args: *mut PyObject, index: Py_ssize_t, count: Py_ssize_t) -> Option<*mut PyObject> {
    if unsafe { PyTuple_Size(args) } != count {
        set_type_error(c"invalid number of arguments");
        return None;
    }
    let item = unsafe { PyTuple_GetItem(args, index) };
    if item.is_null() {
        None
    } else {
        Some(item)
    }
}

unsafe fn get_state(capsule: *mut PyObject) -> Option<*mut HmacState> {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, CAPSULE_NAME.as_ptr()) };
    if pointer.is_null() {
        return None;
    }
    Some(pointer.cast::<HmacState>())
}

unsafe extern "C" fn destroy_state(capsule: *mut PyObject) {
    if unsafe { PyCapsule_IsValid(capsule, CAPSULE_NAME.as_ptr()) } == 0 {
        unsafe { PyErr_Clear() };
        return;
    }
    let pointer = unsafe { PyCapsule_GetPointer(capsule, CAPSULE_NAME.as_ptr()) };
    if !pointer.is_null() {
        unsafe { free_state(pointer.cast::<HmacState>()) };
    } else {
        unsafe { PyErr_Clear() };
    }
}

// System's allocator uses malloc/free for these nonzero, normally aligned
// states on the supported 64-bit macOS and Linux targets. Keep its infallible
// Box allocation contract: exhaustion aborts rather than setting a Python error.
const _: () = assert!(size_of::<usize>() == 8);
const _: () = assert!(size_of::<HmacState>() > 0 && align_of::<HmacState>() <= 16);

#[cfg_attr(target_os = "macos", link(name = "System"))]
#[cfg_attr(target_os = "linux", link(name = "c"))]
unsafe extern "C" {
    fn malloc(size: usize) -> *mut c_void;
    fn free(pointer: *mut c_void);
    fn abort() -> !;
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo<'_>) -> ! {
    unsafe { abort() }
}

fn allocate_state(state: HmacState) -> *mut HmacState {
    let pointer = unsafe { malloc(size_of::<HmacState>()) }.cast::<HmacState>();
    if pointer.is_null() {
        unsafe { abort() }
    }
    unsafe { pointer.write(state) };
    pointer
}

unsafe fn free_state(pointer: *mut HmacState) {
    // Preserve the crypto states' existing destruction and zeroize features
    // before releasing their storage.
    unsafe { ptr::drop_in_place(pointer) };
    unsafe { free(pointer.cast::<c_void>()) };
}

fn make_capsule(state: HmacState) -> *mut PyObject {
    let pointer = allocate_state(state);
    let capsule = unsafe {
        PyCapsule_New(
            pointer.cast::<c_void>(),
            CAPSULE_NAME.as_ptr(),
            Some(destroy_state),
        )
    };
    if capsule.is_null() {
        unsafe { free_state(pointer) };
    }
    capsule
}

unsafe fn new_impl(args: *mut PyObject) -> *mut PyObject {
    let Some(key_object) = (unsafe { tuple_item(args, 0, 2) }) else {
        return ptr::null_mut();
    };
    let Some(name_object) = (unsafe { tuple_item(args, 1, 2) }) else {
        return ptr::null_mut();
    };
    let Some(name) = (unsafe { read_name(name_object) }) else {
        return ptr::null_mut();
    };
    let Some(key) = (unsafe { BorrowedBuffer::from_object(key_object) }) else {
        return ptr::null_mut();
    };
    let Some(state) = HmacState::new(name, key.bytes()) else {
        return set_value_error(c"unsupported HMAC digest");
    };
    make_capsule(state)
}

unsafe fn update_impl(args: *mut PyObject) -> *mut PyObject {
    let Some(state_object) = (unsafe { tuple_item(args, 0, 2) }) else {
        return ptr::null_mut();
    };
    let Some(data_object) = (unsafe { tuple_item(args, 1, 2) }) else {
        return ptr::null_mut();
    };
    let Some(data) = (unsafe { BorrowedBuffer::from_object(data_object) }) else {
        return ptr::null_mut();
    };
    let Some(state) = (unsafe { get_state(state_object) }) else {
        return ptr::null_mut();
    };
    unsafe { &mut *state }.update(data.bytes());
    unsafe { Py_IncRef(state_object) };
    state_object
}

unsafe fn copy_impl(state_object: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { get_state(state_object) }) else {
        return ptr::null_mut();
    };
    make_capsule(unsafe { &*state }.clone())
}

fn bytes_from_slice(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

unsafe fn digest_impl(state_object: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { get_state(state_object) }) else {
        return ptr::null_mut();
    };
    let mut result = [0u8; 64];
    let size = unsafe { &*state }.digest(&mut result);
    bytes_from_slice(&result[..size])
}

unsafe fn hexdigest_impl(state_object: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { get_state(state_object) }) else {
        return ptr::null_mut();
    };
    let mut result = [0u8; 64];
    let size = unsafe { &*state }.digest(&mut result);
    let mut hex = [0u8; 128];
    for (index, byte) in result[..size].iter().copied().enumerate() {
        hex[index * 2] = HEX[(byte >> 4) as usize];
        hex[index * 2 + 1] = HEX[(byte & 0x0f) as usize];
    }
    unsafe { PyUnicode_FromStringAndSize(hex.as_ptr().cast::<c_char>(), (size * 2) as Py_ssize_t) }
}

unsafe fn compute_digest_impl(args: *mut PyObject) -> *mut PyObject {
    let Some(key_object) = (unsafe { tuple_item(args, 0, 3) }) else {
        return ptr::null_mut();
    };
    let Some(data_object) = (unsafe { tuple_item(args, 1, 3) }) else {
        return ptr::null_mut();
    };
    let Some(name_object) = (unsafe { tuple_item(args, 2, 3) }) else {
        return ptr::null_mut();
    };
    let Some(name) = (unsafe { read_name(name_object) }) else {
        return ptr::null_mut();
    };
    let Some(key) = (unsafe { BorrowedBuffer::from_object(key_object) }) else {
        return ptr::null_mut();
    };
    let Some(data) = (unsafe { BorrowedBuffer::from_object(data_object) }) else {
        return ptr::null_mut();
    };
    let Some(mut state) = HmacState::new(name, key.bytes()) else {
        return set_value_error(c"unsupported HMAC digest");
    };
    state.update(data.bytes());
    let mut result = [0u8; 64];
    let size = state.digest(&mut result);
    bytes_from_slice(&result[..size])
}

unsafe extern "C" fn new(
    _module: *mut PyObject,
    args: *mut PyObject,
) -> *mut PyObject {
    unsafe { new_impl(args) }
}

unsafe extern "C" fn update(
    _module: *mut PyObject,
    args: *mut PyObject,
) -> *mut PyObject {
    unsafe { update_impl(args) }
}

unsafe extern "C" fn copy(
    _module: *mut PyObject,
    state: *mut PyObject,
) -> *mut PyObject {
    unsafe { copy_impl(state) }
}

unsafe extern "C" fn digest(
    _module: *mut PyObject,
    state: *mut PyObject,
) -> *mut PyObject {
    unsafe { digest_impl(state) }
}

unsafe extern "C" fn hexdigest(
    _module: *mut PyObject,
    state: *mut PyObject,
) -> *mut PyObject {
    unsafe { hexdigest_impl(state) }
}

unsafe extern "C" fn compute_digest(
    _module: *mut PyObject,
    args: *mut PyObject,
) -> *mut PyObject {
    unsafe { compute_digest_impl(args) }
}

pub extern "C" fn _hmac_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _hmac_rs_free(_obj: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _HMAC_RS_MODULE_METHODS: [PyMethodDef; 7] = {
    [
        PyMethodDef {
            ml_name: c"new".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: new },
            ml_flags: METH_VARARGS,
            ml_doc: c"Create a keyed digest state.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"update".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: update },
            ml_flags: METH_VARARGS,
            ml_doc: c"Update a keyed digest state with bytes-like input.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"copy".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: copy },
            ml_flags: METH_O,
            ml_doc: c"Copy a keyed digest state.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"digest".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: digest },
            ml_flags: METH_O,
            ml_doc: c"Finalize a copy of a keyed digest state.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"hexdigest".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: hexdigest },
            ml_flags: METH_O,
            ml_doc: c"Finalize a copy of a keyed digest state as hexadecimal text.".as_ptr() as *mut c_char,
        },
        PyMethodDef {
            ml_name: c"compute_digest".as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunction: compute_digest },
            ml_flags: METH_VARARGS,
            ml_doc: c"Compute a one-shot keyed digest.".as_ptr() as *mut c_char,
        },
        PyMethodDef::zeroed(),
    ]
};

pub static _HMAC_RS_MODULE: ModuleDef = {
    ModuleDef {
        ffi: UnsafeCell::new(PyModuleDef {
            m_base: PyModuleDef_HEAD_INIT,
            m_name: c"_hmac_rs".as_ptr() as *mut _,
            m_doc: c"Rust HMAC state for supported fixed-output digest algorithms.".as_ptr() as *mut _,
            m_size: 0,
            m_methods: &_HMAC_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
            m_slots: ptr::null_mut(),
            m_traverse: None,
            m_clear: Some(_hmac_rs_clear),
            m_free: Some(_hmac_rs_free),
        }),
    }
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__hmac_rs() -> *mut PyObject {
    _HMAC_RS_MODULE.init_multi_phase()
}
