use super::*;
use std::io::{Cursor, Read};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;

enum Value {
    None,
    Bool(bool),
    Int(i64),
    Handle(OwnedHandle),
    Bytes(Vec<u8>),
    Text(String),
    List(Vec<Value>),
    Tuple(Vec<Value>),
    Dict(Vec<(String, Value)>),
}

impl Value {
    fn int(&self) -> Result<i64, NativeError> {
        match self { Self::Int(value) => Ok(*value), _ => Err(NativeError::value("expected integer")) }
    }
    fn boolean(&self) -> Result<bool, NativeError> {
        match self { Self::Bool(value) => Ok(*value), _ => Err(NativeError::value("expected bool")) }
    }
    fn bytes(&self) -> Result<&[u8], NativeError> {
        match self { Self::Bytes(value) => Ok(value), _ => Err(NativeError::value("expected bytes")) }
    }
    fn text(&self) -> Result<&str, NativeError> {
        match self { Self::Text(value) => Ok(value), _ => Err(NativeError::value("expected str")) }
    }
    fn items(&self) -> Result<&[Value], NativeError> {
        match self { Self::List(value) | Self::Tuple(value) => Ok(value), _ => Err(NativeError::value("expected sequence")) }
    }
    fn encode(&self, output: &mut Vec<u8>) {
        match self {
            Self::None => output.push(0),
            Self::Bool(value) => output.push(if *value { 2 } else { 1 }),
            Self::Int(value) => { output.push(3); output.extend_from_slice(&value.to_le_bytes()); }
            Self::Handle(value) => { output.push(9); output.push(value.kind); output.extend_from_slice(&value.id.to_le_bytes()); }
            Self::Bytes(value) => { output.push(4); put_length(output, value.len()); output.extend_from_slice(value); }
            Self::Text(value) => { output.push(5); put_length(output, value.len()); output.extend_from_slice(value.as_bytes()); }
            Self::List(values) | Self::Tuple(values) => {
                output.push(if matches!(self, Self::List(_)) { 6 } else { 7 });
                put_length(output, values.len());
                for value in values { value.encode(output); }
            }
            Self::Dict(values) => {
                output.push(8); put_length(output, values.len());
                for (key, value) in values { Self::Text(key.clone()).encode(output); value.encode(output); }
            }
        }
    }
}

fn put_length(output: &mut Vec<u8>, length: usize) {
    output.extend_from_slice(&u32::try_from(length).unwrap_or(u32::MAX).to_le_bytes());
}

struct Decoder<'a> { input: &'a [u8], offset: usize }
impl<'a> Decoder<'a> {
    fn take(&mut self, count: usize) -> Result<&'a [u8], NativeError> {
        let end = self.offset.checked_add(count).ok_or_else(|| NativeError::value("argument length overflow"))?;
        let bytes = self.input.get(self.offset..end).ok_or_else(|| NativeError::value("truncated native argument"))?;
        self.offset = end;
        Ok(bytes)
    }
    fn length(&mut self) -> Result<usize, NativeError> {
        let bytes: [u8; 4] = self.take(4)?.try_into().map_err(|_| NativeError::value("truncated native argument"))?;
        Ok(u32::from_le_bytes(bytes) as usize)
    }
    fn value(&mut self, depth: usize) -> Result<Value, NativeError> {
        if depth > 32 { return Err(NativeError::value("native argument nesting is too deep")); }
        Ok(match self.take(1)?[0] {
            0 => Value::None, 1 => Value::Bool(false), 2 => Value::Bool(true),
            3 => {
                let bytes: [u8; 8] = self.take(8)?.try_into().map_err(|_| NativeError::value("truncated native argument"))?;
                Value::Int(i64::from_le_bytes(bytes))
            }
            4 => { let length = self.length()?; Value::Bytes(self.take(length)?.to_vec()) }
            5 => { let length = self.length()?; Value::Text(std::str::from_utf8(self.take(length)?).map_err(|e| NativeError::value(e.to_string()))?.into()) }
            tag @ (6 | 7) => {
                let count = self.length()?;
                if count > self.input.len().saturating_sub(self.offset) { return Err(NativeError::value("invalid argument item count")); }
                let values = (0..count).map(|_| self.value(depth + 1)).collect::<Result<Vec<_>, _>>()?;
                if tag == 6 { Value::List(values) } else { Value::Tuple(values) }
            }
            8 => {
                let count = self.length()?;
                if count > self.input.len().saturating_sub(self.offset) / 2 { return Err(NativeError::value("invalid map item count")); }
                let mut values = Vec::new();
                for _ in 0..count { let key = self.value(depth + 1)?.text()?.to_string(); values.push((key, self.value(depth + 1)?)); }
                Value::Dict(values)
            }
            _ => return Err(NativeError::value("unknown native argument type")),
        })
    }
}

struct NativeError { status: i32, value: Value }
impl NativeError {
    fn ssl(message: impl Into<String>) -> Self { Self { status: 1, value: Value::Text(message.into()) } }
    fn value(message: impl Into<String>) -> Self { Self { status: 5, value: Value::Text(message.into()) } }
}
impl From<String> for NativeError { fn from(value: String) -> Self { Self::ssl(value) } }
impl From<std::io::Error> for NativeError { fn from(value: std::io::Error) -> Self { Self::ssl(value.to_string()) } }
impl From<rustls::Error> for NativeError {
    fn from(error: rustls::Error) -> Self { crate::error::TlsError::from(error).into() }
}
impl From<crate::error::TlsError> for NativeError {
    fn from(error: crate::error::TlsError) -> Self {
        use crate::error::TlsError;
        match error {
            TlsError::CertVerification { message, code } => {
                let verify_message = crate::error::certificate_verification_message(&message, code).to_string();
                Self { status: 2, value: Value::Tuple(vec![Value::Int(code as i64), Value::Text(message), Value::Text(verify_message)]) }
            }
            TlsError::General(message) => Self::ssl(message),
            TlsError::CleanEof => Self { status: 3, value: Value::Text(crate::error::ZERO_RETURN_MESSAGE.into()) },
            TlsError::NoSharedCipher => Self { status: 12, value: Value::Tuple(vec![
                Value::Text(crate::error::NO_SHARED_CIPHER_MESSAGE.into()), Value::Text("SSL".into()), Value::Text(crate::error::NO_SHARED_CIPHER_REASON.into()),
            ]) },
            TlsError::AlertReceived(alert) => {
                let (reason, message) = crate::error::alert_error_fields(alert);
                let reason = reason.map(|value| Value::Text(value.into())).unwrap_or(Value::None);
                Self { status: 12, value: Value::Tuple(vec![Value::Text(message), Value::Text("SSL".into()), reason]) }
            }
        }
    }
}

