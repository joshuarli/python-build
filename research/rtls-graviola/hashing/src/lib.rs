use hmac::{Hmac, KeyInit, Mac, SimpleHmac};
use md5::Md5;
use pyo3::exceptions::{PyOverflowError, PyTypeError, PyValueError};
use pyo3::create_exception;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyBytes, PyString};
use sha1::Sha1;
use sha2::{Sha224, Sha256, Sha384, Sha512, Sha512_224, Sha512_256};
use sha3::{Sha3_224, Sha3_256, Sha3_384, Sha3_512};

create_exception!(_hashlib_graviola, UnsupportedDigestmodError, PyValueError);

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
            "sha3_224" => SimpleHmac::<Sha3_224>::new_from_slice(key)
                .ok()
                .map(Self::Sha3_224),
            "sha3_256" => SimpleHmac::<Sha3_256>::new_from_slice(key)
                .ok()
                .map(Self::Sha3_256),
            "sha3_384" => SimpleHmac::<Sha3_384>::new_from_slice(key)
                .ok()
                .map(Self::Sha3_384),
            "sha3_512" => SimpleHmac::<Sha3_512>::new_from_slice(key)
                .ok()
                .map(Self::Sha3_512),
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
        }
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
        let state = HmacState::new(algorithm, key)
            .ok_or_else(|| UnsupportedDigestmodError::new_err("unsupported digestmod"))?;
        let (digest_size, block_size) = match algorithm {
            "md5" => (16, 64),
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
            _ => return Err(UnsupportedDigestmodError::new_err("unsupported digestmod")),
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
        let bytes = buffer_bytes(py, data)?;
        self.state.update(&bytes);
        Ok(())
    }

    fn copy(&self) -> Self {
        self.clone()
    }

    fn digest(&self) -> Vec<u8> {
        self.state.digest()
    }

    fn hexdigest(&self) -> String {
        let mut hex = String::with_capacity(self.digest_size * 2);
        for byte in self.state.digest() {
            use std::fmt::Write;
            let _ = write!(hex, "{byte:02x}");
        }
        hex
    }

    fn __repr__(&self) -> String {
        format!("<{} HMAC object @ {:p}>", self.algorithm, self)
    }
}

fn buffer_bytes(py: Python<'_>, object: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let memoryview = py.import("builtins")?.getattr("memoryview")?.call1((object,))?;
    if !memoryview.getattr("c_contiguous")?.extract::<bool>()? {
        return Err(pyo3::exceptions::PyBufferError::new_err(
            "underlying buffer is not C-contiguous",
        ));
    }
    memoryview.call_method0("tobytes")?.extract()
}

fn digest_name(object: &Bound<'_, PyAny>) -> PyResult<String> {
    let name = if object.is_instance_of::<PyString>() {
        object.extract::<String>()?
    } else {
        object
            .getattr("__name__")
            .and_then(|value| value.extract::<String>())
            .map_err(|_| UnsupportedDigestmodError::new_err("unsupported digestmod"))?
    };
    let name = name.strip_prefix("openssl_").unwrap_or(&name);
    Ok(name.to_ascii_lowercase().replace('-', "_"))
}

#[pyfunction(signature = (key, msg=None, digestmod=None))]
fn hmac_new(
    py: Python<'_>,
    key: &Bound<'_, PyAny>,
    msg: Option<&Bound<'_, PyAny>>,
    digestmod: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<HmacObject>> {
    let algorithm = digestmod
        .ok_or_else(|| PyTypeError::new_err("Missing required argument 'digestmod'."))
        .and_then(digest_name)?;
    let algorithm = match algorithm.as_str() {
        "md5" => "md5",
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
        _ => return Err(UnsupportedDigestmodError::new_err("unsupported digestmod")),
    };
    let mut hmac = HmacObject::new(algorithm, &buffer_bytes(py, key)?)?;
    if let Some(msg) = msg {
        if !msg.is_none() {
            hmac.state.update(&buffer_bytes(py, msg)?);
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
    let algorithm = digest_name(digest)?;
    let algorithm = match algorithm.as_str() {
        "md5" => "md5",
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
        _ => return Err(UnsupportedDigestmodError::new_err("unsupported digestmod")),
    };
    let mut hmac = HmacObject::new(algorithm, &buffer_bytes(py, key)?)?;
    hmac.state.update(&buffer_bytes(py, msg)?);
    Ok(PyBytes::new(py, &hmac.state.digest()).unbind())
}

fn pbkdf2_for<D: hmac::EagerHash>(
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    result: &mut [u8],
) {
    pbkdf2::pbkdf2_hmac::<D>(password, salt, iterations, result);
}

fn pbkdf2_sha3_224(password: &[u8], salt: &[u8], iterations: u32, result: &mut [u8]) {
    let _ = pbkdf2::pbkdf2::<SimpleHmac<Sha3_224>>(password, salt, iterations, result);
}

fn pbkdf2_sha3_256(password: &[u8], salt: &[u8], iterations: u32, result: &mut [u8]) {
    let _ = pbkdf2::pbkdf2::<SimpleHmac<Sha3_256>>(password, salt, iterations, result);
}

fn pbkdf2_sha3_384(password: &[u8], salt: &[u8], iterations: u32, result: &mut [u8]) {
    let _ = pbkdf2::pbkdf2::<SimpleHmac<Sha3_384>>(password, salt, iterations, result);
}

fn pbkdf2_sha3_512(password: &[u8], salt: &[u8], iterations: u32, result: &mut [u8]) {
    let _ = pbkdf2::pbkdf2::<SimpleHmac<Sha3_512>>(password, salt, iterations, result);
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
    let name = hash_name.extract::<String>()?.to_ascii_lowercase().replace('-', "_");
    let (digest_size, algorithm): (usize, fn(&[u8], &[u8], u32, &mut [u8])) = match name.as_str() {
        "md5" => (16, pbkdf2_for::<Md5>),
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
        _ => return Err(PyValueError::new_err(format!("unsupported hash algorithm {name}"))),
    };
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
    let password = buffer_bytes(py, password)?;
    let salt = buffer_bytes(py, salt)?;
    if password.len() > i32::MAX as usize {
        return Err(PyOverflowError::new_err("password is too long."));
    }
    if salt.len() > i32::MAX as usize {
        return Err(PyOverflowError::new_err("salt is too long."));
    }
    let mut result = Vec::new();
    result
        .try_reserve_exact(length)
        .map_err(|_| PyOverflowError::new_err("key length is too great."))?;
    result.resize(length, 0);
    let rounds = iterations as u32;
    py.detach(|| algorithm(&password, &salt, rounds, &mut result));
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
        .and_then(|value| value.checked_mul(n as u128))
        .and_then(|value| {
            value.checked_add(128u128 * r as u128 * p as u128)
        })
        .and_then(|value| value.checked_add(256u128 * r as u128 + 64));
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
    let password = buffer_bytes(py, password)?;
    let salt = buffer_bytes(py, salt)?;
    if password.len() > i32::MAX as usize {
        return Err(PyOverflowError::new_err("password is too long"));
    }
    if salt.len() > i32::MAX as usize {
        return Err(PyOverflowError::new_err("salt is too long"));
    }
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
    module.add("UnsupportedDigestmodError", module.py().get_type::<UnsupportedDigestmodError>())?;
    module.add_function(wrap_pyfunction!(hmac_new, module)?)?;
    module.add_function(wrap_pyfunction!(hmac_digest, module)?)?;
    module.add_function(wrap_pyfunction!(pbkdf2_hmac, module)?)?;
    module.add_function(wrap_pyfunction!(scrypt_impl, module)?)?;
    Ok(())
}
