use blake2::{Blake2b512, Blake2s256};
use hmac::{Hmac, KeyInit, Mac, SimpleHmac};
use md5::Md5;
use pyo3::exceptions::{PyOverflowError, PyTypeError, PyValueError};
use pyo3::create_exception;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PySlice, PyString};
use ripemd::Ripemd160;
use sha1::{Digest, Sha1};
use sha2::{Sha224, Sha256, Sha384, Sha512, Sha512_224, Sha512_256};
use sha3::{Sha3_224, Sha3_256, Sha3_384, Sha3_512};
use sm3::Sm3;

create_exception!(_hashlib_graviola, UnsupportedDigestmodError, PyValueError);

fn unsupported_digestmod(name: &str) -> PyErr {
    UnsupportedDigestmodError::new_err(format!(
        "[digital envelope routines] unsupported hash algorithm {name}"
    ))
}

fn invalid_key_length(_: hmac::digest::InvalidLength) -> PyErr {
    PyValueError::new_err("invalid key length")
}

#[derive(Clone)]
enum HmacState {
    Blake2b(SimpleHmac<Blake2b512>),
    Blake2s(SimpleHmac<Blake2s256>),
    Md5(Hmac<Md5>),
    Md5Sha1(Md5Sha1Hmac),
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
    fn new(name: &str, key: &[u8]) -> PyResult<Self> {
        match name {
            "blake2b" => SimpleHmac::<Blake2b512>::new_from_slice(key)
                .map(Self::Blake2b)
                .map_err(invalid_key_length),
            "blake2s" => SimpleHmac::<Blake2s256>::new_from_slice(key)
                .map(Self::Blake2s)
                .map_err(invalid_key_length),
            "md5" => Hmac::<Md5>::new_from_slice(key)
                .map(Self::Md5)
                .map_err(invalid_key_length),
            "md5-sha1" => Ok(Self::Md5Sha1(Md5Sha1Hmac::new(key))),
            "sha1" => Hmac::<Sha1>::new_from_slice(key)
                .map(Self::Sha1)
                .map_err(invalid_key_length),
            "sha224" => Hmac::<Sha224>::new_from_slice(key)
                .map(Self::Sha224)
                .map_err(invalid_key_length),
            "sha256" => Hmac::<Sha256>::new_from_slice(key)
                .map(Self::Sha256)
                .map_err(invalid_key_length),
            "sha384" => Hmac::<Sha384>::new_from_slice(key)
                .map(Self::Sha384)
                .map_err(invalid_key_length),
            "sha512" => Hmac::<Sha512>::new_from_slice(key)
                .map(Self::Sha512)
                .map_err(invalid_key_length),
            "sha512_224" => Hmac::<Sha512_224>::new_from_slice(key)
                .map(Self::Sha512_224)
                .map_err(invalid_key_length),
            "sha512_256" => Hmac::<Sha512_256>::new_from_slice(key)
                .map(Self::Sha512_256)
                .map_err(invalid_key_length),
            "sha3_224" => SimpleHmac::<Sha3_224>::new_from_slice(key)
                .map(Self::Sha3_224)
                .map_err(invalid_key_length),
            "sha3_256" => SimpleHmac::<Sha3_256>::new_from_slice(key)
                .map(Self::Sha3_256)
                .map_err(invalid_key_length),
            "sha3_384" => SimpleHmac::<Sha3_384>::new_from_slice(key)
                .map(Self::Sha3_384)
                .map_err(invalid_key_length),
            "sha3_512" => SimpleHmac::<Sha3_512>::new_from_slice(key)
                .map(Self::Sha3_512)
                .map_err(invalid_key_length),
            "ripemd160" => Hmac::<Ripemd160>::new_from_slice(key)
                .map(Self::Ripemd160)
                .map_err(invalid_key_length),
            "sm3" => Hmac::<Sm3>::new_from_slice(key)
                .map(Self::Sm3)
                .map_err(invalid_key_length),
            _ => Err(unsupported_digestmod(name)),
        }
    }

