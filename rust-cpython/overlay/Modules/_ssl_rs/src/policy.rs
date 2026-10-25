use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
use rustls::server::danger::{ClientCertVerified, ClientCertVerifier};
use rustls::crypto::{verify_tls12_signature, verify_tls13_signature, WebPkiSupportedAlgorithms};
use rustls::pki_types::{CertificateDer, ServerName, UnixTime};
use rustls::{CertificateError, DigitallySignedStruct, DistinguishedName, Error, SignatureScheme};
use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use webpki::{CertRevocationList, ExpirationPolicy, RevocationCheckDepth, RevocationOptionsBuilder, UnknownStatusPolicy};

use crate::crl::parse_crls;
use crate::trust::{canonical_issuer_name_from_der, canonical_subject_name_from_der, subject_name_hash};

pub type VerifiedChain = Arc<Mutex<Option<Vec<Vec<u8>>>>>;

thread_local! {
    static CURRENT_VERIFIED_CHAIN: std::cell::RefCell<Option<VerifiedChain>> = const { std::cell::RefCell::new(None) };
}

pub struct VerificationCapture {
    previous: Option<VerifiedChain>,
    thread: std::marker::PhantomData<std::rc::Rc<()>>,
}

impl VerificationCapture {
    pub fn enter(chain: VerifiedChain) -> Self {
        let previous = CURRENT_VERIFIED_CHAIN.with(|current| current.replace(Some(chain)));
        Self { previous, thread: std::marker::PhantomData }
    }
}

impl Drop for VerificationCapture {
    fn drop(&mut self) {
        CURRENT_VERIFIED_CHAIN.with(|current| { current.replace(self.previous.take()); });
    }
}

pub fn capture_current_verified_chain() -> Option<Vec<Vec<u8>>> {
    CURRENT_VERIFIED_CHAIN.with(|current| {
        current.borrow().as_ref().and_then(|chain| chain.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).clone())
    })
}

pub fn restore_current_verified_chain(chain: Vec<Vec<u8>>) -> bool {
    CURRENT_VERIFIED_CHAIN.with(|current| {
        if let Some(sink) = current.borrow().as_ref() {
            *sink.lock().unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(chain);
            true
        } else { false }
    })
}

fn record_verified_chain(chain: Vec<Vec<u8>>) -> Result<(), Error> {
    if restore_current_verified_chain(chain) { Ok(()) }
    else { Err(Error::General("Certificate verification ran outside a connection scope".into())) }
}
use x509_parser::prelude::*;
use x509_parser::extensions::ParsedExtension;

pub const VERIFY_X509_STRICT: i32 = 0x20;
pub const VERIFY_X509_TRUSTED_FIRST: i32 = 0x8000;
pub const VERIFY_X509_PARTIAL_CHAIN: i32 = 0x80000;
pub const VERIFY_CRL_CHECK_LEAF: i32 = 0x4;
pub const VERIFY_CRL_CHECK_CHAIN: i32 = 0xC;
pub const SUPPORTED_VERIFY_FLAGS: i32 = VERIFY_X509_STRICT | VERIFY_X509_TRUSTED_FIRST | VERIFY_X509_PARTIAL_CHAIN | VERIFY_CRL_CHECK_CHAIN;

pub fn validate_der(der: &[u8]) -> Result<(), String> {
    let (rest, _) = X509Certificate::from_der(der).map_err(|e| format!("Invalid certificate DER: {e}"))?;
    if !rest.is_empty() {
        return Err("Trailing data after certificate DER".into());
    }
    webpki::anchor_from_trusted_cert(&CertificateDer::from(der))
        .map_err(|e| format!("Invalid certificate: {e}"))?;
    Ok(())
}

pub(crate) fn validate_pem_footer(suffix: &[u8]) -> Result<(), String> {
    let line_end = suffix.iter().position(|byte| *byte == b'\n').unwrap_or(suffix.len());
    if suffix[..line_end].iter().any(|byte| !crate::trust::is_ascii_space(*byte)) {
        return Err("Invalid PEM footer".into());
    }
    Ok(())
}

