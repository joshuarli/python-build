use std::ffi::{CStr, c_char, c_int, c_long, c_void};
use std::ptr;
use std::slice;

use blake2::{Blake2b512, Blake2s256};
use cpython_binding::ffi::{
    PyErr_NoMemory, PyErr_Occurred, PyErr_SetObject, PyErr_SetString, PyExc_OverflowError,
    PyExc_TypeError, PyExc_ValueError, PyGetSetDef, PyLong_AsLongLong, PyLong_FromLong,
    PyMethodDef, PyModule_AddObject, PyModuleDef_Slot, PyObject, PyObject_Free,
    PyObject_GetAttrString, PyObject_HashNotImplemented, PyObject_Type, PyTuple_GetItem,
    PyTuple_Size, PyTypeObject, PyType_FromSpec, PyType_GenericAlloc, PyType_Slot, PyType_Spec,
    PyUnicode_AsUTF8AndSize, PyUnicode_FromFormat, PyUnicode_FromStringAndSize, Py_DecRef,
    Py_TPFLAGS_DEFAULT, Py_TPFLAGS_DISALLOW_INSTANTIATION, Py_TPFLAGS_IMMUTABLETYPE,
    Py_mod_exec, Py_ssize_t, Py_tp_dealloc, Py_tp_getset, Py_tp_hash, Py_tp_methods, Py_tp_repr,
    _Py_NoneStruct,
};
use cpython_binding::module::PER_INTERPRETER_GIL_SLOT;
use cpython_binding::{
    Borrowed, Buffer, BytesWriter, Module, Owned, into_return, method_table_end, noargs,
    single_argument, varargs,
};
use hmac::{Hmac, KeyInit, Mac, SimpleHmac};
use md5::Md5;
use ripemd::Ripemd160;
use sha1::{Digest, Sha1};
use sha2::{Sha224, Sha256, Sha384, Sha512, Sha512_224, Sha512_256};
use sha3::{Sha3_224, Sha3_256, Sha3_384, Sha3_512};
use sm3::Sm3;

const HEX: &[u8; 16] = b"0123456789abcdef";

#[derive(Clone)]
enum HashState {
    Md5(Md5),
    Sha1(Sha1),
    Sha224(Sha224),
    Sha256(Sha256),
    Sha384(Sha384),
    Sha512(Sha512),
    Sha512_224(Sha512_224),
    Sha512_256(Sha512_256),
    Ripemd160(Ripemd160),
    Sm3(Sm3),
}

impl HashState {
    fn new(name: &str) -> Option<Self> {
        match name {
            "md5" => Some(Self::Md5(Md5::new())),
            "sha1" => Some(Self::Sha1(Sha1::new())),
            "sha224" => Some(Self::Sha224(Sha224::new())),
            "sha256" => Some(Self::Sha256(Sha256::new())),
            "sha384" => Some(Self::Sha384(Sha384::new())),
            "sha512" => Some(Self::Sha512(Sha512::new())),
            "sha512_224" => Some(Self::Sha512_224(Sha512_224::new())),
            "sha512_256" => Some(Self::Sha512_256(Sha512_256::new())),
            "ripemd160" => Some(Self::Ripemd160(Ripemd160::new())),
            "sm3" => Some(Self::Sm3(Sm3::new())),
            _ => None,
        }
    }

    fn update(&mut self, data: &[u8]) {
        match self {
            Self::Md5(hash) => hash.update(data),
            Self::Sha1(hash) => hash.update(data),
            Self::Sha224(hash) => hash.update(data),
            Self::Sha256(hash) => hash.update(data),
            Self::Sha384(hash) => hash.update(data),
            Self::Sha512(hash) => hash.update(data),
            Self::Sha512_224(hash) => hash.update(data),
            Self::Sha512_256(hash) => hash.update(data),
            Self::Ripemd160(hash) => hash.update(data),
            Self::Sm3(hash) => hash.update(data),
        }
    }

