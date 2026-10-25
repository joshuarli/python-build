use sha1::{Digest, Sha1};
use x509_parser::prelude::*;

fn canonical_subject_name(der_bytes: &[u8]) -> Result<Vec<u8>, String> {
    canonical_subject_name_from_der(der_bytes)
}

pub(crate) fn canonical_subject_name_from_der(der_bytes: &[u8]) -> Result<Vec<u8>, String> {
    let (remaining, certificate) = X509Certificate::from_der(der_bytes)
        .map_err(|error| format!("Failed to parse certificate: {error}"))?;
    if !remaining.is_empty() {
        return Err("Unexpected data after certificate".to_string());
    }
    canonical_name(certificate.subject().as_raw())
}

pub(crate) fn subject_name_hash(canonical_name_der: &[u8]) -> u32 {
    let digest = Sha1::digest(canonical_name_der);
    u32::from_le_bytes([digest[0], digest[1], digest[2], digest[3]])
}

pub(crate) fn canonical_issuer_name_from_der(der_bytes: &[u8]) -> Result<Vec<u8>, String> {
    let (remaining, certificate) = X509Certificate::from_der(der_bytes)
        .map_err(|error| format!("Failed to parse certificate: {error}"))?;
    if !remaining.is_empty() {
        return Err("Unexpected data after certificate".to_string());
    }
    canonical_name(certificate.issuer().as_raw())
}

pub(crate) fn names_equal(left: &[u8], right: &[u8]) -> bool {
    match (canonical_name(left), canonical_name(right)) {
        (Ok(left), Ok(right)) => left == right,
        _ => false,
    }
}

pub(crate) fn name_contents_equal(left: &[u8], right: &[u8]) -> bool {
    let mut left_der = Vec::new();
    let mut right_der = Vec::new();
    encode_tlv(0x30, left, &mut left_der);
    encode_tlv(0x30, right, &mut right_der);
    names_equal(&left_der, &right_der)
}

fn canonical_name(name_der: &[u8]) -> Result<Vec<u8>, String> {
    let (tag, name_content, remaining, _) = read_tlv(name_der)?;
    if tag != 0x30 || !remaining.is_empty() {
        return Err("Invalid X.509 subject name".to_string());
    }

    let mut canonical = Vec::new();
    let mut rdns = name_content;
    while !rdns.is_empty() {
        let (tag, rdn_content, remaining, _) = read_tlv(rdns)?;
        if tag != 0x31 {
            return Err("Invalid X.509 relative distinguished name".to_string());
        }
        rdns = remaining;

        let mut attributes = Vec::new();
        let mut entries = rdn_content;
        while !entries.is_empty() {
            let (tag, entry_content, remaining, _) = read_tlv(entries)?;
            if tag != 0x30 {
                return Err("Invalid X.509 name attribute".to_string());
            }
            entries = remaining;

            let (oid_tag, _, after_oid, oid_der) = read_tlv(entry_content)?;
            if oid_tag != 0x06 {
                return Err("Invalid X.509 name attribute OID".to_string());
            }
            let (value_tag, value, trailing, value_der) = read_tlv(after_oid)?;
            if !trailing.is_empty() {
                return Err("Unexpected data in X.509 name attribute".to_string());
            }

            let canonical_value = canonical_attribute_value(value_tag, value, value_der)?;
            let mut attribute_content = oid_der.to_vec();
            attribute_content.extend_from_slice(&canonical_value);
            let mut attribute = Vec::new();
            encode_tlv(0x30, &attribute_content, &mut attribute);
            attributes.push(attribute);
        }

        attributes.sort();
        let mut canonical_rdn = Vec::new();
        for attribute in attributes {
            canonical_rdn.extend_from_slice(&attribute);
        }
        encode_tlv(0x31, &canonical_rdn, &mut canonical);
    }

    Ok(canonical)
}