enum Object {
    Builder(RustlsConfigBuilder),
    Connection(NativeConnection),
    Acceptor(NativeAcceptor),
    Session(Arc<SessionData>),
    Reply { value: Value, data: Vec<u8> },
}

struct NativeClientPolicy {
    config: Arc<ClientConfig>,
    server_name: ServerName<'static>,
    context: Arc<ContextIdentity>,
    require_verified_chain: bool,
}

struct NativeConnection {
    client: Option<NativeClientPolicy>,
    conn: rustls::Connection,
    verified: VerifiedChain,
    sessions: Arc<Mutex<Option<Arc<SessionData>>>>,
    stats: Arc<SessionStats>,
    started: bool,
    completed: bool,
    pending: usize,
    peer_closed: bool,
}
struct NativeAcceptor {
    acceptor: rustls::server::Acceptor,
    accepted: Option<rustls::server::Accepted>,
    remaining: Vec<u8>,
    alert: Vec<u8>,
}

type Registry = HashMap<u64, Arc<Mutex<Object>>>;
static OBJECTS: OnceLock<Mutex<Registry>> = OnceLock::new();
static NEXT_HANDLE: AtomicU64 = AtomicU64::new(1);
fn registry() -> &'static Mutex<Registry> { OBJECTS.get_or_init(|| Mutex::new(HashMap::new())) }
fn insert(object: Object) -> u64 {
    let handle = NEXT_HANDLE.fetch_add(1, Ordering::Relaxed);
    assert!(handle > 0 && handle <= i64::MAX as u64, "native handle space exhausted");
    registry().lock().unwrap_or_else(|poisoned| poisoned.into_inner()).insert(handle, Arc::new(Mutex::new(object)));
    handle
}
fn lookup(handle: u64) -> Result<Arc<Mutex<Object>>, NativeError> {
    registry().lock().map_err(|_| NativeError::ssl("native registry is poisoned"))?
        .get(&handle).cloned().ok_or_else(|| NativeError { status: 7, value: Value::Text("invalid or released native handle".into()) })
}

#[repr(C)]
pub struct NativeReply { handle: u64, status: i32, length: usize }
fn reply(result: Result<Value, NativeError>) -> NativeReply {
    let (status, value) = match result { Ok(value) => (0, value), Err(error) => (error.status, error.value) };
    let mut data = Vec::new(); value.encode(&mut data);
    let length = data.len();
    let handle = insert(Object::Reply { value, data });
    NativeReply { handle, status, length }
}

/// Anchor the C ABI exports against archive member selection when the
/// engine links statically into libpython: the linker only pulls archive
/// members that resolve a reference, and `PyInit__ssl_rs` alone does not
/// reference these entry points. Referencing each one from a `used` static
/// keeps every export alive without changing runtime behavior.
struct AbiExports([*const std::ffi::c_void; 6]);
unsafe impl Sync for AbiExports {}

#[used]
static ABI_EXPORTS: AbiExports = AbiExports([
    rtls_native_invoke as *const std::ffi::c_void,
    rtls_native_copy_reply as *const std::ffi::c_void,
    rtls_native_free as *const std::ffi::c_void,
    rtls_native_handle_count as *const std::ffi::c_void,
    rtls_native_claim as *const std::ffi::c_void,
    rtls_native_report_unraisable as *const std::ffi::c_void,
]);

/// # Safety
/// Input pointers must identify readable allocations of their declared lengths. Zero lengths permit null pointers. The output must be aligned writable storage for one NativeReply until this call returns.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rtls_native_invoke(handle: u64, method: *const u8, method_length: usize, data: *const u8, data_length: usize, output: *mut NativeReply) {
    if output.is_null() { return; }
    if method_length > 128 || data_length > isize::MAX as usize || (method.is_null() && method_length != 0) || (data.is_null() && data_length != 0) {
        let failure = reply(Err(NativeError::value("invalid native input extent")));
        // SAFETY: The caller allocated aligned writable NativeReply storage before entering this function.
        unsafe { output.write(failure); }
        return;
    }
    let method_bytes = if method_length == 0 { &[] } else {
        // SAFETY: The foreign caller owns a readable method allocation for the declared extent.
        unsafe { std::slice::from_raw_parts(method, method_length) }
    };
    let input = if data_length == 0 { &[] } else {
        // SAFETY: The foreign caller owns a readable argument allocation for the declared extent.
        unsafe { std::slice::from_raw_parts(data, data_length) }
    };
    let result = (|| -> Result<Value, NativeError> {
        let method = std::str::from_utf8(method_bytes).map_err(|e| NativeError::value(e.to_string()))?;
        let mut decoder = Decoder { input, offset: 0 };
        let arguments = decoder.value(0)?;
        if decoder.offset != input.len() { return Err(NativeError::value("trailing native arguments")); }
        dispatch(handle, method, arguments.items()?)
    })();
    let reply = reply(result);
    // SAFETY: The caller allocated aligned writable NativeReply storage before entering this function.
    unsafe { output.write(reply); }
}

/// # Safety
/// The output pointer must identify a writable allocation of capacity bytes. A zero capacity permits a null pointer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rtls_native_copy_reply(handle: u64, output: *mut u8, capacity: usize) -> i32 {
    let result = (|| -> Result<(), NativeError> {
        let entry = lookup(handle)?;
        let entry = entry.lock().map_err(|_| NativeError::ssl("native reply is poisoned"))?;
        let Object::Reply { data, .. } = &*entry else { return Err(NativeError::value("handle is not a reply")); };
        if data.len() > capacity || (output.is_null() && !data.is_empty()) { return Err(NativeError::value("native reply destination is too small")); }
        if !data.is_empty() {
            // SAFETY: The caller provides a writable allocation for capacity bytes, and the source belongs to this locked reply.
            unsafe { std::ptr::copy_nonoverlapping(data.as_ptr(), output, data.len()); }
        }
        Ok(())
    })();
    match result { Ok(()) => 0, Err(_) => -1 }
}