    fn digest(&self) -> Vec<u8> {
        match self {
            Self::Md5(hash) => hash.clone().finalize().to_vec(),
            Self::Sha1(hash) => hash.clone().finalize().to_vec(),
            Self::Sha224(hash) => hash.clone().finalize().to_vec(),
            Self::Sha256(hash) => hash.clone().finalize().to_vec(),
            Self::Sha384(hash) => hash.clone().finalize().to_vec(),
            Self::Sha512(hash) => hash.clone().finalize().to_vec(),
            Self::Sha512_224(hash) => hash.clone().finalize().to_vec(),
            Self::Sha512_256(hash) => hash.clone().finalize().to_vec(),
            Self::Ripemd160(hash) => hash.clone().finalize().to_vec(),
            Self::Sm3(hash) => hash.clone().finalize().to_vec(),
        }
    }

    fn name(&self) -> &'static str {
        match self {
            Self::Md5(_) => "md5",
            Self::Sha1(_) => "sha1",
            Self::Sha224(_) => "sha224",
            Self::Sha256(_) => "sha256",
            Self::Sha384(_) => "sha384",
            Self::Sha512(_) => "sha512",
            Self::Sha512_224(_) => "sha512_224",
            Self::Sha512_256(_) => "sha512_256",
            Self::Ripemd160(_) => "ripemd160",
            Self::Sm3(_) => "sm3",
        }
    }

    fn block_size(&self) -> c_int {
        match self {
            Self::Md5(_) | Self::Sha1(_) | Self::Sha224(_) | Self::Sha256(_) => 64,
            Self::Sha384(_) | Self::Sha512(_) | Self::Sha512_224(_) | Self::Sha512_256(_) => 128,
            Self::Ripemd160(_) | Self::Sm3(_) => 64,
        }
    }

    fn digest_size(&self) -> c_int {
        match self {
            Self::Md5(_) => 16,
            Self::Sha1(_) => 20,
            Self::Sha224(_) => 28,
            Self::Sha256(_) => 32,
            Self::Sha384(_) => 48,
            Self::Sha512(_) => 64,
            Self::Sha512_224(_) => 28,
            Self::Sha512_256(_) => 32,
            Self::Ripemd160(_) => 20,
            Self::Sm3(_) => 32,
        }
    }
}

#[derive(Clone)]
struct Md5Sha1Hmac {
    inner_md5: Md5,
    inner_sha1: Sha1,
    outer_md5: Md5,
    outer_sha1: Sha1,
}

impl Md5Sha1Hmac {
    fn new(key: &[u8]) -> Self {
        let normalized_key = if key.len() > 64 {
            let md5 = Md5::digest(key);
            let sha1 = Sha1::digest(key);
            let mut result = Vec::with_capacity(36);
            result.extend_from_slice(&md5);
            result.extend_from_slice(&sha1);
            result
        } else {
            key.to_vec()
        };
        let mut key_block = [0u8; 64];
        if normalized_key.len() <= 64 {
            key_block[..normalized_key.len()].copy_from_slice(&normalized_key);
        }
        let mut inner_pad = key_block;
        let mut outer_pad = key_block;
        for byte in &mut inner_pad {
            *byte ^= 0x36;
        }
        for byte in &mut outer_pad {
            *byte ^= 0x5c;
        }
        let mut inner_md5 = Md5::new();
        inner_md5.update(inner_pad);
        let mut inner_sha1 = Sha1::new();
        inner_sha1.update(inner_pad);
        let mut outer_md5 = Md5::new();
        outer_md5.update(outer_pad);
        let mut outer_sha1 = Sha1::new();
        outer_sha1.update(outer_pad);
        Self {
            inner_md5,
            inner_sha1,
            outer_md5,
            outer_sha1,
        }
    }

    fn update(&mut self, data: &[u8]) {
        self.inner_md5.update(data);
        self.inner_sha1.update(data);
    }

    fn digest(&self) -> [u8; 36] {
        let mut inner_digest = [0u8; 36];
        inner_digest[..16].copy_from_slice(&self.inner_md5.clone().finalize());
        inner_digest[16..].copy_from_slice(&self.inner_sha1.clone().finalize());
        let mut outer_md5 = self.outer_md5.clone();
        outer_md5.update(inner_digest);
        let mut outer_sha1 = self.outer_sha1.clone();
        outer_sha1.update(inner_digest);
        let mut digest = [0u8; 36];
        digest[..16].copy_from_slice(&outer_md5.finalize());
        digest[16..].copy_from_slice(&outer_sha1.finalize());
        digest
    }
}

fn pbkdf2_for<D: hmac::EagerHash>(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    pbkdf2::pbkdf2::<Hmac<D>>(password, salt, iterations, result)
}

