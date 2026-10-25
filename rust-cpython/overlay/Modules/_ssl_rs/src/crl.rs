use rustls::pki_types::CertificateDer;
use webpki::{CertRevocationList, OwnedCertRevocationList};

use crate::policy::{validate_der, validate_pem_footer};

pub struct TrustMaterial {
    pub certificates: Vec<CertificateDer<'static>>,
    pub crls: Vec<Vec<u8>>,
}

pub fn parse_trust_material(pem: &[u8]) -> Result<TrustMaterial, String> {
    let mut certificates = Vec::new();
    let mut crls = Vec::new();
    let mut remaining = pem;
    let certificate_begin = b"-----BEGIN CERTIFICATE-----";
    let certificate_end: &[u8] = b"-----END CERTIFICATE-----";
    let crl_begin = b"-----BEGIN X509 CRL-----";
    let crl_end: &[u8] = b"-----END X509 CRL-----";

    loop {
        let certificate_start = remaining.windows(certificate_begin.len()).position(|window| window == certificate_begin);
        let crl_start = remaining.windows(crl_begin.len()).position(|window| window == crl_begin);
        let (start, end, is_crl) = match (certificate_start, crl_start) {
            (Some(certificate_start), Some(crl_start)) if certificate_start < crl_start =>
                (certificate_start, certificate_end, false),
            (Some(_), Some(crl_start)) => (crl_start, crl_end, true),
            (Some(certificate_start), None) => (certificate_start, certificate_end, false),
            (None, Some(crl_start)) => (crl_start, crl_end, true),
            (None, None) => break,
        };
        let block = &remaining[start..];
        let finish = block.windows(end.len()).position(|window| window == end)
            .ok_or_else(|| if is_crl { "Unterminated CRL PEM" } else { "Unterminated certificate PEM" }.to_string())? + end.len();
        validate_pem_footer(&block[finish..])?;
        let mut input = &block[..finish];
        let item = rustls_pemfile::read_one(&mut input)
            .map_err(|error| format!("Invalid {} PEM: {error}", if is_crl { "CRL" } else { "certificate" }))?
            .ok_or_else(|| format!("Empty {} PEM", if is_crl { "CRL" } else { "certificate" }))?;
        match (is_crl, item) {
            (false, rustls_pemfile::Item::X509Certificate(certificate)) => {
                validate_der(certificate.as_ref())?;
                certificates.push(certificate);
            }
            (true, rustls_pemfile::Item::Crl(crl)) => {
                OwnedCertRevocationList::from_der(crl.as_ref())
                    .map_err(|error| format!("Invalid CRL DER: {error}"))?;
                crls.push(crl.to_vec());
            }
            (false, _) => return Err("Invalid certificate PEM block".into()),
            (true, _) => return Err("Invalid CRL PEM block".into()),
        }
        remaining = &block[finish..];
    }

    if certificates.is_empty() && crls.is_empty() {
        return Err("No certificates or CRLs found in PEM data".into());
    }
    Ok(TrustMaterial { certificates, crls })
}

pub fn parse_crls(crls_der: Vec<Vec<u8>>) -> Result<Vec<CertRevocationList<'static>>, String> {
    crls_der.into_iter().map(|der| {
        OwnedCertRevocationList::from_der(&der)
            .map(CertRevocationList::from)
            .map_err(|error| format!("Invalid CRL DER: {error}"))
    }).collect()
}
