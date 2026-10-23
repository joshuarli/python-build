mod python_ffi;

use blake2::{Blake2b512, Blake2s256};
use hmac::{Hmac, KeyInit, Mac, SimpleHmac};
use md5::Md5;
use ripemd::Ripemd160;
use sha1::{Digest, Sha1};
use sha2::{Sha224, Sha256, Sha384, Sha512, Sha512_224, Sha512_256};
use sha3::{Sha3_224, Sha3_256, Sha3_384, Sha3_512};
use sm3::Sm3;

#[derive(Debug)]
pub(crate) enum BackendError {
    UnsupportedDigest(String),
    Value(String),
    Overflow(&'static str),
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
    fn new(name: &str, key: &[u8]) -> Result<Self, BackendError> {
        let invalid_length = |_: hmac::digest::InvalidLength| BackendError::Value("invalid key length".to_owned());
        match name {
            "blake2b" => SimpleHmac::<Blake2b512>::new_from_slice(key)
                .map(Self::Blake2b)
                .map_err(invalid_length),
            "blake2s" => SimpleHmac::<Blake2s256>::new_from_slice(key)
                .map(Self::Blake2s)
                .map_err(invalid_length),
            "md5" => Hmac::<Md5>::new_from_slice(key)
                .map(Self::Md5)
                .map_err(invalid_length),
            "md5-sha1" => Ok(Self::Md5Sha1(Md5Sha1Hmac::new(key))),
            "sha1" => Hmac::<Sha1>::new_from_slice(key)
                .map(Self::Sha1)
                .map_err(invalid_length),
            "sha224" => Hmac::<Sha224>::new_from_slice(key)
                .map(Self::Sha224)
                .map_err(invalid_length),
            "sha256" => Hmac::<Sha256>::new_from_slice(key)
                .map(Self::Sha256)
                .map_err(invalid_length),
            "sha384" => Hmac::<Sha384>::new_from_slice(key)
                .map(Self::Sha384)
                .map_err(invalid_length),
            "sha512" => Hmac::<Sha512>::new_from_slice(key)
                .map(Self::Sha512)
                .map_err(invalid_length),
            "sha512_224" => Hmac::<Sha512_224>::new_from_slice(key)
                .map(Self::Sha512_224)
                .map_err(invalid_length),
            "sha512_256" => Hmac::<Sha512_256>::new_from_slice(key)
                .map(Self::Sha512_256)
                .map_err(invalid_length),
            "sha3_224" => SimpleHmac::<Sha3_224>::new_from_slice(key)
                .map(Self::Sha3_224)
                .map_err(invalid_length),
            "sha3_256" => SimpleHmac::<Sha3_256>::new_from_slice(key)
                .map(Self::Sha3_256)
                .map_err(invalid_length),
            "sha3_384" => SimpleHmac::<Sha3_384>::new_from_slice(key)
                .map(Self::Sha3_384)
                .map_err(invalid_length),
            "sha3_512" => SimpleHmac::<Sha3_512>::new_from_slice(key)
                .map(Self::Sha3_512)
                .map_err(invalid_length),
            "ripemd160" => Hmac::<Ripemd160>::new_from_slice(key)
                .map(Self::Ripemd160)
                .map_err(invalid_length),
            "sm3" => Hmac::<Sm3>::new_from_slice(key)
                .map(Self::Sm3)
                .map_err(invalid_length),
            _ => Err(BackendError::UnsupportedDigest(name.to_owned())),
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
            let mut result = Vec::with_capacity(36);
            result.extend_from_slice(&md5);
            result.extend_from_slice(&sha1);
            result
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

#[derive(Clone)]
pub(crate) struct HmacObject {
    state: HmacState,
    pub(crate) digest_size: usize,
    pub(crate) block_size: usize,
}

impl HmacObject {
    pub(crate) fn new(algorithm: &'static str, key: &[u8]) -> Result<Self, BackendError> {
        let state = HmacState::new(algorithm, key)?;
        let (digest_size, block_size) = hmac_metadata(algorithm)
            .ok_or_else(|| BackendError::UnsupportedDigest(algorithm.to_owned()))?;
        Ok(Self {
            state,
            digest_size,
            block_size,
        })
    }

    pub(crate) fn update(&mut self, data: &[u8]) {
        self.state.update(data);
    }

    pub(crate) fn digest(&self) -> Vec<u8> {
        self.state.digest()
    }
}

fn hmac_metadata(algorithm: &str) -> Option<(usize, usize)> {
    match algorithm {
        "blake2b" => Some((64, 128)),
        "blake2s" => Some((32, 64)),
        "md5" => Some((16, 64)),
        "md5-sha1" => Some((36, 64)),
        "sha1" => Some((20, 64)),
        "sha224" => Some((28, 64)),
        "sha256" => Some((32, 64)),
        "sha384" => Some((48, 128)),
        "sha512" => Some((64, 128)),
        "sha512_224" => Some((28, 128)),
        "sha512_256" => Some((32, 128)),
        "sha3_224" => Some((28, 144)),
        "sha3_256" => Some((32, 136)),
        "sha3_384" => Some((48, 104)),
        "sha3_512" => Some((64, 72)),
        "ripemd160" => Some((20, 64)),
        "sm3" => Some((32, 64)),
        _ => None,
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

#[derive(Clone)]
pub(crate) struct HashObject {
    state: ExtraDigestState,
    pub(crate) digest_size: usize,
    pub(crate) block_size: usize,
}

impl HashObject {
    pub(crate) fn new(algorithm: &'static str) -> Result<Self, BackendError> {
        let state = ExtraDigestState::new(algorithm)
            .ok_or_else(|| BackendError::UnsupportedDigest(algorithm.to_owned()))?;
        let (digest_size, block_size) = match algorithm {
            "sha512_224" => (28, 128),
            "sha512_256" => (32, 128),
            "ripemd160" => (20, 64),
            "sm3" => (32, 64),
            _ => return Err(BackendError::UnsupportedDigest(algorithm.to_owned())),
        };
        Ok(Self {
            state,
            digest_size,
            block_size,
        })
    }

    pub(crate) fn update(&mut self, data: &[u8]) {
        self.state.update(data);
    }

    pub(crate) fn digest(&self) -> Vec<u8> {
        self.state.digest()
    }
}

#[derive(Clone)]
pub(crate) enum NativeState {
    Hash(HashObject),
    Hmac(HmacObject),
}

impl NativeState {
    pub(crate) fn digest(&self) -> Vec<u8> {
        match self {
            Self::Hash(hash) => hash.digest(),
            Self::Hmac(hmac) => hmac.digest(),
        }
    }
}

pub(crate) fn normalize_digest_name(name: &str) -> String {
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

pub(crate) fn new_hash(name: &str) -> Result<HashObject, BackendError> {
    match normalize_digest_name(name).as_str() {
        "sha512_224" => HashObject::new("sha512_224"),
        "sha512_256" => HashObject::new("sha512_256"),
        "ripemd160" => HashObject::new("ripemd160"),
        "sm3" => HashObject::new("sm3"),
        _ => Err(BackendError::UnsupportedDigest(name.to_owned())),
    }
}

pub(crate) fn new_hmac(name: &str, key: &[u8]) -> Result<HmacObject, BackendError> {
    let normalized = normalize_digest_name(name);
    HmacObject::new(
        match normalized.as_str() {
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
            _ => return Err(BackendError::UnsupportedDigest(name.to_owned())),
        },
        key,
    )
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
        let counter = ((index as u32) + 1).to_be_bytes();
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

pub(crate) struct Pbkdf2Parameters {
    algorithm: Pbkdf2Algorithm,
    iterations: u32,
    length: usize,
}

pub(crate) fn pbkdf2_parameters(
    hash_name: &str,
    password_length: usize,
    salt_length: usize,
    iterations: i64,
    dklen: Option<i64>,
) -> Result<Pbkdf2Parameters, BackendError> {
    let normalized = normalize_digest_name(hash_name);
    let (digest_size, algorithm): (usize, Pbkdf2Algorithm) = match normalized.as_str() {
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
            return Err(BackendError::Value(
                "[Provider routines] xof digests not allowed".to_owned(),
            ));
        }
        _ => return Err(BackendError::UnsupportedDigest(hash_name.to_owned())),
    };
    if password_length > i32::MAX as usize {
        return Err(BackendError::Overflow("password is too long."));
    }
    if salt_length > i32::MAX as usize {
        return Err(BackendError::Overflow("salt is too long."));
    }
    if iterations < 1 {
        return Err(BackendError::Value(
            "iteration value must be greater than 0.".to_owned(),
        ));
    }
    if iterations > i32::MAX as i64 {
        return Err(BackendError::Overflow("iteration value is too great."));
    }
    let length = match dklen {
        None => digest_size,
        Some(length) if length < 1 => {
            return Err(BackendError::Value(
                "key length must be greater than 0.".to_owned(),
            ));
        }
        Some(length) if length > i32::MAX as i64 => {
            return Err(BackendError::Overflow("key length is too great."));
        }
        Some(length) => length as usize,
    };
    Ok(Pbkdf2Parameters {
        algorithm,
        iterations: iterations as u32,
        length,
    })
}

pub(crate) fn pbkdf2_derive(
    parameters: Pbkdf2Parameters,
    password: &[u8],
    salt: &[u8],
) -> Result<Vec<u8>, BackendError> {
    let mut result = Vec::new();
    result
        .try_reserve_exact(parameters.length)
        .map_err(|_| BackendError::Overflow("key length is too great."))?;
    result.resize(parameters.length, 0);
    (parameters.algorithm)(password, salt, parameters.iterations, &mut result)
        .map_err(|_| BackendError::Value("invalid password length".to_owned()))?;
    Ok(result)
}

pub(crate) struct ScryptParameters {
    params: scrypt::Params,
    dklen: usize,
}

pub(crate) fn scrypt_parameters(
    password_length: usize,
    salt_length: usize,
    n: i64,
    r: i64,
    p: i64,
    maxmem: i64,
    dklen: i64,
) -> Result<ScryptParameters, BackendError> {
    if password_length > i32::MAX as usize {
        return Err(BackendError::Overflow("password is too long"));
    }
    if salt_length > i32::MAX as usize {
        return Err(BackendError::Overflow("salt is too long"));
    }
    if n < 2 || !(n as u64).is_power_of_two() {
        return Err(BackendError::Value("n must be a power of 2".to_owned()));
    }
    if maxmem < 0 || maxmem > i32::MAX as i64 {
        return Err(BackendError::Value(
            "maxmem must be positive and at most 2147483647".to_owned(),
        ));
    }
    if dklen < 1 || dklen > i32::MAX as i64 {
        return Err(BackendError::Value(
            "dklen must be at least 1 and at most 2147483647".to_owned(),
        ));
    }
    if r < 1 || r > u32::MAX as i64 || p < 1 || p > u32::MAX as i64 {
        return Err(BackendError::Value(
            "invalid parameter combination for n, r, p, and maxmem".to_owned(),
        ));
    }
    let log_n = (n as u64).trailing_zeros() as u8;
    let params = scrypt::Params::new(log_n, r as u32, p as u32).map_err(|_| {
        BackendError::Value("invalid parameter combination for n, r, p, and maxmem".to_owned())
    })?;
    let memory = 128u128
        .checked_mul(r as u128)
        .and_then(|value| {
            (n as u128)
                .checked_add(p as u128)
                .and_then(|sum| sum.checked_add(2))
                .and_then(|sum| value.checked_mul(sum))
        })
        .ok_or_else(|| {
            BackendError::Value("invalid parameter combination for n, r, p, and maxmem".to_owned())
        })?;
    let limit = if maxmem == 0 {
        32u128 * 1024 * 1024
    } else {
        maxmem as u128
    };
    if memory > limit {
        return Err(BackendError::Value(
            "invalid parameter combination for n, r, p, and maxmem".to_owned(),
        ));
    }
    Ok(ScryptParameters {
        params,
        dklen: dklen as usize,
    })
}

pub(crate) fn scrypt_derive(
    parameters: ScryptParameters,
    password: &[u8],
    salt: &[u8],
) -> Result<Vec<u8>, BackendError> {
    let mut output = Vec::new();
    output
        .try_reserve_exact(parameters.dklen)
        .map_err(|_| BackendError::Overflow("dklen is too large"))?;
    output.resize(parameters.dklen, 0);
    scrypt::scrypt(password, salt, &parameters.params, &mut output)
        .map_err(|_| BackendError::Value("invalid scrypt output length".to_owned()))?;
    Ok(output)
}