macro_rules! pbkdf2_simple {
    ($function:ident, $digest:ty) => {
        fn $function(
            password: &[u8],
            salt: &[u8],
            iterations: u32,
            result: &mut [u8],
        ) -> Result<(), hmac::digest::InvalidLength> {
            pbkdf2::pbkdf2::<SimpleHmac<$digest>>(password, salt, iterations, result)
        }
    };
}

pbkdf2_simple!(pbkdf2_blake2b, Blake2b512);
pbkdf2_simple!(pbkdf2_blake2s, Blake2s256);
pbkdf2_simple!(pbkdf2_sha3_224, Sha3_224);
pbkdf2_simple!(pbkdf2_sha3_256, Sha3_256);
pbkdf2_simple!(pbkdf2_sha3_384, Sha3_384);
pbkdf2_simple!(pbkdf2_sha3_512, Sha3_512);

fn hmac_md5_sha1(key: &[u8], first: &[u8], second: &[u8]) -> [u8; 36] {
    let mut mac = Md5Sha1Hmac::new(key);
    mac.update(first);
    mac.update(second);
    mac.digest()
}

fn pbkdf2_md5_sha1(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    for (index, output) in result.chunks_mut(36).enumerate() {
        let counter = ((index as u32).wrapping_add(1)).to_be_bytes();
        let mut value = hmac_md5_sha1(password, salt, &counter);
        let mut block = value;
        for _ in 1..iterations {
            value = hmac_md5_sha1(password, &value, &[]);
            for (dst, byte) in block.iter_mut().zip(value) {
                *dst ^= byte;
            }
        }
        output.copy_from_slice(&block[..output.len()]);
    }
    Ok(())
}

type Pbkdf2Algorithm =
    fn(&[u8], &[u8], u32, &mut [u8]) -> Result<(), hmac::digest::InvalidLength>;