pub(crate) fn private_key_pem(pem: &[u8]) -> Result<&[u8], String> {
    let labels: &[(&[u8], &[u8])] = &[
        (b"-----BEGIN PRIVATE KEY-----", b"-----END PRIVATE KEY-----"),
        (b"-----BEGIN RSA PRIVATE KEY-----", b"-----END RSA PRIVATE KEY-----"),
        (b"-----BEGIN EC PRIVATE KEY-----", b"-----END EC PRIVATE KEY-----"),
        (b"-----BEGIN ENCRYPTED PRIVATE KEY-----", b"-----END ENCRYPTED PRIVATE KEY-----"),
    ];
    let (start, end) = labels.iter().filter_map(|(begin, end)| {
        pem.windows(begin.len()).position(|window| window == *begin).map(|start| (start, *end))
    }).min_by_key(|(start, _)| *start).ok_or_else(|| "No private key found in PEM data".to_string())?;
    let key = &pem[start..];
    let finish = key.windows(end.len()).position(|window| window == end)
        .ok_or_else(|| "Unterminated private key PEM".to_string())? + end.len();
    validate_pem_footer(&key[finish..])?;
    Ok(&key[..finish])
}

pub fn parse_certificates(pem: &[u8]) -> Result<Vec<CertificateDer<'static>>, String> {
    let mut certs = Vec::new();
    let mut remaining = pem;
    let begin = b"-----BEGIN CERTIFICATE-----";
    let end = b"-----END CERTIFICATE-----";
    while let Some(start) = remaining.windows(begin.len()).position(|w| w == begin) {
        remaining = &remaining[start..];
        let finish = remaining.windows(end.len()).position(|w| w == end)
            .ok_or_else(|| "Unterminated certificate PEM".to_string())? + end.len();
        validate_pem_footer(&remaining[finish..])?;
        let cert = rustls_pemfile::certs(&mut &remaining[..finish]).next()
            .ok_or_else(|| "Empty certificate PEM".to_string())?
            .map_err(|e| format!("Invalid certificate PEM: {e}"))?;
        validate_der(cert.as_ref())?;
        certs.push(cert);
        remaining = &remaining[finish..];
    }
    if certs.is_empty() {
        return Err("No certificates found in PEM data".into());
    }
    Ok(certs)
}

const RSA_ENCRYPTION_OID: &str = "1.2.840.113549.1.1.1";
const RSA_SHA1_SIGNATURE_OID: &str = "1.2.840.113549.1.1.5";

fn null_or_absent_parameters(
    parameters: Option<&x509_parser::der_parser::asn1_rs::Any<'_>>,
) -> bool {
    match parameters {
        None => true,
        Some(parameters) => {
            parameters.header.class() == x509_parser::der_parser::asn1_rs::Class::Universal
                && parameters.tag() == x509_parser::der_parser::asn1_rs::Tag::Null
                && parameters.data.is_empty()
        }
    }
}

fn self_signed(der: &CertificateDer<'_>, supported: WebPkiSupportedAlgorithms) -> bool {
    let Ok((rest, cert)) = X509Certificate::from_der(der.as_ref()) else { return false; };
    if !rest.is_empty() || cert.signature_algorithm != cert.tbs_certificate.signature || !crate::trust::names_equal(cert.subject().as_raw(), cert.issuer().as_raw()) { return false; }
    let signature_oid = cert.signature_algorithm.algorithm.to_id_string();
    if signature_oid == RSA_SHA1_SIGNATURE_OID {
        let public_key = cert.public_key();
        return public_key.algorithm.algorithm.to_id_string() == RSA_ENCRYPTION_OID
            && null_or_absent_parameters(cert.signature_algorithm.parameters.as_ref())
            && null_or_absent_parameters(public_key.algorithm.parameters.as_ref())
            && cert.verify_signature(None).is_ok();
    }
    let Ok(key) = webpki::EndEntityCert::try_from(der) else { return false; };
    supported.all.iter().any(|algorithm| {
        let id = algorithm.signature_alg_id();
        let Ok((parameters, oid)) = x509_parser::der_parser::Oid::from_der(id.as_ref()) else { return false; };
        if oid != cert.signature_algorithm.algorithm { return false; }
        let parsed_parameters = if parameters.is_empty() { None } else {
            let Ok((remaining, value)) = x509_parser::der_parser::asn1_rs::Any::from_der(parameters) else { return false; };
            if !remaining.is_empty() { return false; }
            Some(value)
        };
        if parsed_parameters != cert.signature_algorithm.parameters { return false; }
        key.verify_signature(*algorithm, cert.tbs_certificate.as_ref(), &cert.signature_value.data).is_ok()
    })
}

