use std::ffi::{CStr, c_void};

use cpython_binding::ffi::{
    PyCapsule_GetPointer, PyCapsule_IsValid, PyCapsule_New, PyErr_Clear, PyMethodDef, PyObject,
    PyTuple_GetItem, PyTuple_Size, PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize,
    Py_ssize_t,
};
use cpython_binding::module::PER_INTERPRETER_GIL;
use cpython_binding::{
    Borrowed, Buffer, BytesWriter, Exception, Module, Outcome, Owned, Stop, into_return,
    method_table_end, raise, single_argument, varargs,
};

use hmac::{Hmac, KeyInit, Mac, SimpleHmac};
use md5::Md5;
use ripemd::Ripemd160;
use sha1::Sha1;
use sha2::{Sha224, Sha256, Sha384, Sha512, Sha512_224, Sha512_256};
use sha3::{Sha3_224, Sha3_256, Sha3_384, Sha3_512};
use sm3::Sm3;

const CAPSULE_NAME: &CStr = c"_hmac_rs.HMACState";
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
    Ripemd160(Hmac<Ripemd160>),
    Sm3(Hmac<Sm3>),
}

impl HmacState {
    fn new(name: &str, key: &[u8]) -> Option<Self> {
        match name {
            "md5" => Hmac::<Md5>::new_from_slice(key).ok().map(Self::Md5),
            "sha1" => Hmac::<Sha1>::new_from_slice(key).ok().map(Self::Sha1),
            "sha224" => Hmac::<Sha224>::new_from_slice(key).ok().map(Self::Sha224),
            "sha256" => Hmac::<Sha256>::new_from_slice(key).ok().map(Self::Sha256),
            "sha384" => Hmac::<Sha384>::new_from_slice(key).ok().map(Self::Sha384),
            "sha512" => Hmac::<Sha512>::new_from_slice(key).ok().map(Self::Sha512),
            "sha512_224" => Hmac::<Sha512_224>::new_from_slice(key)
                .ok()
                .map(Self::Sha512_224),
            "sha512_256" => Hmac::<Sha512_256>::new_from_slice(key)
                .ok()
                .map(Self::Sha512_256),
            "sha3_224" => SimpleHmac::<Sha3_224>::new_from_slice(key).ok().map(Self::Sha3_224),
            "sha3_256" => SimpleHmac::<Sha3_256>::new_from_slice(key).ok().map(Self::Sha3_256),
            "sha3_384" => SimpleHmac::<Sha3_384>::new_from_slice(key).ok().map(Self::Sha3_384),
            "sha3_512" => SimpleHmac::<Sha3_512>::new_from_slice(key).ok().map(Self::Sha3_512),
            "ripemd160" => Hmac::<Ripemd160>::new_from_slice(key).ok().map(Self::Ripemd160),
            "sm3" => Hmac::<Sm3>::new_from_slice(key).ok().map(Self::Sm3),
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
            Self::Ripemd160(mac) => mac.update(data),
            Self::Sm3(mac) => mac.update(data),
        }
    }