enum Pbkdf2Error {
    Unsupported(String),
    Invalid(&'static str),
}

fn pbkdf2_parameters(
    hash_name: &str,
    password_length: usize,
    salt_length: usize,
    iterations: i64,
    dklen: Option<i64>,
) -> Result<(Pbkdf2Algorithm, u32, usize), Pbkdf2Error> {
    let (digest_size, algorithm): (usize, Pbkdf2Algorithm) = match hash_name {
        "md5" => (16, pbkdf2_for::<Md5>),
        "blake2b" => (64, pbkdf2_blake2b),
        "blake2s" => (32, pbkdf2_blake2s),
        "md5-sha1" => (36, pbkdf2_md5_sha1),
        "sha1" => (20, pbkdf2_for::<Sha1>),
        "sha224" => (28, pbkdf2_for::<Sha224>),
        "sha256" => (32, pbkdf2_for::<Sha256>),
        "sha384" => (48, pbkdf2_for::<Sha384>),
        "sha512" => (64, pbkdf2_for::<Sha512>),
        "sha512_224" => (28, pbkdf2_for::<Sha512_224>),
        "sha512_256" => (32, pbkdf2_for::<Sha512_256>),
        "sha3_224" => (28, pbkdf2_sha3_224),
        "sha3_256" => (32, pbkdf2_sha3_256),
        "sha3_384" => (48, pbkdf2_sha3_384),
        "sha3_512" => (64, pbkdf2_sha3_512),
        "ripemd160" => (20, pbkdf2_for::<Ripemd160>),
        "sm3" => (32, pbkdf2_for::<Sm3>),
        "shake_128" | "shake_256" => {
            return Err(Pbkdf2Error::Invalid(
                "[Provider routines] xof digests not allowed",
            ));
        }
        _ => return Err(Pbkdf2Error::Unsupported(hash_name.to_owned())),
    };
    if password_length > i32::MAX as usize {
        return Err(Pbkdf2Error::Invalid("password is too long."));
    }
    if salt_length > i32::MAX as usize {
        return Err(Pbkdf2Error::Invalid("salt is too long."));
    }
    if iterations < 1 {
        return Err(Pbkdf2Error::Invalid(
            "iteration value must be greater than 0.",
        ));
    }
    if iterations > i32::MAX as i64 {
        return Err(Pbkdf2Error::Invalid("iteration value is too great."));
    }
    let length = match dklen {
        None => digest_size,
        Some(length) if length < 1 => {
            return Err(Pbkdf2Error::Invalid("key length must be greater than 0."));
        }
        Some(length) if length > i32::MAX as i64 => {
            return Err(Pbkdf2Error::Invalid("key length is too great."));
        }
        Some(length) => length as usize,
    };
    Ok((algorithm, iterations as u32, length))
}

fn scrypt_parameters(
    password_length: usize,
    salt_length: usize,
    n: i64,
    r: i64,
    p: i64,
    maxmem: i64,
    dklen: i64,
) -> Result<(scrypt::Params, usize), &'static str> {
    if password_length > i32::MAX as usize {
        return Err("password is too long");
    }
    if salt_length > i32::MAX as usize {
        return Err("salt is too long");
    }
    if n < 0 || r < 0 || p < 0 {
        return Err("Cannot convert negative int");
    }
    let n = n as u64;
    let r = r as u64;
    let p = p as u64;
    if n < 2 || !n.is_power_of_two() {
        return Err("n must be a power of 2");
    }
    if maxmem < 0 || maxmem > i32::MAX as i64 {
        return Err("maxmem must be positive and at most 2147483647");
    }
    if dklen < 1 || dklen > i32::MAX as i64 {
        return Err("dklen must be at least 1 and at most 2147483647");
    }
    if r > u32::MAX as u64 || p > u32::MAX as u64 {
        return Err("[digital envelope routines] parameter too large");
    }
    if r == 0 || p == 0 {
        return Err("invalid parameter combination for n, r, p, and maxmem");
    }
    if p > ((1 << 30) - 1) / r {
        return Err("[digital envelope routines] memory limit exceeded");
    }
    if r <= 3 && n >= 1u64 << (16 * r as u32) {
        return Err("[digital envelope routines] memory limit exceeded");
    }
    let block_memory = 128u128 * r as u128 * p as u128;
    if block_memory > i32::MAX as u128 {
        return Err("[digital envelope routines] memory limit exceeded");
    }
    let memory = 128u128
        .checked_mul(r as u128)
        .and_then(|value| {
            (n as u128)
                .checked_add(p as u128)
                .and_then(|sum| sum.checked_add(2))
                .and_then(|sum| value.checked_mul(sum))
        })
        .ok_or("[digital envelope routines] memory limit exceeded")?;
    let limit = if maxmem == 0 {
        32u128 * 1024 * 1024
    } else {
        maxmem as u128
    };
    if memory > limit {
        return Err("[digital envelope routines] memory limit exceeded");
    }
    let log_n = n.trailing_zeros() as u8;
    let params = scrypt::Params::new(log_n, r as u32, p as u32)
        .map_err(|_| "invalid parameter combination for n, r, p, and maxmem")?;
    Ok((params, dklen as usize))
}

#[repr(C)]
struct HashObject {
    base: PyObject,
    state: *mut HashState,
}

fn acquire_buffer(object: *mut PyObject) -> Option<Buffer> {
    Buffer::acquire(unsafe { Borrowed::from_raw(object) }).ok()
}

fn copy_checked(buffer: &Buffer, message: &'static CStr) -> Option<Vec<u8>> {
    let bytes = buffer.as_bytes();
    if bytes.len() > i32::MAX as usize {
        unsafe { PyErr_SetString(PyExc_OverflowError, message.as_ptr()) };
        return None;
    }
    let mut owned = Vec::new();
    if owned.try_reserve_exact(bytes.len()).is_err() {
        unsafe { PyErr_NoMemory() };
        return None;
    }
    owned.extend_from_slice(bytes);
    Some(owned)
}

unsafe fn tuple_item(args: *mut PyObject, index: Py_ssize_t, count: Py_ssize_t) -> Option<*mut PyObject> {
    if unsafe { PyTuple_Size(args) } != count {
        unsafe { PyErr_SetString(PyExc_TypeError, c"invalid number of arguments".as_ptr()) };
        return None;
    }
    let item = unsafe { PyTuple_GetItem(args, index) };
    if item.is_null() { None } else { Some(item) }
}

unsafe fn read_name(object: *mut PyObject) -> Option<String> {
    let mut size: Py_ssize_t = 0;
    let name = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if name.is_null() {
        return None;
    }
    if size < 0 {
        unsafe { PyErr_SetString(PyExc_ValueError, c"digest name has a negative encoded length".as_ptr()) };
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(name.cast::<u8>(), size as usize) };
    Some(String::from_utf8_lossy(bytes).into_owned())
}

