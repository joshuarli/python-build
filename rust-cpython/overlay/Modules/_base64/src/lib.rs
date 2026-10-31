use std::slice;

use base64::engine::DecodePaddingMode;
use base64::engine::general_purpose::{
    GeneralPurpose, GeneralPurposeConfig, STANDARD, STANDARD_NO_PAD, URL_SAFE, URL_SAFE_NO_PAD,
};
use base64::{DecodeSliceError, Engine, alphabet};
use cpython_binding::ffi::{PyErr_NoMemory, PyMethodDef, PyObject, PyObject_IsTrue, Py_ssize_t};
use cpython_binding::{
    Borrowed, Buffer, BytesWriter, Exception, Module, Outcome, Owned, Stop, fastcall,
    fastcall_arguments, into_return, method_table_end, raise,
};
use data_encoding::{BASE32, BASE32HEX, BASE32HEX_NOPAD, BASE32_NOPAD, Encoding, HEXUPPER};

const STANDARD_COMPAT: GeneralPurpose = GeneralPurpose::new(
    &alphabet::STANDARD,
    GeneralPurposeConfig::new().with_decode_allow_trailing_bits(true),
);
const STANDARD_NO_PAD_COMPAT: GeneralPurpose = GeneralPurpose::new(
    &alphabet::STANDARD,
    GeneralPurposeConfig::new()
        .with_decode_allow_trailing_bits(true)
        .with_decode_padding_mode(DecodePaddingMode::RequireNone),
);
static HEXUPPER_ENCODING: Encoding = HEXUPPER;
static BASE32_ENCODING: Encoding = BASE32;
static BASE32_NOPAD_ENCODING: Encoding = BASE32_NOPAD;
static BASE32HEX_ENCODING: Encoding = BASE32HEX;
static BASE32HEX_NOPAD_ENCODING: Encoding = BASE32HEX_NOPAD;

#[inline]
fn encoded_output_len(input_len: usize, padded: bool) -> Option<usize> {
    let full_groups = (input_len / 3).checked_mul(4)?;
    match (input_len % 3, padded) {
        (0, _) => Some(full_groups),
        (_, true) => full_groups.checked_add(4),
        (remainder, false) => full_groups.checked_add(remainder + 1),
    }
}

fn out_of_memory() -> Stop {
    unsafe { PyErr_NoMemory() };
    Stop::Raised
}

fn flag(object: Borrowed<'_>) -> Outcome<bool> {
    match unsafe { PyObject_IsTrue(object.as_ptr()) } {
        result if result < 0 => Err(Stop::Raised),
        result => Ok(result != 0),
    }
}

fn output_slice(writer: &mut BytesWriter) -> &mut [u8] {
    let length = writer.len();
    unsafe { slice::from_raw_parts_mut(writer.uninit().as_mut_ptr().cast::<u8>(), length) }
}

fn encode_with<E: Engine>(source: Borrowed<'_>, engine: &E, padded: bool) -> Outcome<Owned> {
    let buffer = Buffer::acquire(source)?;
    let input = buffer.as_bytes();
    let output_len = encoded_output_len(input.len(), padded).ok_or_else(out_of_memory)?;
    let mut writer = BytesWriter::create(output_len)?;
    match engine.encode_slice(input, output_slice(&mut writer)) {
        Ok(written) if written == output_len => unsafe { writer.finish(output_len) },
        _ => Err(out_of_memory()),
    }
}

fn encode_data_encoding(source: Borrowed<'_>, encoding: &'static Encoding) -> Outcome<Owned> {
    let buffer = Buffer::acquire(source)?;
    let input = buffer.as_bytes();
    let output_len = encoding.encode_len(input.len());
    let mut writer = BytesWriter::create(output_len)?;
    encoding.encode_mut(input, output_slice(&mut writer));
    unsafe { writer.finish(output_len) }
}

fn decode_data_encoding(source: Borrowed<'_>, encoding: &'static Encoding) -> Outcome<Owned> {
    let buffer = Buffer::acquire(source)?;
    let input = buffer.as_bytes();
    let capacity = encoding
        .decode_len(input.len())
        .map_err(|_| Stop::Unsupported)?;
    let mut writer = BytesWriter::create(capacity)?;
    match encoding.decode_mut(input, output_slice(&mut writer)) {
        Ok(written) => unsafe { writer.finish(written) },
        Err(_) => Err(Stop::Unsupported),
    }
}