fn check_certificate(der: &[u8], is_anchor: bool, depth: usize, now: UnixTime, client: bool, strict: bool) -> Result<(), webpki::Error> {
    use webpki::CertificatePolicyViolation as Violation;

    let invalid = webpki::Error::ExtensionValueInvalid;
    let violation = |cause| webpki::Error::CertificatePolicyViolation(cause);
    let (rest, cert) = X509Certificate::from_der(der).map_err(|_| invalid.clone())?;
    if !rest.is_empty() { return Err(invalid); }
    let mut seen = HashSet::new();
    let mut basic = None;
    let mut usage = None;
    let mut san = None;
    let mut aki = false;
    let mut ski = false;
    let mut aki_critical = false;
    let mut ski_critical = false;
    for extension in cert.extensions() {
        if !seen.insert(extension.oid.clone()) { return Err(invalid); }
        let oid = extension.oid.to_id_string();
        if oid == "1.3.6.1.5.5.7.1.14" { return Err(webpki::Error::UnsupportedCriticalExtension); }
        if extension.critical && !matches!(oid.as_str(),
            "2.16.840.1.113730.1.1" | "2.5.29.15" | "2.5.29.17" | "2.5.29.19" |
            "2.5.29.32" | "2.5.29.31" | "2.5.29.37" | "2.5.29.36" |
            "2.5.29.30" | "2.5.29.33" | "2.5.29.54" | "1.3.6.1.5.5.7.48.1.5"
        ) { return Err(webpki::Error::UnsupportedCriticalExtension); }
        match extension.parsed_extension() {
            ParsedExtension::BasicConstraints(value) => basic = Some((value, extension.critical)),
            ParsedExtension::KeyUsage(value) => usage = Some(value),
            ParsedExtension::NSCertType(value) if depth == 0 => {
                if !(if client { value.ssl_client() } else { value.ssl_server() }) {
                    return Err(violation(Violation::InvalidPurpose));
                }
            }
            ParsedExtension::SubjectAlternativeName(value) => san = Some((value, extension.critical)),
            ParsedExtension::AuthorityKeyIdentifier(value) => {
                aki_critical = extension.critical;
                aki = value.key_identifier.is_some();
            }
            ParsedExtension::SubjectKeyIdentifier(_) => {
                ski_critical = extension.critical;
                ski = true;
            }
            ParsedExtension::ExtendedKeyUsage(value) if is_anchor => {
                if !(if client { value.client_auth } else { value.server_auth }) {
                    return Err(violation(Violation::InvalidPurpose));
                }
            }
            ParsedExtension::ParseError { .. } => return Err(invalid),
            ParsedExtension::UnsupportedExtension { .. } if extension.critical => return Err(webpki::Error::UnsupportedCriticalExtension),
            _ => {}
        }
    }
    let ca = basic.is_some_and(|(value, _)| value.ca);
    let timestamp = now.as_secs() as i64;
    if timestamp < cert.validity().not_before.timestamp() {
        return Err(webpki::Error::CertNotValidYet {
            time: now,
            not_before: UnixTime::since_unix_epoch(std::time::Duration::from_secs(
                cert.validity().not_before.timestamp().max(0) as u64,
            )),
        });
    }
    if timestamp >= cert.validity().not_after.timestamp() {
        return Err(webpki::Error::CertExpired {
            time: now,
            not_after: UnixTime::since_unix_epoch(std::time::Duration::from_secs(
                cert.validity().not_after.timestamp().max(0) as u64,
            )),
        });
    }
    if depth > 0 && basic.is_some_and(|(value, _)| !value.ca) {
        return Err(webpki::Error::EndEntityUsedAsCa);
    }
    if depth > 0 && usage.is_some_and(|value| !value.key_cert_sign()) {
        return Err(webpki::Error::EndEntityUsedAsCa);
    }
    if depth == 0 && usage.is_some_and(|value| if client {
        !(value.digital_signature() || value.key_agreement())
    } else {
        !(value.digital_signature() || value.key_encipherment() || value.key_agreement())
    }) {
        return Err(violation(Violation::InvalidPurpose));
    }
    if !strict { return Ok(()); }
    if depth > 0 && !ca { return Err(violation(Violation::InvalidCaCertificate)); }
    if basic.is_some_and(|(value, _)| value.path_len_constraint.is_some()) {
        if !ca { return Err(violation(Violation::PathLengthOnNonCaCertificate)); }
        if !usage.is_some_and(|value| value.key_cert_sign()) {
            return Err(violation(Violation::PathLengthWithoutKeyCertSign));
        }
    }
    if ca && !basic.is_some_and(|(_, critical)| critical) {
        return Err(violation(Violation::NoncriticalCaBasicConstraints));
    }
    if ca && usage.is_none() { return Err(violation(Violation::CaMissingKeyUsage)); }
    if !ca && usage.is_some_and(|value| value.key_cert_sign()) {
        return Err(violation(Violation::KeyCertSignOnNonCaCertificate));
    }
    if cert.issuer().iter().next().is_none() {
        return Err(violation(Violation::EmptyIssuerName));
    }
    if cert.subject().iter().next().is_none() {
        if ca || usage.is_some_and(|value| value.crl_sign()) {
            return Err(violation(Violation::EmptySubjectName));
        }
        if !san.is_some_and(|(_, critical)| critical) {
            return Err(violation(Violation::EmptySubjectWithNoncriticalSubjectAlternativeName));
        }
    }
    if san.is_some_and(|(value, _)| value.general_names.is_empty()) {
        return Err(violation(Violation::EmptySubjectAlternativeName));
    }
    if cert.signature_algorithm != cert.tbs_certificate.signature {
        return Err(violation(Violation::SignatureAlgorithmMismatch));
    }
    if aki_critical { return Err(violation(Violation::CriticalAuthorityKeyIdentifier)); }
    if ski_critical { return Err(violation(Violation::CriticalSubjectKeyIdentifier)); }
    if cert.version().0 >= 2 {
        if !is_anchor && !aki { return Err(violation(Violation::MissingAuthorityKeyIdentifier)); }
        if ca && !ski { return Err(violation(Violation::MissingSubjectKeyIdentifier)); }
    } else if !cert.extensions().is_empty() {
        return Err(violation(Violation::ExtensionsRequireX509V3));
    }
    Ok(())
}