unsafe fn read_long(object: *mut PyObject) -> Option<i64> {
    let value = unsafe { PyLong_AsLongLong(object) };
    if unsafe { !PyErr_Occurred().is_null() } {
        return None;
    }
    Some(value)
}

fn is_none(object: *mut PyObject) -> bool {
    object.cast::<c_void>() == ptr::addr_of_mut!(_Py_NoneStruct).cast::<c_void>()
}

unsafe fn set_value_error(message: &str) {
    let error = unsafe {
        PyUnicode_FromStringAndSize(message.as_ptr().cast::<c_char>(), message.len() as Py_ssize_t)
    };
    if error.is_null() {
        return;
    }
    unsafe { PyErr_SetObject(PyExc_ValueError, error) };
    unsafe { Py_DecRef(error) };
}

fn normalize_digest_name(name: &str) -> String {
    match name.to_ascii_lowercase().as_str() {
        "sha-1" => "sha1".to_owned(),
        "sha-224" => "sha224".to_owned(),
        "sha-256" => "sha256".to_owned(),
        "sha-384" => "sha384".to_owned(),
        "sha-512" => "sha512".to_owned(),
        "sha512-224" => "sha512_224".to_owned(),
        "sha512-256" => "sha512_256".to_owned(),
        "sha3-224" => "sha3_224".to_owned(),
        "sha3-256" => "sha3_256".to_owned(),
        "sha3-384" => "sha3_384".to_owned(),
        "sha3-512" => "sha3_512".to_owned(),
        "shake-128" => "shake_128".to_owned(),
        "shake-256" => "shake_256".to_owned(),
        "ripemd-160" => "ripemd160".to_owned(),
        "blake2b512" | "blake2b-512" => "blake2b".to_owned(),
        "blake2s256" | "blake2s-256" => "blake2s".to_owned(),
        other => other.to_owned(),
    }
}

unsafe fn object_state(object: *mut PyObject) -> Option<*mut HashState> {
    let hash_object = unsafe { &mut *object.cast::<HashObject>() };
    if hash_object.state.is_null() {
        unsafe { PyErr_SetString(PyExc_ValueError, c"hash object has no state".as_ptr()) };
        return None;
    }
    Some(hash_object.state)
}

fn allocate_hash(type_object: *mut PyTypeObject, state: HashState) -> *mut PyObject {
    let object = unsafe { PyType_GenericAlloc(type_object, 0) };
    if object.is_null() {
        return ptr::null_mut();
    }
    let pointer = Box::into_raw(Box::new(state));
    unsafe { (*object.cast::<HashObject>()).state = pointer };
    object
}

fn return_bytes(bytes: &[u8]) -> *mut PyObject {
    into_return(BytesWriter::copy_of(bytes))
}

unsafe extern "C" fn new_hash(_module: *mut PyObject, args: *mut PyObject) -> *mut PyObject {
    let Some(name_object) = (unsafe { tuple_item(args, 0, 2) }) else {
        return ptr::null_mut();
    };
    let Some(data_object) = (unsafe { tuple_item(args, 1, 2) }) else {
        return ptr::null_mut();
    };
    let Some(name) = (unsafe { read_name(name_object) }) else {
        return ptr::null_mut();
    };
    let Some(mut state) = HashState::new(&normalize_digest_name(&name)) else {
        unsafe { PyErr_SetString(PyExc_ValueError, c"unsupported hash algorithm".as_ptr()) };
        return ptr::null_mut();
    };
    let Some(data) = (unsafe { acquire_buffer(data_object) }) else {
        return ptr::null_mut();
    };
    state.update(data.as_bytes());

    let type_object = unsafe { PyObject_GetAttrString(_module, c"HASH".as_ptr()) };
    if type_object.is_null() {
        return ptr::null_mut();
    }
    let result = allocate_hash(type_object.cast::<PyTypeObject>(), state);
    unsafe { Py_DecRef(type_object) };
    result
}