fn canonical_attribute_value(tag: u8, value: &[u8], original_der: &[u8]) -> Result<Vec<u8>, String> {
    let text = match tag {
        0x0c => Some(
            std::str::from_utf8(value)
                .map_err(|_| "Invalid UTF8String in X.509 subject name".to_string())?
                .to_string(),
        ),
        0x13 | 0x14 | 0x16 | 0x1a => Some(value.iter().map(|byte| char::from(*byte)).collect()),
        0x1c => {
            if value.len() % 4 != 0 {
                return Err("Invalid UniversalString in X.509 subject name".to_string());
            }
            let mut text = String::new();
            for scalar in value.chunks_exact(4) {
                let value = u32::from_be_bytes([scalar[0], scalar[1], scalar[2], scalar[3]]);
                text.push(
                    char::from_u32(value)
                        .ok_or_else(|| "Invalid UniversalString in X.509 subject name".to_string())?,
                );
            }
            Some(text)
        }
        0x1e => {
            if value.len() % 2 != 0 {
                return Err("Invalid BMPString in X.509 subject name".to_string());
            }
            let mut text = String::new();
            for scalar in value.chunks_exact(2) {
                let value = u16::from_be_bytes([scalar[0], scalar[1]]);
                text.push(
                    char::from_u32(u32::from(value))
                        .ok_or_else(|| "Invalid BMPString in X.509 subject name".to_string())?,
                );
            }
            Some(text)
        }
        _ => None,
    };

    let Some(text) = text else {
        return Ok(original_der.to_vec());
    };

    let bytes = text.into_bytes();
    let mut index = 0;
    while index < bytes.len() && is_ascii_space(bytes[index]) {
        index += 1;
    }
    let mut end = bytes.len();
    while end > index && is_ascii_space(bytes[end - 1]) {
        end -= 1;
    }
    let mut utf8 = Vec::new();
    while index < end {
        if is_ascii_space(bytes[index]) {
            utf8.push(b' ');
            while index < end && is_ascii_space(bytes[index]) {
                index += 1;
            }
        } else {
            let byte = bytes[index];
            utf8.push(if byte.is_ascii() {
                byte.to_ascii_lowercase()
            } else {
                byte
            });
            index += 1;
        }
    }
    let mut encoded = Vec::new();
    encode_tlv(0x0c, &utf8, &mut encoded);
    Ok(encoded)
}

pub(crate) fn is_ascii_space(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
}

fn read_tlv(data: &[u8]) -> Result<(u8, &[u8], &[u8], &[u8]), String> {
    if data.len() < 2 {
        return Err("Truncated DER value".to_string());
    }
    let tag = data[0];
    let first_length = data[1];
    let (header_length, value_length) = if first_length & 0x80 == 0 {
        (2, usize::from(first_length))
    } else {
        let length_bytes = usize::from(first_length & 0x7f);
        if length_bytes == 0 || length_bytes > std::mem::size_of::<usize>() {
            return Err("Invalid DER length".to_string());
        }
        if data.len() < 2 + length_bytes {
            return Err("Truncated DER length".to_string());
        }
        let mut value_length = 0usize;
        for byte in &data[2..2 + length_bytes] {
            value_length = value_length
                .checked_mul(256)
                .and_then(|length| length.checked_add(usize::from(*byte)))
                .ok_or_else(|| "DER length overflow".to_string())?;
        }
        (2 + length_bytes, value_length)
    };
    let end = header_length
        .checked_add(value_length)
        .filter(|end| *end <= data.len())
        .ok_or_else(|| "Truncated DER value".to_string())?;
    Ok((tag, &data[header_length..end], &data[end..], &data[..end]))
}

fn encode_tlv(tag: u8, value: &[u8], output: &mut Vec<u8>) {
    output.push(tag);
    if value.len() < 128 {
        output.push(value.len() as u8);
    } else {
        let length_bytes = value.len().to_be_bytes();
        let first_nonzero = length_bytes
            .iter()
            .position(|byte| *byte != 0)
            .unwrap_or(length_bytes.len() - 1);
        let length_bytes = &length_bytes[first_nonzero..];
        output.push(0x80 | length_bytes.len() as u8);
        output.extend_from_slice(length_bytes);
    }
    output.extend_from_slice(value);
}