    fn update(&mut self, data: &[u8]) {
        match self {
            Self::Blake2b(mac) => mac.update(data),
            Self::Blake2s(mac) => mac.update(data),
            Self::Md5(mac) => mac.update(data),
            Self::Md5Sha1(mac) => mac.update(data),
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
            Self::Blake2b(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Blake2s(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Md5(mac) => mac.clone().finalize().into_bytes().to_vec(),
            Self::Md5Sha1(mac) => mac.digest().to_vec(),
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
            let mut normalized_key = Vec::with_capacity(36);
            normalized_key.extend_from_slice(&md5);
            normalized_key.extend_from_slice(&sha1);
            normalized_key
        } else {
            key.to_vec()
        };
        let mut key_block = [0u8; 64];
        key_block[..normalized_key.len()].copy_from_slice(&normalized_key);
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

#[pyclass(module = "_hashlib_graviola", name = "HMAC", immutable_type)]
#[derive(Clone)]
struct HmacObject {
    algorithm: &'static str,
    state: HmacState,
    digest_size: usize,
    block_size: usize,
}

impl HmacObject {
    fn new(algorithm: &'static str, key: &[u8]) -> PyResult<Self> {
        let state = HmacState::new(algorithm, key)?;
        let (digest_size, block_size) = match algorithm {
            "blake2b" => (64, 128),
            "blake2s" => (32, 64),
            "md5" => (16, 64),
            "md5-sha1" => (36, 64),
            "sha1" => (20, 64),
            "sha224" => (28, 64),
            "sha256" => (32, 64),
            "sha384" => (48, 128),
            "sha512" => (64, 128),
            "sha512_224" => (28, 128),
            "sha512_256" => (32, 128),
            "sha3_224" => (28, 144),
            "sha3_256" => (32, 136),
            "sha3_384" => (48, 104),
            "sha3_512" => (64, 72),
            "ripemd160" => (20, 64),
            "sm3" => (32, 64),
            _ => return Err(unsupported_digestmod(algorithm)),
        };
        Ok(Self {
            algorithm,
            state,
            digest_size,
            block_size,
        })
    }
}

#[pymethods]
impl HmacObject {
    #[getter]
    fn name(&self) -> String {
        format!("hmac-{}", self.algorithm)
    }

    #[getter]
    fn digest_size(&self) -> usize {
        self.digest_size
    }

    #[getter]
    fn block_size(&self) -> usize {
        self.block_size
    }

    fn update(&mut self, py: Python<'_>, data: &Bound<'_, PyAny>) -> PyResult<()> {
        let state = &mut self.state;
        update_buffer(py, data, |bytes| py.detach(|| state.update(bytes)))
    }

    fn copy(&self) -> Self {
        self.clone()
    }

    fn digest(&self) -> Vec<u8> {
        self.state.digest()
    }

    fn hexdigest(&self) -> String {
        hex_digest(&self.state.digest())
    }

    fn __repr__(&self) -> String {
        format!("<{} HMAC object @ {:p}>", self.algorithm, self)
    }
}

#[derive(Clone)]
enum ExtraDigestState {
    Sha512_224(Sha512_224),
    Sha512_256(Sha512_256),
    Ripemd160(Ripemd160),
    Sm3(Sm3),
}

impl ExtraDigestState {
    fn new(name: &str) -> Option<Self> {
        match name {
            "sha512_224" => Some(Self::Sha512_224(Sha512_224::new())),
            "sha512_256" => Some(Self::Sha512_256(Sha512_256::new())),
            "ripemd160" => Some(Self::Ripemd160(Ripemd160::new())),
            "sm3" => Some(Self::Sm3(Sm3::new())),
            _ => None,
        }
    }

    fn update(&mut self, data: &[u8]) {
        match self {
            Self::Sha512_224(state) => state.update(data),
            Self::Sha512_256(state) => state.update(data),
            Self::Ripemd160(state) => state.update(data),
            Self::Sm3(state) => state.update(data),
        }
    }

    fn digest(&self) -> Vec<u8> {
        match self {
            Self::Sha512_224(state) => state.clone().finalize().to_vec(),
            Self::Sha512_256(state) => state.clone().finalize().to_vec(),
            Self::Ripemd160(state) => state.clone().finalize().to_vec(),
            Self::Sm3(state) => state.clone().finalize().to_vec(),
        }
    }
}

#[pyclass(module = "_hashlib_graviola", name = "HASH")]
#[derive(Clone)]
struct HashObject {
    algorithm: &'static str,
    state: ExtraDigestState,
}

impl HashObject {
    fn new(algorithm: &'static str) -> PyResult<Self> {
        let state = ExtraDigestState::new(algorithm)
            .ok_or_else(|| PyValueError::new_err("unsupported hash algorithm"))?;
        Ok(Self { algorithm, state })
    }

    fn metadata(&self) -> (usize, usize) {
        match self.algorithm {
            "sha512_224" => (28, 128),
            "sha512_256" => (32, 128),
            "ripemd160" => (20, 64),
            "sm3" => (32, 64),
            _ => unreachable!(),
        }
    }
}

#[pymethods]
impl HashObject {
    #[getter]
    fn name(&self) -> &'static str {
        self.algorithm
    }

    #[getter]
    fn digest_size(&self) -> usize {
        self.metadata().0
    }

    #[getter]
    fn block_size(&self) -> usize {
        self.metadata().1
    }

    fn update(&mut self, py: Python<'_>, data: &Bound<'_, PyAny>) -> PyResult<()> {
        let state = &mut self.state;
        update_buffer(py, data, |bytes| py.detach(|| state.update(bytes)))
    }

    fn copy(&self) -> Self {
        self.clone()
    }

    fn digest(&self) -> Vec<u8> {
        self.state.digest()
    }

    fn hexdigest(&self) -> String {
        hex_digest(&self.state.digest())
    }

    fn __repr__(&self) -> String {
        format!("<{} HASH object @ {:p}>", self.algorithm, self)
    }
}

fn buffer_view<'py>(py: Python<'py>, object: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let memoryview = py.import("builtins")?.getattr("memoryview")?.call1((object,))?;
    if !memoryview.getattr("c_contiguous")?.extract::<bool>()? {
        return Err(pyo3::exceptions::PyBufferError::new_err(
            "memoryview: underlying buffer is not C-contiguous",
        ));
    }
    Ok(memoryview)
}

fn buffer_length(memoryview: &Bound<'_, PyAny>) -> PyResult<usize> {
    memoryview.getattr("nbytes")?.extract()
}

fn buffer_bytes_from_view(memoryview: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    memoryview.call_method0("tobytes")?.extract()
}

fn update_buffer(
    py: Python<'_>,
    object: &Bound<'_, PyAny>,
    mut update: impl FnMut(&[u8]),
) -> PyResult<()> {
    let view = buffer_view(py, object)?;
    let byte_view = view.call_method1("cast", ("B",))?;
    let length = buffer_length(&byte_view)?;
    for start in (0..length).step_by(1 << 20) {
        let end = (start + (1 << 20)).min(length);
        let slice = byte_view.get_item(PySlice::new(py, start as isize, end as isize, 1))?;
        let bytes = buffer_bytes_from_view(&slice)?;
        update(&bytes);
    }
    Ok(())
}

fn hex_digest(bytes: &[u8]) -> String {
    let mut hex = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        use std::fmt::Write;
        let _ = write!(hex, "{byte:02x}");
    }
    hex
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
        other => other.to_owned(),
    }
}