unsafe extern "C" fn pbkdf2_hmac(_module: *mut PyObject, args: *mut PyObject) -> *mut PyObject {
    let Some(name_object) = (unsafe { tuple_item(args, 0, 5) }) else {
        return ptr::null_mut();
    };
    let Some(password_object) = (unsafe { tuple_item(args, 1, 5) }) else {
        return ptr::null_mut();
    };
    let Some(salt_object) = (unsafe { tuple_item(args, 2, 5) }) else {
        return ptr::null_mut();
    };
    let Some(iterations_object) = (unsafe { tuple_item(args, 3, 5) }) else {
        return ptr::null_mut();
    };
    let Some(dklen_object) = (unsafe { tuple_item(args, 4, 5) }) else {
        return ptr::null_mut();
    };
    let Some(name) = (unsafe { read_name(name_object) }) else {
        return ptr::null_mut();
    };
    let normalized = normalize_digest_name(&name);
    let Some(iterations) = (unsafe { read_long(iterations_object) }) else {
        return ptr::null_mut();
    };
    let dklen = if is_none(dklen_object) {
        None
    } else {
        let Some(value) = (unsafe { read_long(dklen_object) }) else {
            return ptr::null_mut();
        };
        Some(value)
    };
    let Some(password_view) = (unsafe { acquire_buffer(password_object) }) else {
        return ptr::null_mut();
    };
    let password_length = password_view.as_bytes().len();
    let Some(salt_view) = (unsafe { acquire_buffer(salt_object) }) else {
        return ptr::null_mut();
    };
    let salt_length = salt_view.as_bytes().len();
    let (algorithm, iterations, length) = match pbkdf2_parameters(
        &normalized,
        password_length,
        salt_length,
        iterations,
        dklen,
    ) {
        Ok(parameters) => parameters,
        Err(Pbkdf2Error::Unsupported(digest)) => {
            let message =
                format!("[digital envelope routines] unsupported hash algorithm {digest}");
            unsafe { set_value_error(&message) };
            return ptr::null_mut();
        }
        Err(Pbkdf2Error::Invalid(message)) => {
            unsafe { set_value_error(message) };
            return ptr::null_mut();
        }
    };
    let Some(password) = copy_checked(&password_view, c"password is too long.") else {
        return ptr::null_mut();
    };
    let Some(salt) = copy_checked(&salt_view, c"salt is too long.") else {
        return ptr::null_mut();
    };
    let mut result = Vec::new();
    if result.try_reserve_exact(length).is_err() {
        unsafe { PyErr_SetString(PyExc_OverflowError, c"key length is too great.".as_ptr()) };
        return ptr::null_mut();
    }
    result.resize(length, 0);
    if algorithm(&password, &salt, iterations, &mut result).is_err() {
        unsafe { PyErr_SetString(PyExc_ValueError, c"invalid password length".as_ptr()) };
        return ptr::null_mut();
    }
    return_bytes(&result)
}

unsafe extern "C" fn scrypt_derive(_module: *mut PyObject, args: *mut PyObject) -> *mut PyObject {
    let mut objects = [ptr::null_mut(); 7];
    for (index, slot) in objects.iter_mut().enumerate() {
        let Some(object) = (unsafe { tuple_item(args, index as Py_ssize_t, 7) }) else {
            return ptr::null_mut();
        };
        *slot = object;
    }
    let [password_object, salt_object, n_object, r_object, p_object, maxmem_object, dklen_object] =
        objects;
    let Some(n) = (unsafe { read_long(n_object) }) else {
        return ptr::null_mut();
    };
    let Some(r) = (unsafe { read_long(r_object) }) else {
        return ptr::null_mut();
    };
    let Some(p) = (unsafe { read_long(p_object) }) else {
        return ptr::null_mut();
    };
    let Some(maxmem) = (unsafe { read_long(maxmem_object) }) else {
        return ptr::null_mut();
    };
    let Some(dklen) = (unsafe { read_long(dklen_object) }) else {
        return ptr::null_mut();
    };
    let Some(password_view) = (unsafe { acquire_buffer(password_object) }) else {
        return ptr::null_mut();
    };
    let password_length = password_view.as_bytes().len();
    let Some(salt_view) = (unsafe { acquire_buffer(salt_object) }) else {
        return ptr::null_mut();
    };
    let salt_length = salt_view.as_bytes().len();
    let (params, length) = match scrypt_parameters(
        password_length,
        salt_length,
        n,
        r,
        p,
        maxmem,
        dklen,
    ) {
        Ok(parameters) => parameters,
        Err(message) => {
            unsafe { set_value_error(message) };
            return ptr::null_mut();
        }
    };
    let Some(password) = copy_checked(&password_view, c"password is too long") else {
        return ptr::null_mut();
    };
    let Some(salt) = copy_checked(&salt_view, c"salt is too long") else {
        return ptr::null_mut();
    };
    let mut output = Vec::new();
    if output.try_reserve_exact(length).is_err() {
        unsafe { PyErr_SetString(PyExc_OverflowError, c"dklen is too large".as_ptr()) };
        return ptr::null_mut();
    }
    output.resize(length, 0);
    if scrypt::scrypt(&password, &salt, &params, &mut output).is_err() {
        unsafe { PyErr_SetString(PyExc_ValueError, c"invalid scrypt output length".as_ptr()) };
        return ptr::null_mut();
    }
    return_bytes(&output)
}