fn check_issuer(child: &[u8], parent: &[u8]) -> Result<(), webpki::Error> {
    let invalid = webpki::Error::UnknownIssuer;
    let (_, child) = X509Certificate::from_der(child).map_err(|_| invalid.clone())?;
    let (_, parent) = X509Certificate::from_der(parent).map_err(|_| invalid.clone())?;
    for extension in child.extensions() {
        if let ParsedExtension::AuthorityKeyIdentifier(aki) = extension.parsed_extension() {
            if let Some(key_id) = &aki.key_identifier {
                for extension in parent.extensions() {
                    if let ParsedExtension::SubjectKeyIdentifier(ski) = extension.parsed_extension() {
                        if key_id.0 != ski.0 { return Err(invalid); }
                    }
                }
            }
            if aki.authority_cert_serial.is_some_and(|serial| serial != parent.raw_serial()) { return Err(invalid); }
            if let Some(names) = &aki.authority_cert_issuer {
                if !names.iter().any(|name| matches!(name, x509_parser::extensions::GeneralName::DirectoryName(name) if crate::trust::names_equal(name.as_raw(), parent.issuer().as_raw()))) { return Err(invalid); }
            }
        }
    }
    Ok(())
}

fn common_name_matches(der: &[u8], name: &ServerName<'_>) -> bool {
    let ServerName::DnsName(expected) = name else { return false; };
    let Ok((_, certificate)) = X509Certificate::from_der(der) else { return false; };
    for extension in certificate.extensions() {
        if let ParsedExtension::SubjectAlternativeName(san) = extension.parsed_extension() {
            if san.general_names.iter().any(|name| matches!(name, GeneralName::DNSName(_))) { return false; }
        }
    }
    let matches = certificate.subject().iter_common_name().any(|attribute| {
        common_name_value(attribute).ok().is_some_and(|presented| {
            webpki::common_name_matches(&presented, expected).unwrap_or(false)
        })
    });
    matches
}

