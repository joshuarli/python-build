use rustls::client::danger::{HandshakeSignatureValid, ServerCertVerified, ServerCertVerifier};
use rustls::crypto::{verify_tls12_signature, verify_tls13_signature, WebPkiSupportedAlgorithms};
use rustls::pki_types::{CertificateDer, ServerName, UnixTime};
use rustls::{DigitallySignedStruct, Error, SignatureScheme};

#[derive(Debug)]
pub struct NoVerifier {
    supported: WebPkiSupportedAlgorithms,
    allowed_schemes: Vec<SignatureScheme>,
}

impl NoVerifier {
    pub fn new(supported: WebPkiSupportedAlgorithms, allowed_schemes: Vec<SignatureScheme>) -> Self { Self { supported, allowed_schemes } }
}

impl ServerCertVerifier for NoVerifier {
    fn verify_server_cert(
        &self, _: &CertificateDer<'_>, _: &[CertificateDer<'_>],
        _: &ServerName<'_>, _: &[u8], _: UnixTime,
    ) -> Result<ServerCertVerified, Error> {
        Ok(ServerCertVerified::assertion())
    }

    fn verify_tls12_signature(
        &self, message: &[u8], cert: &CertificateDer<'_>, signature: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, Error> {
        if !self.allowed_schemes.contains(&signature.scheme) {
            return Err(Error::PeerMisbehaved(rustls::PeerMisbehaved::SignedHandshakeWithUnadvertisedSigScheme));
        }
        verify_tls12_signature(message, cert, signature, &self.supported)
    }

    fn verify_tls13_signature(
        &self, message: &[u8], cert: &CertificateDer<'_>, signature: &DigitallySignedStruct,
    ) -> Result<HandshakeSignatureValid, Error> {
        if !self.allowed_schemes.contains(&signature.scheme) {
            return Err(Error::PeerMisbehaved(rustls::PeerMisbehaved::SignedHandshakeWithUnadvertisedSigScheme));
        }
        verify_tls13_signature(message, cert, signature, &self.supported)
    }

    fn supported_verify_schemes(&self) -> Vec<SignatureScheme> { self.allowed_schemes.clone() }
}