unsafe extern "C" fn update(object: *mut PyObject, data_object: *mut PyObject) -> *mut PyObject {
    let Some(data) = (unsafe { acquire_buffer(data_object) }) else {
        return ptr::null_mut();
    };
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    unsafe { &mut *state }.update(data.as_bytes());
    Owned::none().into_raw()
}

unsafe extern "C" fn copy_hash(object: *mut PyObject, _unused: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    let type_object = unsafe { PyObject_Type(object) };
    if type_object.is_null() {
        return ptr::null_mut();
    }
    let result = allocate_hash(type_object.cast::<PyTypeObject>(), unsafe { &*state }.clone());
    unsafe { Py_DecRef(type_object) };
    result
}

unsafe extern "C" fn digest(object: *mut PyObject, _unused: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    return_bytes(&unsafe { &*state }.digest())
}

unsafe extern "C" fn hexdigest(object: *mut PyObject, _unused: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    let digest = unsafe { &*state }.digest();
    let mut output = Vec::with_capacity(digest.len() * 2);
    for byte in digest {
        output.push(HEX[(byte >> 4) as usize]);
        output.push(HEX[(byte & 0x0f) as usize]);
    }
    if output.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyUnicode_FromStringAndSize(output.as_ptr().cast::<c_char>(), output.len() as Py_ssize_t) }
}

unsafe extern "C" fn get_name(object: *mut PyObject, _closure: *mut c_void) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    let name = unsafe { &*state }.name();
    unsafe { PyUnicode_FromStringAndSize(name.as_ptr().cast::<c_char>(), name.len() as Py_ssize_t) }
}

unsafe extern "C" fn get_digest_size(object: *mut PyObject, _closure: *mut c_void) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    unsafe { PyLong_FromLong(unsafe { &*state }.digest_size() as c_long) }
}

unsafe extern "C" fn get_block_size(object: *mut PyObject, _closure: *mut c_void) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    unsafe { PyLong_FromLong(unsafe { &*state }.block_size() as c_long) }
}

unsafe extern "C" fn hash_repr(object: *mut PyObject) -> *mut PyObject {
    let Some(state) = (unsafe { object_state(object) }) else {
        return ptr::null_mut();
    };
    let name = match unsafe { &*state }.name() {
        "md5" => c"md5".as_ptr(),
        "sha1" => c"sha1".as_ptr(),
        "sha224" => c"sha224".as_ptr(),
        "sha256" => c"sha256".as_ptr(),
        "sha384" => c"sha384".as_ptr(),
        "sha512" => c"sha512".as_ptr(),
        "sha512_224" => c"sha512_224".as_ptr(),
        "sha512_256" => c"sha512_256".as_ptr(),
        "ripemd160" => c"ripemd160".as_ptr(),
        _ => c"sm3".as_ptr(),
    };
    unsafe { PyUnicode_FromFormat(c"<%s HASH object @ %p>".as_ptr(), name, object.cast::<c_void>()) }
}

unsafe extern "C" fn dealloc(object: *mut PyObject) {
    let type_object = unsafe { (*object).ob_type };
    let hash_object = unsafe { &mut *object.cast::<HashObject>() };
    if !hash_object.state.is_null() {
        unsafe { drop(Box::from_raw(hash_object.state)) };
        hash_object.state = ptr::null_mut();
    }
    unsafe { PyObject_Free(object.cast::<c_void>()) };
    // Generic allocation owns a heap-type reference until the object is freed.
    unsafe { Py_DecRef(type_object.cast::<PyObject>()) }
}