fn common_name_value(attribute: &AttributeTypeAndValue<'_>) -> Result<String, webpki::Error> {
    use x509_parser::der_parser::asn1_rs::Tag;
    let invalid = webpki::Error::MalformedDnsIdentifier;
    match attribute.attr_value().tag() {
        Tag::BmpString => {
            if attribute.attr_value().data.len() % 2 != 0 { return Err(invalid); }
            attribute.attr_value().as_bmpstring().map(|value| value.string()).map_err(|_| invalid)
        }
        Tag::UniversalString => attribute.attr_value().as_universalstring().map(|value| value.string()).map_err(|_| invalid),
        Tag::TeletexString => attribute.attr_value().as_teletexstring().map(|value| value.as_ref().to_string()).map_err(|_| invalid),
        _ => attribute.as_str().map(str::to_string).map_err(|_| invalid),
    }
}

fn constraint_dns_common_name(name: &str) -> Result<Option<&str>, webpki::Error> {
    let name = name.trim_end_matches('\0');
    if name.contains('\0') { return Err(webpki::Error::NameConstraintViolation); }
    let bytes = name.as_bytes();
    let mut multiple_labels = false;
    for (index, byte) in bytes.iter().copied().enumerate() {
        if byte.is_ascii_alphanumeric() || byte == b'_' { continue; }
        if index > 0 && index + 1 < bytes.len() {
            if byte == b'-' { continue; }
            if byte == b'.' && bytes[index + 1] != b'.' && bytes[index - 1] != b'-' && bytes[index + 1] != b'-' {
                multiple_labels = true;
                continue;
            }
        }
        return Ok(None);
    }
    Ok(multiple_labels.then_some(name))
}

#[derive(Debug)]
pub struct PathVerifier {
    trusted: Vec<CertificateDer<'static>>,
    crls: Vec<CertRevocationList<'static>>,
    capath_dirs: Vec<PathBuf>,
    loaded_capath_certs: Arc<Mutex<Vec<Vec<u8>>>>,
    flags: i32,
    hostname: bool,
    common_name: bool,
    optional: bool,
    supported: WebPkiSupportedAlgorithms,
    hints: Vec<DistinguishedName>,
    allowed_schemes: Vec<SignatureScheme>,
}

impl PathVerifier {
    pub fn new(
        trusted: Vec<Vec<u8>>,
        capath_dirs: Vec<PathBuf>,
        loaded_capath_certs: Arc<Mutex<Vec<Vec<u8>>>>,
        crls_der: Vec<Vec<u8>>,
        flags: i32,
        hostname: bool,
        optional: bool,
        provider: &Arc<rustls::crypto::CryptoProvider>,
        allowed_schemes: Vec<SignatureScheme>,
    ) -> Result<Self, String> {
        let crls = parse_crls(crls_der)?;
        let mut trusted: Vec<CertificateDer<'static>> = trusted.into_iter().map(CertificateDer::from).collect();
        for der in loaded_capath_certs.lock().unwrap_or_else(|poisoned| poisoned.into_inner()).iter() {
            if !trusted.iter().any(|cert| cert.as_ref() == der.as_slice()) {
                trusted.push(CertificateDer::from(der.clone()));
            }
        }
        Ok(Self { trusted, crls, capath_dirs, loaded_capath_certs, flags, hostname, common_name: true, optional,
            supported: provider.signature_verification_algorithms, hints: Vec::new(), allowed_schemes }
        )
    }

    pub fn with_common_name(mut self, enabled: bool) -> Self {
        self.common_name = enabled;
        self
    }