#[unsafe(no_mangle)]
pub extern "C" fn rtls_native_free(handle: u64) -> i32 {
    let removed = registry().lock().map(|mut entries| entries.remove(&handle));
    match removed {
        Ok(Some(object)) => { drop(object); 0 }
        _ => -1,
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn rtls_native_handle_count() -> usize {
    registry().lock().map(|entries| entries.len()).unwrap_or(usize::MAX)
}

fn argument(arguments: &[Value], index: usize) -> Result<&Value, NativeError> {
    arguments.get(index).ok_or_else(|| NativeError::value("missing native argument"))
}
struct OwnedHandle { id: u64, kind: u8 }
impl Drop for OwnedHandle {
    fn drop(&mut self) {
        if self.id != 0 {
            let object = registry().lock().unwrap_or_else(|poisoned| poisoned.into_inner()).remove(&self.id);
            drop(object);
        }
    }
}
fn handle_value(handle: u64) -> Result<Value, NativeError> {
    let mut owned = OwnedHandle { id: handle, kind: 0 };
    let entry = lookup(handle)?;
    let kind = match &*entry.lock().unwrap_or_else(|poisoned| poisoned.into_inner()) {
        Object::Builder(_) => 1, Object::Connection(connection) => if connection.client.is_some() { 2 } else { 3 },
        Object::Acceptor(_) => 4, Object::Session(_) => 5,
        Object::Reply { .. } => return Err(NativeError::value("a reply cannot be returned as a TLS object")),
    };
    owned.kind = kind;
    Ok(Value::Handle(owned))
}
fn byte_list(values: Vec<Vec<u8>>) -> Value { Value::List(values.into_iter().map(Value::Bytes).collect()) }

fn dispatch(handle: u64, method: &str, arguments: &[Value]) -> Result<Value, NativeError> {
    if handle == 0 {
        return match method {
            "new_builder" => handle_value(insert(Object::Builder(RustlsConfigBuilder::new()))),
            "new_acceptor" => {
                let capture_message_callback = arguments.get(0).map(Value::boolean).transpose()?.unwrap_or(false);
                handle_value(insert(Object::Acceptor(NativeAcceptor {
                    acceptor: rustls::server::Acceptor::new_with_message_callback(capture_message_callback),
                    accepted: None,
                    remaining: Vec::new(),
                    alert: Vec::new(),
                })))
            }
            "rustls_version" => Ok(Value::Text(env!("RUSTLS_VERSION").into())),
            "graviola_version" => Ok(Value::Text(env!("GRAVIOLA_VERSION").into())),
            "crypto_provider_version" => Ok(Value::Text(env!("RUSTLS_GRAVIOLA_VERSION").into())),
            "crypto_provider" => Ok(Value::Text("rustls-graviola".into())),
            "supported_sigalgs" => Ok(Value::List(RustlsConfigBuilder::supported_sigalgs().into_iter().map(Value::Text).collect())),
            "rand_bytes" => {
                let length = usize::try_from(argument(arguments, 0)?.int()?).map_err(|_| NativeError::value("invalid random byte count"))?;
                let mut data = Vec::new();
                data.try_reserve_exact(length).map_err(|error| NativeError { status: 11, value: Value::Text(error.to_string()) })?;
                data.resize(length, 0);
                default_crypto_provider().secure_random.fill(&mut data).map_err(|_| NativeError::ssl("random generation failed"))?;
                Ok(Value::Bytes(data))
            }
            "parse_certificate_dict" => certificate_value(argument(arguments, 0)?.bytes()?),
            "certificate_subject_name_der" => Ok(Value::Bytes(crate::trust::canonical_subject_name_from_der(argument(arguments, 0)?.bytes()?)?)),
            _ => Err(NativeError { status: 6, value: Value::Text(format!("native TLS function is not implemented: {method}")) }),
        };
    }
    if method == "equals" {
        let session = optional_session(&Value::Int(handle as i64))?.ok_or_else(|| NativeError::value("expected session handle"))?;
        return Ok(Value::Bool(optional_session(argument(arguments, 0)?)?.is_some_and(|other| session.same_id(&other))));
    }
    if matches!(method, "validate_server_hello" | "accept_server_connection") {
        return accept_with_policy(handle, method, arguments);
    }
    let entry = lookup(handle)?;
    let mut object = entry.lock().map_err(|_| NativeError::ssl("native TLS handle is poisoned"))?;
    match &mut *object {
        Object::Builder(builder) => builder_call(builder, method, arguments),
        Object::Connection(connection) => connection_call(connection, method, arguments),
        Object::Acceptor(acceptor) => acceptor_call(acceptor, method, arguments),
        Object::Session(session) => session_call(session, method, arguments),
        Object::Reply { .. } => Err(NativeError::value("reply is not a TLS object")),
    }
}

fn snapshot(builder: &RustlsConfigBuilder) -> RustlsConfigBuilder {
    let mut cloned = builder.clone_builder_inner();
    cloned.server_sessions = Arc::clone(&builder.server_sessions);
    cloned.server_ticketer = Arc::clone(&builder.server_ticketer);
    cloned
}
fn cloned_builder(handle: u64) -> Result<RustlsConfigBuilder, NativeError> {
    let entry = lookup(handle)?;
    let entry = entry.lock().map_err(|_| NativeError::ssl("native builder is poisoned"))?;
    match &*entry { Object::Builder(builder) => Ok(snapshot(builder)), _ => Err(NativeError::value("expected builder handle")) }
}

fn builder_call(builder: &mut RustlsConfigBuilder, method: &str, arguments: &[Value]) -> Result<Value, NativeError> {
    match method {
        "clone_builder" => return handle_value(insert(Object::Builder(builder.clone_builder_inner()))),
        "snapshot_server_builder" => return handle_value(insert(Object::Builder(snapshot(builder)))),
        "set_min_version" => { builder.set_min_version(u16::try_from(argument(arguments, 0)?.int()?).map_err(|_| NativeError::value("invalid TLS version"))?); return Ok(Value::None); }
        "set_max_version" => { builder.set_max_version(u16::try_from(argument(arguments, 0)?.int()?).map_err(|_| NativeError::value("invalid TLS version"))?); return Ok(Value::None); }
        "set_verify_mode" => {
            let mode = argument(arguments, 0)?.int()?;
            if !(0..=2).contains(&mode) { return Err(NativeError::value("invalid verification mode")); }
            builder.set_verify_mode(mode as i32);
            return Ok(Value::None);
        }
        "set_verify_flags" => {
            let flags = i32::try_from(argument(arguments, 0)?.int()?).map_err(|_| NativeError::value("invalid verification flags"))?;
            if flags & !SUPPORTED_VERIFY_FLAGS != 0 { return Err(NativeError { status: 6, value: Value::Text("Unsupported certificate verification flags".into()) }); }
            builder.verify_flags = flags;
        }
        "set_check_hostname" => { builder.set_check_hostname(argument(arguments, 0)?.boolean()?); return Ok(Value::None); }
        "set_hostname_checks_common_name" => { builder.set_hostname_checks_common_name(argument(arguments, 0)?.boolean()?); return Ok(Value::None); }
        "set_sni_enabled" => { builder.set_sni_enabled(argument(arguments, 0)?.boolean()?); return Ok(Value::None); }
        "set_cipher_server_preference" => { builder.set_cipher_server_preference(argument(arguments, 0)?.boolean()?); return Ok(Value::None); }
        "set_alpn" => { builder.set_alpn(argument(arguments, 0)?.items()?.iter().map(|value| value.bytes().map(Vec::from)).collect::<Result<_, _>>()?); return Ok(Value::None); }
        "set_cipher_suites" | "set_tls13_cipher_suites" => {
            let suites = argument(arguments, 0)?.items()?.iter().map(|value| value.text().map(str::to_owned)).collect::<Result<_, _>>()?;
            if method == "set_cipher_suites" { builder.set_cipher_suites(suites); }
            else { builder.set_tls13_cipher_suites(suites); }
            return Ok(Value::None);
        }
        "get_num_tickets" => return Ok(Value::Int(builder.get_num_tickets())),
        "set_num_tickets" => {
            builder.set_num_tickets_inner(argument(arguments, 0)?.int()?, argument(arguments, 1)?.boolean()?).map_err(NativeError::value)?;
            return Ok(Value::None);
        }
        "set_groups" => builder.groups = Some(parse_groups(argument(arguments, 0)?.text()?)?),
        "set_client_sigalgs" => builder.client_sigalgs = Some(parse_signature_schemes(argument(arguments, 0)?.text()?)?),
        "set_server_sigalgs" => builder.server_sigalgs = Some(parse_signature_schemes(argument(arguments, 0)?.text()?)?),
        "get_groups" => return Ok(Value::List(builder.get_groups(argument(arguments, 0)?.boolean()?).into_iter().map(Value::Text).collect())),
        "enabled_cipher_suites" => return Ok(Value::List(builder.get_cipher_suites()?.into_iter().map(|suite| Value::Tuple(vec![Value::Text(format!("{:?}", suite.suite())), Value::Int(u16::from(suite.suite()) as i64)])).collect())),
        "add_root_certs_from_pem" | "add_root_certs_from_cadata" => {
            let data = argument(arguments, 0)?.bytes()?;
            let (certificates, crls) = if method == "add_root_certs_from_pem" {
                let material = parse_trust_material(data).map_err(|error| NativeError::ssl(format!("[SSL] PEM lib ({error})")))?;
                (material.certificates, material.crls)
            } else {
                let certificates = parse_certificates(data).map_err(|error| NativeError::ssl(format!("[SSL] PEM lib ({error})")))?;
                (certificates, Vec::new())
            };
            let count = certificates.len();
            for certificate in certificates {
                let der = certificate.to_vec();
                if !builder.root_certs_der.contains(&der) { builder.root_certs_der.push(der); }
            }
            for crl in crls { if !builder.crls_der.contains(&crl) { builder.crls_der.push(crl); } }
            builder.invalidate_config();
            return Ok(Value::Int(count as i64));
        }
        "add_root_cert_from_der" => {
            use x509_parser::prelude::*;
            let mut remaining = argument(arguments, 0)?.bytes()?;
            let mut certificates = Vec::new();
            while !remaining.is_empty() {
                let (rest, _) = X509Certificate::from_der(remaining).map_err(|error| {
                    let insufficient = match &error {
                        x509_parser::nom::Err::Incomplete(_) => true,
                        x509_parser::nom::Err::Error(x509_parser::error::X509Error::NomError(
                            x509_parser::nom::error::ErrorKind::Eof,
                        ))
                        | x509_parser::nom::Err::Failure(x509_parser::error::X509Error::NomError(
                            x509_parser::nom::error::ErrorKind::Eof,
                        )) => true,
                        _ => false,
                    };
                    if insufficient {
                        NativeError::ssl("not enough data: cadata does not contain a certificate")
                    } else {
                        NativeError::ssl(format!("Invalid certificate DER: {error}"))
                    }
                })?;
                let consumed = remaining.len() - rest.len();
                if consumed == 0 { return Err(NativeError::ssl("empty DER certificate")); }
                validate_der(&remaining[..consumed])?;
                certificates.push(remaining[..consumed].to_vec()); remaining = rest;
            }
            if certificates.is_empty() { return Err(NativeError::ssl("No certificates found in DER data")); }
            for certificate in certificates { if !builder.root_certs_der.contains(&certificate) { builder.root_certs_der.push(certificate); } }
        }
        "add_capath_directory" => {
            let path = path_buf_from_bytes(argument(arguments, 0)?.bytes()?).map_err(NativeError::value)?;
            if !builder.capath_dirs.contains(&path) { builder.capath_dirs.push(path); }
        }
        "cert_chain_key_is_encrypted" => {
            parse_certificates(argument(arguments, 0)?.bytes()?)
                .map_err(|error| NativeError::ssl(format!("[SSL] PEM lib ({error})")))?;
            let key = crate::policy::private_key_pem(argument(arguments, 1)?.bytes()?)
                .map_err(|error| NativeError::ssl(format!("[SSL] PEM lib ({error})")))?;
            let encrypted = selected_key_is_encrypted(key)
                .map_err(|error| NativeError::ssl(format!("[SSL] PEM lib ({error})")))?;
            return Ok(Value::Bool(encrypted));
        }
        "set_client_cert_chain_pem" | "set_server_cert_chain_pem" => {
            let certificates = parse_certificates(argument(arguments, 0)?.bytes()?)
                .map_err(|error| NativeError::ssl(format!("[SSL] PEM lib ({error})")))?;
            let password = match argument(arguments, 2)? { Value::None => None, value => Some(value.bytes()?) };
            let key = load_private_key(argument(arguments, 1)?.bytes()?, password)
                .map_err(|error| NativeError::ssl(format!("[SSL] PEM lib ({error})")))?;
            let certified = rustls::sign::CertifiedKey::from_der(certificates.clone(), key.clone_key(), &default_crypto_provider()).map_err(|error| match error {
                rustls::Error::InconsistentKeys(rustls::InconsistentKeys::KeyMismatch) => NativeError::ssl("[X509: KEY_VALUES_MISMATCH] key values mismatch"),
                other => NativeError::ssl(other.to_string()),
            })?;
            certified.keys_match().map_err(|error| match error {
                rustls::Error::InconsistentKeys(rustls::InconsistentKeys::KeyMismatch) => NativeError::ssl("[X509: KEY_VALUES_MISMATCH] key values mismatch"),
                other => NativeError::ssl(other.to_string()),
            })?;
            if method == "set_client_cert_chain_pem" { builder.client_cert_chain = Some(certificates); builder.client_key = Some(key); }
            else { builder.add_server_certificate(certificates, key, certified.key.algorithm()); }
        }
        "root_cert_count" => return Ok(Value::Int(builder.root_cert_count() as i64)),
        "root_ca_count" => return Ok(Value::Int(builder.root_ca_count() as i64)),
        "crl_count" => return Ok(Value::Int(builder.crl_count() as i64)),
        "get_root_certs_der" => return Ok(byte_list(builder.get_root_certs_der())),
        "get_ca_certs_der" => return Ok(byte_list(builder.get_ca_certs_der())),
        "session_stats" => return Ok(Value::Dict(builder.session_stats.snapshot(builder.client_sessions.entry_count()).into_iter().map(|(key, value)| (key, Value::Int(value as i64))).collect())),
        "has_ech" => return Ok(Value::Bool(builder.ech_config_list.is_some())),
        "set_ech_configs" => return Err(NativeError { status: 6, value: Value::Text("ECH is not supported by the Graviola provider".into()) }),
        "set_keylog_filename" => {
            let logger = match argument(arguments, 0)? {
                Value::None => None,
                path => {
                    let path_bytes = path.bytes()?;
                    let path = path_buf_from_bytes(path_bytes).map_err(NativeError::value)?;
                    let logger = KeyLogToFile::open(path).map_err(|error| NativeError { status: 9, value: Value::Tuple(vec![Value::Int(error.raw_os_error().unwrap_or(5) as i64), Value::Text(error.to_string()), Value::Bytes(path_bytes.to_vec())]) })?;
                    Some(Arc::new(logger))
                }
            };
            if let Some(previous) = builder.keylog.as_ref() { previous.disable(); }
            builder.keylog = logger;
        }
        "build_client_connection" => {
            let name = ServerName::try_from(argument(arguments, 0)?.text()?.to_string()).map_err(|e| NativeError::ssl(e.to_string()))?;
            let session = optional_session(argument(arguments, 1)?)?;
            let capture_message_callback = arguments.get(2).map(Value::boolean).transpose()?.unwrap_or(false);
            if let Some(session) = session.as_ref() {
                validate_session(session, &builder.context_identity, &name, builder.verify_mode != CERT_NONE)?;
            }
            let session_override = session.as_ref().map(|value| value.reserve_explicit()).transpose()
                .map_err(|error| NativeError::value(error.to_string()))?;
            let config = builder.get_or_build_client_config()?;
            let verified = Arc::new(Mutex::new(None));
            let sessions = Arc::new(Mutex::new(None));
            let _capture = VerificationCapture::enter(Arc::clone(&verified));
            let _sessions = SessionCapture::enter(Arc::clone(&sessions));
            let _override = session_override.map(SessionOverride::enter);
            let conn = rustls::ClientConnection::new_with_message_callback(
                Arc::clone(&config),
                name.clone(),
                capture_message_callback,
            )?;
            builder.session_stats.client_started();
            return handle_value(insert(Object::Connection(NativeConnection {
                client: Some(NativeClientPolicy {
                    config, server_name: name, context: Arc::clone(&builder.context_identity),
                    require_verified_chain: builder.verify_mode != CERT_NONE,
                }),
                conn: conn.into(), verified, sessions, stats: Arc::clone(&builder.session_stats),
                started: false, completed: false, pending: 0, peer_closed: false,
            })))
        }
        "build_server_connection" => {
            let capture_message_callback = arguments.get(0).map(Value::boolean).transpose()?.unwrap_or(false);
            let conn = rustls::ServerConnection::new_with_message_callback(
                Arc::new(builder.build_server_config_inner()?),
                capture_message_callback,
            )?;
            return handle_value(insert(Object::Connection(NativeConnection {
                client: None, conn: conn.into(), verified: Arc::new(Mutex::new(None)), sessions: Arc::new(Mutex::new(None)), stats: Arc::clone(&builder.session_stats),
                started: false, completed: false, pending: 0, peer_closed: false,
            })));
        }
        _ => return Err(NativeError { status: 6, value: Value::Text(format!("native builder method is not implemented: {method}")) }),
    }
    builder.invalidate_config();
    Ok(Value::None)
}

fn accept_with_policy(initial_handle: u64, method: &str, arguments: &[Value]) -> Result<Value, NativeError> {
    let initial = cloned_builder(initial_handle)?;
    let acceptor_entry = lookup(u64::try_from(argument(arguments, 0)?.int()?).map_err(|_| NativeError::value("invalid acceptor handle"))?)?;
    if method == "validate_server_hello" {
        let versions = initial.get_protocol_versions()?;
        let mut state = acceptor_entry.lock().map_err(|_| NativeError::ssl("native acceptor is poisoned"))?;
        let Object::Acceptor(state) = &mut *state else { return Err(NativeError::value("expected acceptor handle")); };
        let accepted = state.accepted.as_ref().ok_or_else(|| NativeError::ssl("ClientHello is not available"))?;
        if versions.iter().any(|version| accepted.offers_protocol_version(version.version)) { return Ok(Value::None); }
        let mut alert = state.accepted.take().ok_or_else(|| NativeError::ssl("ClientHello is not available"))?.reject(rustls::AlertDescription::ProtocolVersion);
        alert.write_all(&mut state.alert)?;
        return Err(NativeError::ssl("UNSUPPORTED_PROTOCOL"));
    }
    let selected = cloned_builder(u64::try_from(argument(arguments, 1)?.int()?).map_err(|_| NativeError::value("invalid selected context handle"))?)?;
    let capture_message_callback = arguments.get(2).map(Value::boolean).transpose()?.unwrap_or(false);
    let mut config = initial.build_server_config_for_context(&selected)?;
    let mut state = acceptor_entry.lock().map_err(|_| NativeError::ssl("native acceptor is poisoned"))?;
    let Object::Acceptor(state) = &mut *state else { return Err(NativeError::value("expected acceptor handle")); };
    let accepted = state.accepted.take().ok_or_else(|| NativeError::ssl("ClientHello is not available"))?;
    {
        let hello = accepted.client_hello();
        if let Some(mut offers) = hello.alpn() {
            if !offers.any(|offered| config.alpn_protocols.iter().any(|configured| configured == offered)) { config.alpn_protocols.clear(); }
        }
    }
    let verified = Arc::new(Mutex::new(None));
    let _capture = VerificationCapture::enter(Arc::clone(&verified));
    let mut conn = match accepted.into_connection_with_message_callback(
        Arc::new(config),
        capture_message_callback,
    ) {
        Ok(conn) => conn,
        Err((error, mut alert)) => { alert.write_all(&mut state.alert)?; return Err(error.into()); }
    };
    let mut remaining = Cursor::new(std::mem::take(&mut state.remaining));
    while remaining.position() < remaining.get_ref().len() as u64 {
        if conn.read_tls(&mut remaining)? == 0 { return Err(NativeError::ssl("server did not consume buffered TLS records")); }
    }
    initial.session_stats.server_started();
    handle_value(insert(Object::Connection(NativeConnection {
        client: None, conn: conn.into(), verified, sessions: Arc::new(Mutex::new(None)), stats: Arc::clone(&initial.session_stats),
        started: true, completed: false, pending: 0, peer_closed: false,
    })))
}

fn message_events_value(events: Vec<(bool, u16, u16, i32, Vec<u8>)>) -> Value {
    Value::List(events.into_iter().map(|(write, version, content_type, message_type, data)| {
        Value::Tuple(vec![
            Value::Text(if write { "write" } else { "read" }.into()),
            Value::Int(i64::from(version)),
            Value::Int(i64::from(content_type)),
            Value::Int(i64::from(message_type)),
            Value::Bytes(data),
        ])
    }).collect())
}

fn acceptor_call(state: &mut NativeAcceptor, method: &str, arguments: &[Value]) -> Result<Value, NativeError> {
    match method {
        "set_message_callback_enabled" => {
            let enabled = argument(arguments, 0)?.boolean()?;
            if let Some(accepted) = state.accepted.as_mut() {
                accepted.set_message_callback_enabled(enabled);
            } else {
                state.acceptor.set_message_callback_enabled(enabled);
            }
            Ok(Value::None)
        }
        "take_message_events" => {
            let events = match state.accepted.as_mut() {
                Some(accepted) => accepted.take_message_callback_events(),
                None => state.acceptor.take_message_callback_events(),
            }
            .ok_or_else(|| NativeError::ssl("TLS message callback event queue limit exceeded"))?;
            Ok(message_events_value(events))
        }
        "feed" => {
            let data = argument(arguments, 0)?.bytes()?;
            let mut input = Cursor::new(data);
            loop {
                if state.accepted.is_some() { state.remaining.extend_from_slice(&data[input.position() as usize..]); return Ok(Value::Bool(true)); }
                if input.position() == data.len() as u64 { return Ok(Value::Bool(false)); }
                if state.acceptor.read_tls(&mut input)? == 0 { return Ok(Value::Bool(false)); }
                match state.acceptor.accept() {
                    Ok(Some(accepted)) => state.accepted = Some(accepted),
                    Ok(None) => (),
                    Err((error, mut alert)) => { alert.write_all(&mut state.alert)?; return Err(error.into()); }
                }
            }
        }
        "cipher_suites" => {
            let accepted = state.accepted.as_ref().ok_or_else(|| NativeError::ssl("ClientHello is not available"))?;
            Ok(Value::List(accepted.client_hello().cipher_suites().iter().map(|suite| Value::Int(u16::from(*suite) as i64)).collect()))
        }
        "server_name" => Ok(state.accepted.as_ref().and_then(|accepted| accepted.client_hello().server_name().map(str::to_owned)).map(Value::Text).unwrap_or(Value::None)),
        "take_alert" => Ok(Value::Bytes(std::mem::take(&mut state.alert))),
        "reject" => {
            let alert = u8::try_from(argument(arguments, 0)?.int()?).map_err(|_| NativeError::value("invalid TLS alert"))?;
            let accepted = state.accepted.take().ok_or_else(|| NativeError::ssl("ClientHello is not available"))?;
            let mut alert = accepted.reject(rustls::AlertDescription::from(alert));
            let mut output = Vec::new(); alert.write_all(&mut output)?;
            Ok(Value::Bytes(output))
        }
        _ => Err(NativeError { status: 6, value: Value::Text(format!("native acceptor method is not implemented: {method}")) }),
    }
}

fn process(connection: &mut NativeConnection) -> Result<(), NativeError> {
    connection.started = true;
    let _verification = VerificationCapture::enter(Arc::clone(&connection.verified));
    let _sessions = SessionCapture::enter(Arc::clone(&connection.sessions));
    let state = connection.conn.process_new_packets()?;
    connection.pending = state.plaintext_bytes_to_read();
    connection.peer_closed |= state.peer_has_closed();
    if !connection.conn.is_handshaking() && !connection.completed {
        connection.completed = true;
        match &connection.conn {
            rustls::Connection::Client(_) => connection.stats.client_completed(),
            rustls::Connection::Server(conn) => connection.stats.server_completed(conn.handshake_kind() == Some(rustls::HandshakeKind::Resumed)),
        }
    }
    if !connection.conn.is_handshaking()
        && connection.conn.protocol_version() == Some(rustls::ProtocolVersion::TLSv1_3)
        && connection.conn.handshake_kind() != Some(rustls::HandshakeKind::Resumed)
        && connection.sessions.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).is_none()
    {
        if let Some(policy) = &connection.client {
            let verified_chain = connection.verified.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).clone();
            if !policy.require_verified_chain || verified_chain.is_some() {
                let time = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map_err(|error| NativeError::ssl(error.to_string()))?
                    .as_secs();
                *connection.sessions.lock().unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(Arc::new(
                    SessionData::new_tls13_without_ticket(
                        Arc::clone(&policy.context),
                        policy.server_name.to_str().to_string(),
                        verified_chain,
                        time,
                    ),
                ));
            }
        }
    }
    Ok(())
}
fn plaintext(connection: &mut NativeConnection, maximum: usize) -> Result<Vec<u8>, NativeError> {
    let allocation = maximum.min(connection.pending.max(1));
    let mut data = vec![0; allocation];
    match connection.conn.reader().read(&mut data) {
        Ok(0) if maximum > 0 && connection.peer_closed => Err(NativeError { status: 3, value: Value::Text(crate::error::ZERO_RETURN_MESSAGE.into()) }),
        Ok(count) => { data.truncate(count); connection.pending = connection.pending.saturating_sub(count); Ok(data) }
        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => Ok(Vec::new()),
        Err(error) if error.kind() == std::io::ErrorKind::UnexpectedEof => Err(NativeError { status: 4, value: Value::Text("EOF occurred in violation of protocol".into()) }),
        Err(error) => Err(error.into()),
    }
}
fn signature_value(scheme: Option<rustls::SignatureScheme>) -> Value {
    scheme
        .and_then(crate::config::signature_scheme_name)
        .map(|name| Value::Text(name.into()))
        .unwrap_or(Value::None)
}