fn encode_base85(input: &[u8], padded: bool, alphabet: &[u8; 85]) -> Vec<u8> {
    let complete_len = input.len() / 4 * 5;
    let remainder = input.len() % 4;
    let output_len = complete_len + if remainder == 0 { 0 } else if padded { 5 } else { remainder + 1 };
    let mut output = Vec::with_capacity(output_len);
    for chunk in input.chunks(4) {
        let mut bytes = [0u8; 4];
        bytes[..chunk.len()].copy_from_slice(chunk);
        let mut value = u32::from_be_bytes(bytes);
        let mut encoded = [0u8; 5];
        for slot in encoded.iter_mut().rev() {
            *slot = alphabet[(value % 85) as usize];
            value /= 85;
        }
        let count = if chunk.len() == 4 || padded { 5 } else { chunk.len() + 1 };
        output.extend_from_slice(&encoded[..count]);
    }
    output
}

const B85_ALPHABET: &[u8; 85] = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~";
const Z85_ALPHABET: &[u8; 85] = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#";

fn decode_base85(input: &[u8], alphabet: &[u8; 85]) -> Option<Vec<u8>> {
    let mut output = Vec::with_capacity(input.len() / 5 * 4 + input.len() % 5);
    let mut chunks = input.chunks_exact(5);
    for chunk in &mut chunks {
        let value = chunk.iter().try_fold(0u64, |value, byte| {
            let digit = alphabet.iter().position(|candidate| candidate == byte)? as u64;
            value.checked_mul(85)?.checked_add(digit)
        })?;
        if value > u32::MAX as u64 {
            return None;
        }
        output.extend_from_slice(&(value as u32).to_be_bytes());
    }
    let remainder = chunks.remainder();
    if remainder.len() == 1 {
        return None;
    }
    if !remainder.is_empty() {
        let mut value = 0u64;
        for &byte in remainder {
            let digit = alphabet.iter().position(|candidate| *candidate == byte)? as u64;
            value = value.checked_mul(85)?.checked_add(digit)?;
        }
        for _ in remainder.len()..5 {
            value = value.checked_mul(85)?.checked_add(84)?;
        }
        if value > u32::MAX as u64 {
            return None;
        }
        output.extend_from_slice(&(value as u32).to_be_bytes()[..remainder.len() - 1]);
    }
    Some(output)
}

fn encode_ascii85(input: &[u8]) -> Vec<u8> {
    let mut output = Vec::with_capacity(input.len() / 4 * 5 + input.len() % 4 + usize::from(input.len() % 4 != 0));
    for chunk in input.chunks(4) {
        if chunk == [0, 0, 0, 0] {
            output.push(b'z');
            continue;
        }
        let mut bytes = [0u8; 4];
        bytes[..chunk.len()].copy_from_slice(chunk);
        let mut value = u32::from_be_bytes(bytes);
        let mut encoded = [0u8; 5];
        for slot in encoded.iter_mut().rev() {
            *slot = b'!' + (value % 85) as u8;
            value /= 85;
        }
        let count = if chunk.len() == 4 { 5 } else { chunk.len() + 1 };
        output.extend_from_slice(&encoded[..count]);
    }
    output
}

fn decode_ascii85(input: &[u8]) -> Option<Vec<u8>> {
    let mut output = Vec::with_capacity(input.len() * 4 / 5);
    let mut group = [84u8; 5];
    let mut count = 0usize;
    for &byte in input {
        if matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b) {
            continue;
        }
        if byte == b'z' {
            if count != 0 {
                return None;
            }
            output.extend_from_slice(&[0, 0, 0, 0]);
            continue;
        }
        if !(b'!'..=b'u').contains(&byte) {
            return None;
        }
        group[count] = byte - b'!';
        count += 1;
        if count == 5 {
            let value = group.iter().fold(0u64, |value, digit| value * 85 + u64::from(*digit));
            if value > u32::MAX as u64 {
                return None;
            }
            output.extend_from_slice(&(value as u32).to_be_bytes());
            group = [84; 5];
            count = 0;
        }
    }
    if count == 1 {
        return None;
    }
    if count > 1 {
        let value = group.iter().fold(0u64, |value, digit| value * 85 + u64::from(*digit));
        if value > u32::MAX as u64 {
            return None;
        }
        output.extend_from_slice(&(value as u32).to_be_bytes()[..count - 1]);
    }
    Some(output)
}

fn argument_count_error(message: &'static std::ffi::CStr) -> Stop {
    raise(Exception::TypeError, message)
}