    fn extend_trusted_from_capath(
        &self,
        leaf: &CertificateDer<'_>,
        sent: &[CertificateDer<'_>],
        trusted: &mut Vec<CertificateDer<'static>>,
    ) -> Result<(), Error> {
        let invalid = |error| Error::InvalidCertificate(CertificateError::Other(
            rustls::OtherError(Arc::new(error)),
        ));
        let mut requested = Vec::<(Vec<u8>, u32)>::new();
        for certificate in std::iter::once(leaf).chain(sent.iter()) {
            let issuer = canonical_issuer_name_from_der(certificate.as_ref())
                .map_err(|_| invalid(webpki::Error::BadDer))?;
            let hash = subject_name_hash(&issuer);
            if !requested.iter().any(|(name, _)| name == &issuer) {
                requested.push((issuer, hash));
            }
        }

        let mut loaded = self.loaded_capath_certs.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        for der in loaded.iter() {
            if !trusted.iter().any(|certificate| certificate.as_ref() == der.as_slice()) {
                trusted.push(CertificateDer::from(der.clone()));
            }
        }
        for (issuer, hash) in requested {
            let has_issuer = trusted.iter().any(|certificate| {
                canonical_subject_name_from_der(certificate.as_ref())
                    .is_ok_and(|subject| subject == issuer)
            });
            if has_issuer {
                continue;
            }
            for directory in &self.capath_dirs {
                let mut index = 0usize;
                loop {
                    let filename = format!("{hash:08x}.{index}");
                    let contents = match std::fs::read(directory.join(filename)) {
                        Ok(contents) => contents,
                        Err(_) => break,
                    };
                    let certificates = match parse_certificates(&contents) {
                        Ok(certificates) => certificates,
                        Err(_) => break,
                    };
                    for certificate in certificates {
                        let der = certificate.to_vec();
                        if !loaded.contains(&der) {
                            loaded.push(der.clone());
                        }
                        if !trusted.iter().any(|root| root.as_ref() == der.as_slice()) {
                            trusted.push(CertificateDer::from(der));
                        }
                    }
                    let Some(next_index) = index.checked_add(1) else { break; };
                    index = next_index;
                }
            }
        }
        Ok(())
    }

    fn verify(&self, leaf: &CertificateDer<'_>, sent: &[CertificateDer<'_>], now: UnixTime, client: bool) -> Result<(), Error> {
        let invalid = |e: webpki::Error| match e {
            webpki::Error::UnknownIssuer => Error::InvalidCertificate(CertificateError::UnknownIssuer),
            error => Error::InvalidCertificate(CertificateError::Other(rustls::OtherError(Arc::new(error)))),
        };
        let crl_check = self.flags & VERIFY_CRL_CHECK_LEAF != 0;
        if crl_check && self.crls.is_empty() {
            return Err(invalid(webpki::Error::UnknownRevocationStatus));
        }
        let mut trusted = self.trusted.clone();
        self.extend_trusted_from_capath(leaf, sent, &mut trusted)?;
        if !crl_check && trusted.iter().any(|root| root.as_ref() == leaf.as_ref()
            && (self.flags & VERIFY_X509_PARTIAL_CHAIN != 0 || self_signed(root, self.supported))) {
            check_certificate(leaf.as_ref(), true, 0, now, client, false).map_err(invalid)?;
            let (_, parsed) = X509Certificate::from_der(leaf.as_ref())
                .map_err(|_| invalid(webpki::Error::BadDer))?;
            if let Some(usage) = parsed.key_usage().map_err(|_| invalid(webpki::Error::ExtensionValueInvalid))? {
                if client && !usage.value.digital_signature() {
                    return Err(invalid(webpki::Error::ExtensionValueInvalid));
                }
                if !client && !(usage.value.digital_signature() || usage.value.key_encipherment() || usage.value.key_agreement()) {
                    return Err(invalid(webpki::Error::ExtensionValueInvalid));
                }
            }
            record_verified_chain(vec![leaf.to_vec()])?;
            return Ok(());
        }
        let cert = webpki::EndEntityCert::try_from(leaf).map_err(invalid)?;
        let mut intermediates = Vec::new();
        if self.flags & VERIFY_X509_TRUSTED_FIRST != 0 { intermediates.extend(trusted.iter().cloned()); }
        intermediates.extend_from_slice(sent);
        if self.flags & VERIFY_X509_TRUSTED_FIRST == 0 { intermediates.extend(trusted.iter().cloned()); }
        let mut last_error = webpki::Error::UnknownIssuer;
        let crls: Vec<_> = self.crls.iter().collect();
        let revocation = if crl_check {
            Some(RevocationOptionsBuilder::new(&crls)
                .map_err(|_| invalid(webpki::Error::UnknownRevocationStatus))?
                .with_depth(if self.flags & VERIFY_CRL_CHECK_CHAIN == VERIFY_CRL_CHECK_CHAIN {
                    RevocationCheckDepth::Chain
                } else {
                    RevocationCheckDepth::EndEntity
                })
                .with_status_policy(UnknownStatusPolicy::Deny)
                .with_expiration_policy(ExpirationPolicy::Enforce)
                .build())
        } else {
            None
        };
        for root in &trusted {
            if self.flags & VERIFY_X509_PARTIAL_CHAIN == 0 && !self_signed(root, self.supported) { continue; }
            let anchor = webpki::anchor_from_trusted_cert(root).map_err(invalid)?;
            let anchors = [anchor];
            let policy = |path: &webpki::VerifiedPath<'_>| {
                if self.common_name {
                    let (_, parsed_leaf) = X509Certificate::from_der(leaf.as_ref()).map_err(|_| webpki::Error::BadDer)?;
                    let dns_san = parsed_leaf.extensions().iter().any(|extension| {
                        matches!(extension.parsed_extension(), ParsedExtension::SubjectAlternativeName(san)
                            if san.general_names.iter().any(|name| matches!(name, GeneralName::DNSName(_))))
                    });
                    if !dns_san {
                        for attribute in parsed_leaf.subject().iter_common_name() {
                            let name = common_name_value(attribute)?;
                            if let Some(name) = constraint_dns_common_name(&name)? {
                                path.verify_common_name_constraints(name)?;
                            }
                        }
                    }
                }
                let strict = self.flags & VERIFY_X509_STRICT != 0;
                check_certificate(leaf.as_ref(), false, 0, now, client, strict)?;
                let mut previous = leaf.clone();
                let mut depth = 1;
                let mut non_self_issued = 0;
                for intermediate in path.intermediate_certificates() {
                    let der = intermediate.der();
                    check_issuer(previous.as_ref(), der.as_ref())?;
                    check_certificate(der.as_ref(), false, depth, now, client, strict)?;
                    previous = der.clone();
                    let (_, parsed) = X509Certificate::from_der(der.as_ref()).map_err(|_| webpki::Error::BadDer)?;
                    if !crate::trust::names_equal(parsed.subject().as_raw(), parsed.issuer().as_raw()) { non_self_issued += 1; }
                    depth += 1;
                }
                check_issuer(previous.as_ref(), root.as_ref())?;
                check_certificate(root.as_ref(), true, depth, now, client, strict)?;
                if self.flags & VERIFY_CRL_CHECK_CHAIN == VERIFY_CRL_CHECK_CHAIN
                    && root.as_ref() != leaf.as_ref()
                {
                    revocation
                        .as_ref()
                        .ok_or(webpki::Error::UnknownRevocationStatus)?
                        .check_trusted_certificate(
                            root,
                            self.supported.all,
                            now,
                            crate::trust::name_contents_equal,
                        )?;
                }
                let (_, parsed) = X509Certificate::from_der(root.as_ref()).map_err(|_| webpki::Error::BadDer)?;
                if parsed.basic_constraints().map_err(|_| webpki::Error::ExtensionValueInvalid)?
                    .and_then(|extension| extension.value.path_len_constraint)
                    .is_some_and(|limit| non_self_issued > limit) { return Err(webpki::Error::PathLenConstraintViolated); }
                Ok(())
            };
            let usage = if client { webpki::KeyUsage::client_auth() } else { webpki::KeyUsage::server_auth() };
            match cert.verify_for_usage_with_name_comparison(self.supported.all, &anchors, &intermediates, now, usage, revocation, Some(&policy), crate::trust::name_contents_equal) {
                Ok(path) => {
                    let mut chain = vec![leaf.to_vec()];
                    chain.extend(path.intermediate_certificates().map(|cert| cert.der().to_vec()));
                    if chain.last().is_none_or(|cert| cert.as_slice() != root.as_ref()) { chain.push(root.to_vec()); }
                    record_verified_chain(chain)?;
                    return Ok(());
                },
                Err(e) => last_error = e,
            }
        }
        Err(invalid(last_error))
    }
}