fn connection_call(connection: &mut NativeConnection, method: &str, arguments: &[Value]) -> Result<Value, NativeError> {
    match method {
        "read_tls" => {
            let data = argument(arguments, 0)?.bytes()?;
            let count = connection.conn.read_tls(&mut Cursor::new(data))?;
            if count > 0 && !connection.started {
                connection.started = true;
                if matches!(connection.conn, rustls::Connection::Server(_)) { connection.stats.server_started(); }
            }
            Ok(Value::Int(count as i64))
        }
        "process_new_packets" => { process(connection)?; Ok(Value::None) }
        "set_message_callback_enabled" => {
            connection.conn.set_message_callback_enabled(argument(arguments, 0)?.boolean()?);
            Ok(Value::None)
        }
        "take_message_events" => {
            let events = connection.conn.take_message_callback_events()
                .ok_or_else(|| NativeError::ssl("TLS message callback event queue limit exceeded"))?;
            Ok(message_events_value(events))
        }
        "read_plaintext" => Ok(Value::Bytes(plaintext(connection, usize::try_from(argument(arguments, 0)?.int()?).map_err(|_| NativeError::value("negative plaintext length"))?)?)),
        "write_plaintext" => Ok(Value::Int(connection.conn.writer().write(argument(arguments, 0)?.bytes()?)? as i64)),
        "write_tls" => { let mut output = Vec::new(); connection.conn.write_tls(&mut output)?; Ok(Value::Bytes(output)) }
        "send_close_notify" => { connection.conn.send_close_notify(); Ok(Value::None) }
        "is_handshaking" => Ok(Value::Bool(connection.conn.is_handshaking())),
        "wants_read" => Ok(Value::Bool(connection.conn.wants_read())),
        "wants_write" => Ok(Value::Bool(connection.conn.wants_write())),
        "pending" => Ok(Value::Int(connection.pending as i64)),
        "peer_certificates" => Ok(connection.conn.peer_certificates().map(|certificates| byte_list(certificates.iter().map(|certificate| certificate.to_vec()).collect())).unwrap_or(Value::None)),
        "verified_certificates" => {
            let chain = connection.verified.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).clone();
            Ok(chain.map(byte_list).unwrap_or(Value::None))
        }
        "alpn_protocol" => Ok(connection.conn.alpn_protocol().map(|value| Value::Bytes(value.to_vec())).unwrap_or(Value::None)),
        "tls_unique" => {
            let data = if connection.conn.is_handshaking() { None } else { match &connection.conn {
                rustls::Connection::Client(conn) => conn.tls_unique(),
                rustls::Connection::Server(conn) => conn.tls_unique(),
            }};
            Ok(data.map(|data| Value::Bytes(data.to_vec())).unwrap_or(Value::None))
        }
        "group" => {
            let group = match &connection.conn {
                rustls::Connection::Client(conn) => conn.negotiated_key_exchange_group(),
                rustls::Connection::Server(conn) => conn.negotiated_key_exchange_group(),
            };
            Ok(group.map(|group| Value::Text(match group.name() {
                rustls::NamedGroup::X25519 => "x25519".into(), name => format!("{name:?}"),
            })).unwrap_or(Value::None))
        }
        "client_sigalg" => {
            let scheme = match &connection.conn {
                rustls::Connection::Client(conn) => conn.local_signature_scheme(),
                rustls::Connection::Server(conn) => conn.peer_signature_scheme(),
            };
            Ok(signature_value(scheme))
        }
        "server_sigalg" => {
            let scheme = match &connection.conn {
                rustls::Connection::Client(conn) => conn.peer_signature_scheme(),
                rustls::Connection::Server(conn) => conn.local_signature_scheme(),
            };
            Ok(signature_value(scheme))
        }
        "protocol_version" => Ok(connection.conn.protocol_version().map(|version| Value::Int(u16::from(version) as i64)).unwrap_or(Value::None)),
        "negotiated_cipher_suite" => Ok(connection.conn.negotiated_cipher_suite().map(|suite| Value::Text(format!("{:?}", suite.suite()))).unwrap_or(Value::None)),
        "negotiated_cipher_suite_bits" => Ok(connection.conn.negotiated_cipher_suite().map(|suite| {
            let name = format!("{:?}", suite.suite()); Value::Int(if name.contains("AES_128") { 128 } else if name.contains("AES_256") || name.contains("CHACHA20") { 256 } else { 0 })
        }).unwrap_or(Value::None)),
        "session_reused" => Ok(Value::Bool(connection.conn.handshake_kind() == Some(rustls::HandshakeKind::Resumed))),
        "session" => Ok(connection.sessions.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).clone()
            .and_then(|session| handle_value(insert(Object::Session(session))).ok()).unwrap_or(Value::None)),
        "set_session" => {
            let session = optional_session(argument(arguments, 0)?)?.ok_or_else(|| NativeError::value("expected SSLSession"))?;
            let policy = connection.client.as_ref().ok_or_else(|| NativeError::value("session can only be specified in client mode"))?;
            validate_session(&session, &policy.context, &policy.server_name, policy.require_verified_chain)?;
            if connection.started || !connection.conn.is_handshaking() { return Err(NativeError::value("Cannot set session after handshake.")); }
            if connection.sessions.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).as_ref().is_some_and(|current| Arc::ptr_eq(current, &session)) {
                return Ok(Value::Bool(false));
            }
            let reserved = session.reserve_explicit().map_err(|e| NativeError::value(e.to_string()))?;
            let _verification = VerificationCapture::enter(Arc::clone(&connection.verified));
            let _capture = SessionCapture::enter(Arc::clone(&connection.sessions));
            let _override = SessionOverride::enter(reserved);
            connection.conn = rustls::ClientConnection::new(Arc::clone(&policy.config), policy.server_name.clone())?.into();
            *connection.sessions.lock().unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(session);
            Ok(Value::Bool(true))
        }
        "ech_status" => match &connection.conn {
            rustls::Connection::Client(client) => Ok(Value::Text(match client.ech_status() {
                rustls::client::EchStatus::NotOffered => "not_offered", rustls::client::EchStatus::Grease => "grease", rustls::client::EchStatus::Offered => "offered", rustls::client::EchStatus::Accepted => "accepted", rustls::client::EchStatus::Rejected => "rejected",
            }.into())),
            rustls::Connection::Server(_) => Err(NativeError::value("server connection has no ECH client status")),
        },
        _ => Err(NativeError { status: 6, value: Value::Text(format!("native connection method is not implemented: {method}")) }),
    }
}