fn base32_encoding(hex: bool, padded: bool) -> &'static Encoding {
    match (hex, padded) {
        (false, true) => &BASE32_ENCODING,
        (false, false) => &BASE32_NOPAD_ENCODING,
        (true, true) => &BASE32HEX_ENCODING,
        (true, false) => &BASE32HEX_NOPAD_ENCODING,
    }
}

fn base32_encode(arguments: &[Borrowed<'_>], hex: bool) -> Outcome<Owned> {
    let [data, padded] = arguments else {
        return Err(argument_count_error(c"Base32 encode requires data and padded"));
    };
    let padded = flag(*padded)?;
    encode_data_encoding(*data, base32_encoding(hex, padded))
}

fn base32_decode(arguments: &[Borrowed<'_>], hex: bool) -> Outcome<Owned> {
    let [data, padded] = arguments else {
        return Err(argument_count_error(c"Base32 decode requires data and padded"));
    };
    let padded = flag(*padded)?;
    decode_data_encoding(*data, base32_encoding(hex, padded))
}

fn base16_encode(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [data] = arguments else {
        return Err(argument_count_error(c"b16encode() takes exactly one argument"));
    };
    encode_data_encoding(*data, &HEXUPPER_ENCODING)
}

fn base16_decode(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [data] = arguments else {
        return Err(argument_count_error(c"b16decode() takes exactly one argument"));
    };
    decode_data_encoding(*data, &HEXUPPER_ENCODING)
}

fn base85_encode(arguments: &[Borrowed<'_>], alphabet: &'static [u8; 85]) -> Outcome<Owned> {
    let [data, padded] = arguments else {
        return Err(argument_count_error(c"Base85 encode requires data and pad"));
    };
    let padded = flag(*padded)?;
    let buffer = Buffer::acquire(*data)?;
    BytesWriter::copy_of(&encode_base85(buffer.as_bytes(), padded, alphabet))
}

fn base85_decode(arguments: &[Borrowed<'_>], alphabet: &'static [u8; 85]) -> Outcome<Owned> {
    let [data] = arguments else {
        return Err(argument_count_error(c"Base85 decode requires one argument"));
    };
    let buffer = Buffer::acquire(*data)?;
    let output = decode_base85(buffer.as_bytes(), alphabet).ok_or(Stop::Unsupported)?;
    BytesWriter::copy_of(&output)
}

fn ascii85_encode(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [data] = arguments else {
        return Err(argument_count_error(c"a85encode() takes exactly one argument"));
    };
    let buffer = Buffer::acquire(*data)?;
    BytesWriter::copy_of(&encode_ascii85(buffer.as_bytes()))
}

fn ascii85_decode(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [data] = arguments else {
        return Err(argument_count_error(c"a85decode() takes exactly one argument"));
    };
    let buffer = Buffer::acquire(*data)?;
    let output = decode_ascii85(buffer.as_bytes()).ok_or(Stop::Unsupported)?;
    BytesWriter::copy_of(&output)
}

fn padded_encode<E: Engine>(
    arguments: &[Borrowed<'_>],
    padded_engine: &E,
    unpadded_engine: &E,
    message: &'static std::ffi::CStr,
) -> Outcome<Owned> {
    let (source, padded) = match arguments {
        [source] => (*source, true),
        [source, padded] => (*source, flag(*padded)?),
        _ => return Err(argument_count_error(message)),
    };
    let engine = if padded { padded_engine } else { unpadded_engine };
    encode_with(source, engine, padded)
}

fn base64_decode(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [source, validate, padded] = arguments else {
        return Err(argument_count_error(c"b64decode() takes exactly three arguments"));
    };
    let validate = flag(*validate)?;
    let padded = flag(*padded)?;
    let buffer = Buffer::acquire(*source)?;
    let input = buffer.as_bytes();

    // Discarded characters are rare: decode straight from the caller's
    // buffer when every byte is part of the alphabet, and only build a
    // cleaned copy when something has to be dropped.
    let is_clean = |byte: u8| {
        byte.is_ascii_alphanumeric() || matches!(byte, b'+' | b'/') || (padded && byte == b'=')
    };
    let cleaned;
    let input = if input.iter().all(|&byte| is_clean(byte)) {
        input
    } else if validate {
        return Err(Stop::Unsupported);
    } else {
        cleaned = input.iter().copied().filter(|&byte| is_clean(byte)).collect::<Vec<u8>>();
        &cleaned[..]
    };

    let engine = if padded {
        &STANDARD_COMPAT
    } else {
        &STANDARD_NO_PAD_COMPAT
    };
    let estimate = (input.len() / 4 + usize::from(input.len() % 4 != 0)).saturating_mul(3);
    let exact = match input.len() % 4 {
        0 if padded => {
            let padding = input
                .iter()
                .rev()
                .take(2)
                .take_while(|&&byte| byte == b'=')
                .count();
            estimate - padding.min(estimate)
        }
        2 if !padded => estimate - 2,
        3 if !padded => estimate - 1,
        _ => estimate,
    };
    for capacity in [exact, estimate] {
        let mut writer = BytesWriter::create(capacity)?;
        match engine.decode_slice(input, output_slice(&mut writer)) {
            Ok(written) => return unsafe { writer.finish(written) },
            Err(DecodeSliceError::OutputSliceTooSmall) if capacity != estimate => {}
            Err(_) => return Err(Stop::Unsupported),
        }
    }
    Err(Stop::Unsupported)
}

macro_rules! entry_point {
    ($name:ident, |$arguments:ident| $body:expr) => {
        pub unsafe extern "C" fn $name(
            _module: *mut PyObject,
            args: *mut *mut PyObject,
            nargs: Py_ssize_t,
        ) -> *mut PyObject {
            let $arguments = unsafe { fastcall_arguments(args, nargs) };
            into_return($body)
        }
    };
}

entry_point!(standard_b64encode, |arguments| padded_encode(
    arguments,
    &STANDARD,
    &STANDARD_NO_PAD,
    c"standard_b64encode() takes one or two arguments"
));
entry_point!(urlsafe_b64encode, |arguments| padded_encode(
    arguments,
    &URL_SAFE,
    &URL_SAFE_NO_PAD,
    c"urlsafe_b64encode() takes one or two arguments"
));
entry_point!(b64decode, |arguments| base64_decode(arguments));
entry_point!(b16encode, |arguments| base16_encode(arguments));
entry_point!(b16decode, |arguments| base16_decode(arguments));
entry_point!(b32encode, |arguments| base32_encode(arguments, false));
entry_point!(b32decode, |arguments| base32_decode(arguments, false));
entry_point!(b32hexencode, |arguments| base32_encode(arguments, true));
entry_point!(b32hexdecode, |arguments| base32_decode(arguments, true));
entry_point!(b85encode, |arguments| base85_encode(arguments, B85_ALPHABET));
entry_point!(b85decode, |arguments| base85_decode(arguments, B85_ALPHABET));
entry_point!(z85encode, |arguments| base85_encode(arguments, Z85_ALPHABET));
entry_point!(z85decode, |arguments| base85_decode(arguments, Z85_ALPHABET));
entry_point!(a85encode, |arguments| ascii85_encode(arguments));
entry_point!(a85decode, |arguments| ascii85_decode(arguments));

static METHODS: [PyMethodDef; 16] = [
    fastcall(c"standard_b64encode", standard_b64encode, c"Encode with the standard Base64 alphabet"),
    fastcall(c"urlsafe_b64encode", urlsafe_b64encode, c"Encode with the URL-safe Base64 alphabet"),
    fastcall(c"b64decode", b64decode, c"Decode Base64 data for the public base64 module"),
    fastcall(c"b16encode", b16encode, c"Encode with the Base16 alphabet"),
    fastcall(c"b16decode", b16decode, c"Decode Base16 data for the public base64 module"),
    fastcall(c"b32encode", b32encode, c"Encode with the Base32 alphabet"),
    fastcall(c"b32decode", b32decode, c"Decode Base32 data for the public base64 module"),
    fastcall(c"b32hexencode", b32hexencode, c"Encode with the Base32hex alphabet"),
    fastcall(c"b32hexdecode", b32hexdecode, c"Decode Base32hex data for the public base64 module"),
    fastcall(c"b85encode", b85encode, c"Encode with the Base85 alphabet"),
    fastcall(c"b85decode", b85decode, c"Decode Base85 data for the public base64 module"),
    fastcall(c"z85encode", z85encode, c"Encode with the Z85 alphabet"),
    fastcall(c"z85decode", z85decode, c"Decode Z85 data for the public base64 module"),
    fastcall(c"a85encode", a85encode, c"Encode with the Ascii85 alphabet"),
    fastcall(c"a85decode", a85decode, c"Decode Ascii85 data for the public base64 module"),
    method_table_end(),
];

static MODULE: Module = Module::new(c"_base64", c"Rust encoding engines used by base64", &METHODS);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__base64() -> *mut PyObject {
    MODULE.init()
}