impl ServerCertVerifier for PathVerifier {
    fn verify_server_cert(&self, leaf: &CertificateDer<'_>, intermediates: &[CertificateDer<'_>], name: &ServerName<'_>, _: &[u8], now: UnixTime) -> Result<ServerCertVerified, Error> {
        self.verify(leaf, intermediates, now, false)?;
        if self.hostname {
            let cert = rustls::server::ParsedCertificate::try_from(leaf)?;
            match rustls::client::verify_server_name(&cert, name) {
                Ok(()) => {}
                Err(Error::InvalidCertificate(CertificateError::NotValidForName))
                | Err(Error::InvalidCertificate(CertificateError::NotValidForNameContext { .. }))
                    if self.common_name && common_name_matches(leaf.as_ref(), name) => {}
                Err(error) => return Err(error),
            }
        }
        Ok(ServerCertVerified::assertion())
    }
    fn verify_tls12_signature(&self, message: &[u8], cert: &CertificateDer<'_>, signature: &DigitallySignedStruct) -> Result<HandshakeSignatureValid, Error> {
        if !self.allowed_schemes.contains(&signature.scheme) {
            return Err(Error::PeerMisbehaved(rustls::PeerMisbehaved::SignedHandshakeWithUnadvertisedSigScheme));
        }
        verify_tls12_signature(message, cert, signature, &self.supported)
    }
    fn verify_tls13_signature(&self, message: &[u8], cert: &CertificateDer<'_>, signature: &DigitallySignedStruct) -> Result<HandshakeSignatureValid, Error> {
        if !self.allowed_schemes.contains(&signature.scheme) {
            return Err(Error::PeerMisbehaved(rustls::PeerMisbehaved::SignedHandshakeWithUnadvertisedSigScheme));
        }
        verify_tls13_signature(message, cert, signature, &self.supported)
    }
    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> { self.allowed_schemes.clone() }
}