    fn digest(&self) -> Vec<u8> {
        match self {
            Self::Md5(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha1(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha224(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha256(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha384(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha512(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha512_224(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha512_256(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha3_224(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha3_256(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha3_384(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sha3_512(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Ripemd160(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Sm3(mac) => mac.clone().finalize().into_bytes().to_vec(),
        }
    }
}

fn read_name(object: Borrowed<'_>) -> Outcome<String> {
    let mut size: Py_ssize_t = 0;
    let name = unsafe { PyUnicode_AsUTF8AndSize(object.as_ptr(), &mut size) };
    if name.is_null() {
        return Err(Stop::Raised);
    }
    if size < 0 {
        return Err(raise(Exception::ValueError, c"digest name has a negative encoded length"));
    }
    let bytes = unsafe { core::slice::from_raw_parts(name.cast::<u8>(), size as usize) };
    Ok(unsafe { core::str::from_utf8_unchecked(bytes) }.to_owned())
}

unsafe fn tuple_arguments<'a, const COUNT: usize>(args: *mut PyObject) -> Outcome<[Borrowed<'a>; COUNT]> {
    if unsafe { PyTuple_Size(args) } != COUNT as Py_ssize_t {
        return Err(raise(Exception::TypeError, c"invalid number of arguments"));
    }
    let mut items = [None; COUNT];
    for (index, item) in items.iter_mut().enumerate() {
        let pointer = unsafe { PyTuple_GetItem(args, index as Py_ssize_t) };
        if pointer.is_null() {
            return Err(Stop::Raised);
        }
        *item = Some(unsafe { Borrowed::from_raw(pointer) });
    }
    Ok(items.map(|item| item.unwrap()))
}

fn get_state<'a>(capsule: Borrowed<'a>) -> Outcome<&'a mut HmacState> {
    let pointer = unsafe { PyCapsule_GetPointer(capsule.as_ptr(), CAPSULE_NAME.as_ptr()) };
    if pointer.is_null() {
        return Err(Stop::Raised);
    }
    Ok(unsafe { &mut *pointer.cast::<HmacState>() })
}

unsafe extern "C" fn destroy_state(capsule: *mut PyObject) {
    if unsafe { PyCapsule_IsValid(capsule, CAPSULE_NAME.as_ptr()) } == 0 {
        unsafe { PyErr_Clear() };
        return;
    }
    let pointer = unsafe { PyCapsule_GetPointer(capsule, CAPSULE_NAME.as_ptr()) };
    if !pointer.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<HmacState>())) };
    } else {
        unsafe { PyErr_Clear() };
    }
}

fn make_capsule(state: HmacState) -> Outcome<Owned> {
    let pointer = Box::into_raw(Box::new(state));
    let capsule = unsafe {
        PyCapsule_New(
            pointer.cast::<c_void>(),
            CAPSULE_NAME.as_ptr(),
            Some(destroy_state),
        )
    };
    unsafe { Owned::from_new_reference(capsule) }.inspect_err(|_| unsafe {
        drop(Box::from_raw(pointer));
    })
}

fn unsupported_digest() -> Stop {
    raise(Exception::ValueError, c"unsupported HMAC digest")
}

fn new_state(args: *mut PyObject) -> Outcome<Owned> {
    let [key_object, name_object] = unsafe { tuple_arguments(args) }?;
    let name = read_name(name_object)?;
    let key = Buffer::acquire(key_object)?;
    make_capsule(HmacState::new(&name, key.as_bytes()).ok_or_else(unsupported_digest)?)
}

fn update_state(args: *mut PyObject) -> Outcome<Owned> {
    let [state_object, data_object] = unsafe { tuple_arguments(args) }?;
    let data = Buffer::acquire(data_object)?;
    get_state(state_object)?.update(data.as_bytes());
    Ok(state_object.to_owned())
}

fn copy_state(state_object: Borrowed<'_>) -> Outcome<Owned> {
    make_capsule(get_state(state_object)?.clone())
}

fn digest_state(state_object: Borrowed<'_>) -> Outcome<Owned> {
    BytesWriter::copy_of(&get_state(state_object)?.digest())
}

fn hexdigest_state(state_object: Borrowed<'_>) -> Outcome<Owned> {
    let result = get_state(state_object)?.digest();
    let mut hex = Vec::with_capacity(result.len() * 2);
    for byte in result {
        hex.push(HEX[(byte >> 4) as usize]);
        hex.push(HEX[(byte & 0x0f) as usize]);
    }
    let text = unsafe { PyUnicode_FromStringAndSize(hex.as_ptr().cast(), hex.len() as Py_ssize_t) };
    unsafe { Owned::from_new_reference(text) }
}

fn compute_digest_once(args: *mut PyObject) -> Outcome<Owned> {
    let [key_object, data_object, name_object] = unsafe { tuple_arguments(args) }?;
    let name = read_name(name_object)?;
    let key = Buffer::acquire(key_object)?;
    let data = Buffer::acquire(data_object)?;
    let mut state = HmacState::new(&name, key.as_bytes()).ok_or_else(unsupported_digest)?;
    state.update(data.as_bytes());
    BytesWriter::copy_of(&state.digest())
}

unsafe extern "C" fn new(_module: *mut PyObject, args: *mut PyObject) -> *mut PyObject {
    into_return(new_state(args))
}

unsafe extern "C" fn update(_module: *mut PyObject, args: *mut PyObject) -> *mut PyObject {
    into_return(update_state(args))
}

unsafe extern "C" fn copy(_module: *mut PyObject, state: *mut PyObject) -> *mut PyObject {
    into_return(copy_state(unsafe { Borrowed::from_raw(state) }))
}

unsafe extern "C" fn digest(_module: *mut PyObject, state: *mut PyObject) -> *mut PyObject {
    into_return(digest_state(unsafe { Borrowed::from_raw(state) }))
}

unsafe extern "C" fn hexdigest(_module: *mut PyObject, state: *mut PyObject) -> *mut PyObject {
    into_return(hexdigest_state(unsafe { Borrowed::from_raw(state) }))
}

unsafe extern "C" fn compute_digest(_module: *mut PyObject, args: *mut PyObject) -> *mut PyObject {
    into_return(compute_digest_once(args))
}

static METHODS: [PyMethodDef; 7] = [
    varargs(c"new", new, c"Create a keyed digest state."),
    varargs(c"update", update, c"Update a keyed digest state with bytes-like input."),
    single_argument(c"copy", copy, c"Copy a keyed digest state."),
    single_argument(c"digest", digest, c"Finalize a copy of a keyed digest state."),
    single_argument(
        c"hexdigest",
        hexdigest,
        c"Finalize a copy of a keyed digest state as hexadecimal text.",
    ),
    varargs(c"compute_digest", compute_digest, c"Compute a one-shot keyed digest."),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_hmac_rs",
    c"Rust HMAC state for supported fixed-output digest algorithms.",
    &METHODS,
)
.with_slots(&PER_INTERPRETER_GIL);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__hmac_rs() -> *mut PyObject {
    MODULE.init()
}