/// # Safety
/// The caller must hold its current interpreter GIL and pass live exception and callback objects belonging to that interpreter. Neither pointer is retained.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn rtls_native_report_unraisable(error: *mut cpython_sys::PyObject, callback: *mut cpython_sys::PyObject) {
    // SAFETY: PyDLL retains the caller's interpreter GIL and both argument objects for this entire call.
    unsafe {
        let kind = (*error.cast::<cpython_sys::_object>()).ob_type;
        cpython_sys::PyErr_SetObject(kind as *mut cpython_sys::PyObject, error);
        cpython_sys::PyErr_WriteUnraisable(callback);
    }
}

fn certificate_value(der: &[u8]) -> Result<Value, NativeError> {
    use crate::cert::{ParsedSanValue, parse_cert_to_rust};
    fn rdns(values: Vec<Vec<(String, String)>>) -> Value {
        Value::Tuple(values.into_iter().map(|rdn| Value::Tuple(rdn.into_iter().map(|(name, value)| Value::Tuple(vec![Value::Text(name), Value::Text(value)])).collect())).collect())
    }
    fn strings(values: Vec<String>) -> Value { Value::Tuple(values.into_iter().map(Value::Text).collect()) }
    let certificate = parse_cert_to_rust(der).map_err(NativeError::value)?;
    let mut values = vec![
        ("version".into(), Value::Int(certificate.version as i64)),
        ("serialNumber".into(), Value::Text(certificate.serial)),
        ("issuer".into(), rdns(certificate.issuer)),
        ("subject".into(), rdns(certificate.subject)),
        ("notBefore".into(), Value::Text(certificate.not_before)),
        ("notAfter".into(), Value::Text(certificate.not_after)),
    ];
    if let Some(names) = certificate.san {
        values.push(("subjectAltName".into(), Value::Tuple(names.into_iter().map(|name| Value::Tuple(vec![
            Value::Text(name.kind.into()), match name.value { ParsedSanValue::Text(text) => Value::Text(text), ParsedSanValue::DirectoryName(names) => rdns(names) },
        ])).collect())));
    }
    if !certificate.ocsp.is_empty() { values.push(("OCSP".into(), strings(certificate.ocsp))); }
    if !certificate.ca_issuers.is_empty() { values.push(("caIssuers".into(), strings(certificate.ca_issuers))); }
    if !certificate.crl_distribution_points.is_empty() { values.push(("crlDistributionPoints".into(), strings(certificate.crl_distribution_points))); }
    Ok(Value::Dict(values))
}

