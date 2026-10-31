#![no_std]

use core::net::{Ipv4Addr, Ipv6Addr};
use core::slice;
use core::str;

use cpython_binding::ffi::{
    PyErr_Occurred, PyLong_AsLong, PyMethodDef, PyObject, PyUnicode_AsUTF8AndSize, Py_ssize_t,
};
use cpython_binding::{
    Borrowed, Buffer, BytesWriter, Exception, Module, Outcome, Owned, Stop, fastcall,
    fastcall_arguments, into_return, method_table_end, raise,
};

fn parse_address(arguments: &[Borrowed<'_>], ipv6: bool) -> Outcome<Owned> {
    let [argument] = arguments else {
        return Err(raise(
            Exception::TypeError,
            if ipv6 {
                c"parse_ipv6() takes exactly one argument"
            } else {
                c"parse_ipv4() takes exactly one argument"
            },
        ));
    };
    let mut size = 0;
    let text = unsafe { PyUnicode_AsUTF8AndSize(argument.as_ptr(), &mut size) };
    if text.is_null() {
        return Err(Stop::Raised);
    }
    if size < 0 {
        return Err(raise(Exception::ValueError, c"address length cannot be negative"));
    }
    let bytes = unsafe { slice::from_raw_parts(text.cast::<u8>(), size as usize) };
    let text = unsafe { str::from_utf8_unchecked(bytes) };

    if ipv6 {
        match text.parse::<Ipv6Addr>() {
            Ok(address) => BytesWriter::copy_of(&address.octets()),
            Err(_) => Err(raise(Exception::ValueError, c"invalid IPv6 address")),
        }
    } else {
        match text.parse::<Ipv4Addr>() {
            Ok(address) => BytesWriter::copy_of(&address.octets()),
            Err(_) => Err(raise(Exception::ValueError, c"invalid IPv4 address")),
        }
    }
}

/// Parse standard IPv4 text and return its four network-order octets.
/// Invalid input raises ValueError so the Python boundary can retain its
/// detailed CPython-compatible validation message.
unsafe extern "C" fn parse_ipv4(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    into_return(parse_address(unsafe { fastcall_arguments(args, nargs) }, false))
}

/// Parse standard IPv6 text and return its sixteen network-order octets.
/// Invalid input raises ValueError so the Python boundary can retain its
/// detailed CPython-compatible validation message.
unsafe extern "C" fn parse_ipv6(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    into_return(parse_address(unsafe { fastcall_arguments(args, nargs) }, true))
}

fn bounds(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [address_object, prefix_object] = arguments else {
        return Err(raise(
            Exception::TypeError,
            c"network_bounds() takes exactly two arguments",
        ));
    };
    let buffer = Buffer::acquire(*address_object)?;
    let address = buffer.as_bytes();
    let width = address.len();
    let bits = match width {
        4 => 32,
        16 => 128,
        _ => {
            return Err(raise(
                Exception::ValueError,
                c"packed address must contain 4 or 16 bytes",
            ));
        }
    };

    let prefix = unsafe { PyLong_AsLong(prefix_object.as_ptr()) };
    if unsafe { !PyErr_Occurred().is_null() } {
        return Err(Stop::Raised);
    }
    if prefix < 0 || prefix > bits {
        return Err(raise(
            Exception::ValueError,
            c"prefix length is outside the address width",
        ));
    }
    let value = if width == 4 {
        u32::from_be_bytes(address.try_into().unwrap()) as u128
    } else {
        u128::from_be_bytes(address.try_into().unwrap())
    };
    let all_bits = if bits == 32 {
        u32::MAX as u128
    } else {
        u128::MAX
    };
    let mask = if prefix == 0 {
        0
    } else {
        all_bits << (bits - prefix)
    };
    let network = value & mask;
    let broadcast = network | (all_bits ^ mask);

    let mut result = [0_u8; 32];
    if width == 4 {
        result[..4].copy_from_slice(&(network as u32).to_be_bytes());
        result[4..8].copy_from_slice(&(broadcast as u32).to_be_bytes());
    } else {
        result[..16].copy_from_slice(&network.to_be_bytes());
        result[16..].copy_from_slice(&broadcast.to_be_bytes());
    }
    BytesWriter::copy_of(&result[..width * 2])
}

/// Return the network and broadcast addresses as concatenated network-order
/// octets. The width is inferred from the packed IPv4 or IPv6 input.
unsafe extern "C" fn network_bounds(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    into_return(bounds(unsafe { fastcall_arguments(args, nargs) }))
}

static METHODS: [PyMethodDef; 4] = [
    fastcall(c"parse_ipv4", parse_ipv4, c"Parse an IPv4 address string"),
    fastcall(c"parse_ipv6", parse_ipv6, c"Parse an IPv6 address string"),
    fastcall(
        c"network_bounds",
        network_bounds,
        c"Calculate an address network range",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_ipaddress_rs",
    c"Rust address parsing and network range calculations",
    &METHODS,
);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__ipaddress_rs() -> *mut PyObject {
    MODULE.init()
}