fn digest_name(object: &Bound<'_, PyAny>) -> PyResult<String> {
    let name = if object.is_instance_of::<PyString>() {
        object.extract::<String>()?
    } else {
        object
            .getattr("__name__")
            .and_then(|value| value.extract::<String>())
            .map_err(|_| unsupported_digestmod(""))?
    };
    let name = name.strip_prefix("openssl_").unwrap_or(&name);
    Ok(normalize_digest_name(name))
}

#[pyfunction(signature = (algorithm, data=None))]
fn hash_new(
    py: Python<'_>,
    algorithm: &str,
    data: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<HashObject>> {
    let normalized = normalize_digest_name(algorithm);
    let algorithm = match normalized.as_str() {
        "sha512_224" => "sha512_224",
        "sha512_256" => "sha512_256",
        "ripemd160" => "ripemd160",
        "sm3" => "sm3",
        _ => return Err(unsupported_digestmod(algorithm)),
    };
    let mut hash = HashObject::new(algorithm)?;
    if let Some(data) = data {
        let state = &mut hash.state;
        update_buffer(py, data, |bytes| py.detach(|| state.update(bytes)))?;
    }
    Py::new(py, hash)
}

#[pyfunction(signature = (key, msg=None, digestmod=None))]
fn hmac_new(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    msg: Option<&Bound<'_, PyAny>>,
    digestmod: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<HmacObject>> {
    let name = digestmod
        .ok_or_else(|| PyTypeError::new_err("Missing required argument 'digestmod'."))
        .and_then(digest_name)?;
    let algorithm = match name.as_str() {
        "blake2b" => "blake2b",
        "blake2s" => "blake2s",
        "md5" => "md5",
        "md5-sha1" => "md5-sha1",
        "sha1" => "sha1",
        "sha224" => "sha224",
        "sha256" => "sha256",
        "sha384" => "sha384",
        "sha512" => "sha512",
        "sha512_224" => "sha512_224",
        "sha512_256" => "sha512_256",
        "sha3_224" => "sha3_224",
        "sha3_256" => "sha3_256",
        "sha3_384" => "sha3_384",
        "sha3_512" => "sha3_512",
        "ripemd160" => "ripemd160",
        "sm3" => "sm3",
        _ => return Err(unsupported_digestmod(&name)),
    };
    let key_view = buffer_view(py, key)?;
    if buffer_length(&key_view)? > i32::MAX as usize {
        return Err(PyOverflowError::new_err("key is too long."));
    }
    let mut hmac = HmacObject::new(algorithm, &buffer_bytes_from_view(&key_view)?)?;
    if let Some(msg) = msg {
        if !msg.is_none() {
            let state = &mut hmac.state;
            update_buffer(py, msg, |bytes| py.detach(|| state.update(bytes)))?;
        }
    }
    Py::new(py, hmac)
}

#[pyfunction]
fn hmac_digest(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    msg: &Bound<'_, PyAny>,
    digest: &Bound<'_, PyAny>,
) -> PyResult<Py<PyBytes>> {
    let name = digest_name(digest)?;
    let algorithm = match name.as_str() {
        "blake2b" => "blake2b",
        "blake2s" => "blake2s",
        "md5" => "md5",
        "md5-sha1" => "md5-sha1",
        "sha1" => "sha1",
        "sha224" => "sha224",
        "sha256" => "sha256",
        "sha384" => "sha384",
        "sha512" => "sha512",
        "sha512_224" => "sha512_224",
        "sha512_256" => "sha512_256",
        "sha3_224" => "sha3_224",
        "sha3_256" => "sha3_256",
        "sha3_384" => "sha3_384",
        "sha3_512" => "sha3_512",
        "ripemd160" => "ripemd160",
        "sm3" => "sm3",
        _ => return Err(unsupported_digestmod(&name)),
    };
    let key_view = buffer_view(py, key)?;
    let msg_view = buffer_view(py, msg)?;
    if buffer_length(&key_view)? > i32::MAX as usize {
        return Err(PyOverflowError::new_err("key is too long."));
    }
    if buffer_length(&msg_view)? > i32::MAX as usize {
        return Err(PyOverflowError::new_err("msg is too long."));
    }
    let mut hmac = HmacObject::new(algorithm, &buffer_bytes_from_view(&key_view)?)?;
    let state = &mut hmac.state;
    update_buffer(py, &msg_view, |bytes| py.detach(|| state.update(bytes)))?;
    Ok(PyBytes::new(py, &hmac.state.digest()).unbind())
}

fn pbkdf2_for<D: hmac::EagerHash>(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    pbkdf2::pbkdf2::<Hmac<D>>(password, salt, iterations, result)
}

fn pbkdf2_sha3_224(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    pbkdf2::pbkdf2::<SimpleHmac<Sha3_224>>(password, salt, iterations, result)
}

fn pbkdf2_sha3_256(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    pbkdf2::pbkdf2::<SimpleHmac<Sha3_256>>(password, salt, iterations, result)
}

fn pbkdf2_sha3_384(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    pbkdf2::pbkdf2::<SimpleHmac<Sha3_384>>(password, salt, iterations, result)
}

fn pbkdf2_sha3_512(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    pbkdf2::pbkdf2::<SimpleHmac<Sha3_512>>(password, salt, iterations, result)
}

fn pbkdf2_blake2b(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    pbkdf2::pbkdf2::<SimpleHmac<Blake2b512>>(password, salt, iterations, result)
}

fn pbkdf2_blake2s(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) -> Result<(), hmac::digest::InvalidLength> {
    pbkdf2::pbkdf2::<SimpleHmac<Blake2s256>>(password, salt, iterations, result)
}

fn hmac_md5_sha1(
    key: &[u8],
    first: &[u8],
    second: &[u8],
) -> [u8; 36] {
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
        let counter = ((index as u32) + 1).to_be_bytes();
        let mut u = hmac_md5_sha1(password, salt, &counter);
        let mut block = u;
        for _ in 1..iterations {
            u = hmac_md5_sha1(password, &u, &[]);
            for (dst, byte) in block.iter_mut().zip(u) {
                *dst ^= byte;
            }
        }
        output.copy_from_slice(&block[..output.len()]);
    }
    Ok(())
}

#[pyfunction(signature = (hash_name, password, salt, iterations, dklen=None))]
fn pbkdf2_hmac(
    py: Python<'_>,
    hash_name: &Bound<'_, PyAny>,
    password: &Bound<'_, PyAny>,
    salt: &Bound<'_, PyAny>,
    iterations: i64,
    dklen: Option<i64>,
) -> PyResult<Py<PyBytes>> {
    if !hash_name.is_instance_of::<PyString>() {
        return Err(PyTypeError::new_err("hash_name must be a string"));
    }
    let input_name = hash_name.extract::<String>()?;
    let name = normalize_digest_name(&input_name);
    let (digest_size, algorithm): (
        usize,
        fn(&[u8], &[u8], u32, &mut [u8]) -> Result<(), hmac::digest::InvalidLength>,
    ) = match name.as_str() {
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
            return Err(PyValueError::new_err("[Provider routines] xof digests not allowed"));
        }
        _ => return Err(unsupported_digestmod(&input_name)),
    };
    let password_view = buffer_view(py, password)?;
    let salt_view = buffer_view(py, salt)?;
    if buffer_length(&password_view)? > i32::MAX as usize {
        return Err(PyOverflowError::new_err("password is too long."));
    }
    if buffer_length(&salt_view)? > i32::MAX as usize {
        return Err(PyOverflowError::new_err("salt is too long."));
    }
    if iterations < 1 {
        return Err(PyValueError::new_err("iteration value must be greater than 0."));
    }
    if iterations > i32::MAX as i64 {
        return Err(PyOverflowError::new_err("iteration value is too great."));
    }
    let length = match dklen {
        None => digest_size,
        Some(length) if length < 1 => {
            return Err(PyValueError::new_err("key length must be greater than 0."));
        }
        Some(length) if length > i32::MAX as i64 => {
            return Err(PyOverflowError::new_err("key length is too great."));
        }
        Some(length) => length as usize,
    };
    let password = buffer_bytes_from_view(&password_view)?;
    let salt = buffer_bytes_from_view(&salt_view)?;
    let mut result = Vec::new();
    result
        .try_reserve_exact(length)
        .map_err(|_| PyOverflowError::new_err("key length is too great."))?;
    result.resize(length, 0);
    let rounds = iterations as u32;
    let derived = py.detach(|| algorithm(&password, &salt, rounds, &mut result));
    derived.map_err(|_| PyValueError::new_err("invalid password length"))?;
    Ok(PyBytes::new(py, &result).unbind())
}