fn optional_session(value: &Value) -> Result<Option<Arc<SessionData>>, NativeError> {
    if matches!(value, Value::None) { return Ok(None); }
    let handle = u64::try_from(value.int()?).map_err(|_| NativeError::value("invalid session handle"))?;
    let entry = lookup(handle)?;
    let entry = entry.lock().map_err(|_| NativeError::ssl("native session is poisoned"))?;
    let Object::Session(session) = &*entry else { return Err(NativeError::value("expected session handle")); };
    Ok(Some(Arc::clone(session)))
}
fn validate_session(session: &SessionData, context: &Arc<ContextIdentity>, name: &ServerName<'_>, require_verified: bool) -> Result<(), NativeError> {
    if !Arc::ptr_eq(&session.context, context) { return Err(NativeError::value("Session refers to a different SSLContext.")); }
    if session.server_name != name.to_str().as_ref() { return Err(NativeError::value("Session is for a different server name.")); }
    if require_verified && session.verified_chain.is_none() { return Err(NativeError::value("Session has no verified certificate path.")); }
    Ok(())
}
fn session_call(session: &Arc<SessionData>, method: &str, arguments: &[Value]) -> Result<Value, NativeError> {
    let (id, time, timeout, has_ticket, lifetime) = session.binding_metadata();
    match method {
        "id" => Ok(Value::Bytes(id.to_vec())),
        "time" => Ok(Value::Int(time as i64)),
        "timeout" => Ok(Value::Int(timeout as i64)),
        "has_ticket" => Ok(Value::Bool(has_ticket)),
        "ticket_lifetime_hint" => Ok(Value::Int(lifetime as i64)),
        "equals" => Ok(Value::Bool(optional_session(argument(arguments, 0)?)?.is_some_and(|other| Arc::ptr_eq(session, &other)))),
        _ => Err(NativeError::value("unknown session property")),
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn rtls_native_claim(reply: u64, handle: u64) -> i32 {
    let result = (|| -> Result<(), NativeError> {
        let entry = lookup(reply)?;
        let mut entry = entry.lock().map_err(|_| NativeError::ssl("native reply is poisoned"))?;
        let Object::Reply { value: Value::Handle(owned), .. } = &mut *entry else { return Err(NativeError::value("reply does not own a TLS object")); };
        if owned.id != handle || handle == 0 { return Err(NativeError::value("reply does not own this handle")); }
        owned.id = 0;
        Ok(())
    })();
    match result { Ok(()) => 0, Err(_) => -1 }
}