impl ClientCertVerifier for PathVerifier {
    fn client_auth_mandatory(&self) -> bool { !self.optional }
    fn root_hint_subjects(&self) -> &[DistinguishedName] { &self.hints }
    fn verify_client_cert(&self, leaf: &CertificateDer<'_>, intermediates: &[CertificateDer<'_>], now: UnixTime) -> Result<ClientCertVerified, Error> {
        self.verify(leaf, intermediates, now, true)?;
        Ok(ClientCertVerified::assertion())
    }
    fn verify_tls12_signature(&self, message: &[u8], cert: &CertificateDer<'_>, signature: &DigitallySignedStruct) -> Result<HandshakeSignatureValid, Error> {
        if !self.allowed_schemes.contains(&signature.scheme) {
            return Err(Error::PeerMisbehaved(rustls::PeerMisbehaved::SignedHandshakeWithUnadvertisedSigScheme));
        }
        verify_tls12_signature(message, cert, signature, &self.supported)
    }
    fn verify_tls13_signature(&self, message: &[u8], cert: &CertificateDer<'_>, signature: &DigitallySignedStruct) -> Result<HandshakeSignatureValid, Error> {
        if !self.allowed_schemes.contains(&signature.scheme) {
            return Err(Error::PeerMisbehaved(rustls::PeerMisbehaved::SignedHandshakeWithUnadvertisedSigScheme));
        }
        verify_tls13_signature(message, cert, signature, &self.supported)
    }
    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> { self.allowed_schemes.clone() }
}

#[cfg(test)]
mod expiry_tests {
    use super::*;

    fn check_expiry(pem: &[u8], anchor: bool, depth: usize) {
        let certificates = parse_certificates(pem).unwrap();
        let certificate = certificates[0].as_ref();
        let (_, parsed) = X509Certificate::from_der(certificate).unwrap();
        let expires = parsed.validity().not_after.timestamp() as u64;
        let time = |seconds| UnixTime::since_unix_epoch(std::time::Duration::from_secs(seconds));
        assert!(check_certificate(certificate, anchor, depth, time(expires - 1), false, false).is_ok());
        for seconds in [expires, expires + 1] {
            assert!(matches!(
                check_certificate(certificate, anchor, depth, time(seconds), false, false),
                Err(webpki::Error::CertExpired { .. })
            ));
        }
    }

    #[test]
    fn leaf_expires_at_not_after() {
        check_expiry(include_bytes!("../../tests/certdata/keycert3.pem"), false, 0);
    }

    #[test]
    fn intermediate_expires_at_not_after() {
        check_expiry(include_bytes!("../../tests/certdata/pycacert.pem"), false, 1);
    }

    #[test]
    fn anchor_expires_at_not_after() {
        check_expiry(include_bytes!("../../tests/certdata/pycacert.pem"), true, 2);
    }
}