#[pyfunction(name = "scrypt", signature = (password, *, salt, n, r, p, maxmem=0, dklen=64))]
fn scrypt_impl(
    py: Python<'_>,
    password: &Bound<'_, PyAny>,
    salt: &Bound<'_, PyAny>,
    n: i64,
    r: i64,
    p: i64,
    maxmem: i64,
    dklen: i64,
) -> PyResult<Py<PyBytes>> {
    let password_view = buffer_view(py, password)?;
    let salt_view = buffer_view(py, salt)?;
    if buffer_length(&password_view)? > i32::MAX as usize {
        return Err(PyOverflowError::new_err("password is too long"));
    }
    if buffer_length(&salt_view)? > i32::MAX as usize {
        return Err(PyOverflowError::new_err("salt is too long"));
    }
    if n < 2 || !(n as u64).is_power_of_two() {
        return Err(PyValueError::new_err("n must be a power of 2"));
    }
    if maxmem < 0 || maxmem > i32::MAX as i64 {
        return Err(PyValueError::new_err("maxmem must be positive and at most 2147483647"));
    }
    if dklen < 1 || dklen > i32::MAX as i64 {
        return Err(PyValueError::new_err("dklen must be at least 1 and at most 2147483647"));
    }
    if r < 1 || r > u32::MAX as i64 || p < 1 || p > u32::MAX as i64 {
        return Err(PyValueError::new_err("invalid parameter combination for n, r, p, and maxmem"));
    }
    let log_n = (n as u64).trailing_zeros() as u8;
    let params = ::scrypt::Params::new(log_n, r as u32, p as u32)
        .map_err(|_| PyValueError::new_err("invalid parameter combination for n, r, p, and maxmem"))?;
    let memory = (128u128)
        .checked_mul(r as u128)
        .and_then(|value| {
            (n as u128)
                .checked_add(p as u128)
                .and_then(|sum| sum.checked_add(2))
                .and_then(|sum| value.checked_mul(sum))
        });
    let memory = memory.ok_or_else(|| {
        PyValueError::new_err("invalid parameter combination for n, r, p, and maxmem")
    })?;
    let limit = if maxmem == 0 {
        32u128 * 1024 * 1024
    } else {
        maxmem as u128
    };
    if memory > limit {
        return Err(PyValueError::new_err(
            "invalid parameter combination for n, r, p, and maxmem",
        ));
    }
    let password = buffer_bytes_from_view(&password_view)?;
    let salt = buffer_bytes_from_view(&salt_view)?;
    let mut output = Vec::new();
    output
        .try_reserve_exact(dklen as usize)
        .map_err(|_| PyOverflowError::new_err("dklen is too large"))?;
    output.resize(dklen as usize, 0);
    let result = py.detach(|| ::scrypt::scrypt(&password, &salt, &params, &mut output));
    result.map_err(|_| PyValueError::new_err("invalid scrypt output length"))?;
    Ok(PyBytes::new(py, &output).unbind())
}

#[pymodule]
fn _hashlib_graviola(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<HmacObject>()?;
    module.add_class::<HashObject>()?;
    module.add("UnsupportedDigestmodError", module.py().get_type::<UnsupportedDigestmodError>())?;
    module.add_function(wrap_pyfunction!(hash_new, module)?)?;
    module.add_function(wrap_pyfunction!(hmac_new, module)?)?;
    module.add_function(wrap_pyfunction!(hmac_digest, module)?)?;
    module.add_function(wrap_pyfunction!(pbkdf2_hmac, module)?)?;
    module.add_function(wrap_pyfunction!(scrypt_impl, module)?)?;
    Ok(())
}