unsafe extern "C" fn unhashable(object: *mut PyObject) -> isize {
    unsafe { PyObject_HashNotImplemented(object) }
}

static HASH_METHODS: [PyMethodDef; 5] = [
    single_argument(c"update", update, c"Update the digest with bytes-like data."),
    noargs(c"copy", copy_hash, c"Return a copy of the hash object."),
    noargs(c"digest", digest, c"Return the digest of the data passed to update()."),
    noargs(
        c"hexdigest",
        hexdigest,
        c"Return the hexadecimal digest of the data passed to update().",
    ),
    method_table_end(),
];

const fn read_only(
    name: &'static CStr,
    get: unsafe extern "C" fn(*mut PyObject, *mut c_void) -> *mut PyObject,
    doc: &'static CStr,
) -> PyGetSetDef {
    PyGetSetDef {
        name: name.as_ptr(),
        get: Some(get),
        set: None,
        doc: doc.as_ptr(),
        closure: ptr::null_mut(),
    }
}

static HASH_GETSET: [PyGetSetDef; 4] = [
    read_only(c"name", get_name, c"Canonical name of this digest algorithm."),
    read_only(c"digest_size", get_digest_size, c"Size of the digest in bytes."),
    read_only(
        c"block_size",
        get_block_size,
        c"Internal block size of the hash algorithm in bytes.",
    ),
    PyGetSetDef {
        name: ptr::null(),
        get: None,
        set: None,
        doc: ptr::null(),
        closure: ptr::null_mut(),
    },
];

static HASH_TYPE_SLOTS: [PyType_Slot; 6] = [
    PyType_Slot { slot: Py_tp_dealloc, pfunc: dealloc as *const () as *mut c_void },
    PyType_Slot { slot: Py_tp_getset, pfunc: HASH_GETSET.as_ptr() as *mut c_void },
    PyType_Slot { slot: Py_tp_hash, pfunc: unhashable as *const () as *mut c_void },
    PyType_Slot { slot: Py_tp_methods, pfunc: HASH_METHODS.as_ptr() as *mut c_void },
    PyType_Slot { slot: Py_tp_repr, pfunc: hash_repr as *const () as *mut c_void },
    PyType_Slot { slot: 0, pfunc: ptr::null_mut() },
];

static HASH_TYPE_SPEC: PyType_Spec = PyType_Spec {
    name: c"_hashlib_rs.HASH".as_ptr(),
    basicsize: size_of::<HashObject>() as c_int,
    itemsize: 0,
    flags: Py_TPFLAGS_DEFAULT | Py_TPFLAGS_DISALLOW_INSTANTIATION | Py_TPFLAGS_IMMUTABLETYPE,
    slots: HASH_TYPE_SLOTS.as_ptr().cast_mut(),
};

unsafe extern "C" fn exec_module(module: *mut PyObject) -> c_int {
    let hash_type = unsafe { PyType_FromSpec(ptr::addr_of!(HASH_TYPE_SPEC).cast_mut()) };
    if hash_type.is_null() {
        return -1;
    }
    if unsafe { PyModule_AddObject(module, c"HASH".as_ptr(), hash_type) } != 0 {
        unsafe { Py_DecRef(hash_type) };
        return -1;
    }
    0
}

static MODULE_SLOTS: [PyModuleDef_Slot; 3] = [
    PyModuleDef_Slot { slot: Py_mod_exec, value: exec_module as *const () as *mut c_void },
    PER_INTERPRETER_GIL_SLOT,
    PyModuleDef_Slot { slot: 0, value: ptr::null_mut() },
];

static MODULE_METHODS: [PyMethodDef; 4] = [
    varargs(c"new", new_hash, c"Create a Rust-backed fixed-output digest object."),
    varargs(c"pbkdf2_hmac", pbkdf2_hmac, c"Derive a key with PBKDF2-HMAC."),
    varargs(c"scrypt", scrypt_derive, c"Derive a key with scrypt."),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_hashlib_rs",
    c"Rust-backed digest, PBKDF2, and scrypt implementations used by hashlib.",
    &MODULE_METHODS,
)
.with_slots(&MODULE_SLOTS);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__hashlib_rs() -> *mut PyObject {
    MODULE.init()
}
