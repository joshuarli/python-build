use cpython_binding::ffi::{PyMethodDef, PyObject, Py_ssize_t};
use cpython_binding::{
    Borrowed, Buffer, BytesWriter, Exception, Module, Outcome, Owned, fastcall,
    fastcall_arguments, into_return, method_table_end, raise,
};
use uuid::Uuid;

fn read_uuid(object: Borrowed<'_>) -> Outcome<Uuid> {
    let buffer = Buffer::acquire(object)?;
    Uuid::from_slice(buffer.as_bytes())
        .map_err(|_| raise(Exception::ValueError, c"UUID data must contain exactly 16 bytes"))
}

fn parse_hex_text(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [object] = arguments else {
        return Err(raise(Exception::TypeError, c"parse_hex() takes exactly one argument"));
    };
    let invalid = || raise(Exception::ValueError, c"invalid UUID hexadecimal data");
    let buffer = Buffer::acquire(*object)?;
    let text = core::str::from_utf8(buffer.as_bytes()).map_err(|_| invalid())?;
    let value = Uuid::parse_str(text).map_err(|_| invalid())?;
    BytesWriter::copy_of(value.as_bytes())
}

fn normalize_uuid(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [object] = arguments else {
        return Err(raise(Exception::TypeError, c"normalize() takes exactly one argument"));
    };
    BytesWriter::copy_of(read_uuid(*object)?.as_bytes())
}

fn with_version(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [uuid, version] = arguments else {
        return Err(raise(Exception::TypeError, c"set_version() takes exactly two arguments"));
    };
    let version = {
        let buffer = Buffer::acquire(*version)?;
        match buffer.as_bytes() {
            [version @ 1..=8] => *version,
            _ => return Err(raise(Exception::ValueError, c"illegal UUID version number")),
        }
    };
    let mut value = *read_uuid(*uuid)?.as_bytes();
    value[6] = (value[6] & 0x0f) | (version << 4);
    value[8] = (value[8] & 0x3f) | 0x80;
    BytesWriter::copy_of(&value)
}

fn name_uuid(arguments: &[Borrowed<'_>], version: u8) -> Outcome<Owned> {
    let [object] = arguments else {
        return Err(raise(
            Exception::TypeError,
            c"name UUID generator takes exactly one argument",
        ));
    };
    let buffer = Buffer::acquire(*object)?;
    let data = buffer.as_bytes();
    let invalid = || raise(Exception::ValueError, c"namespace UUID data must contain 16 bytes");
    let (namespace, name) = data.split_first_chunk::<16>().ok_or_else(invalid)?;
    let namespace = Uuid::from_bytes(*namespace);
    let value = match version {
        3 => Uuid::new_v3(&namespace, name),
        _ => Uuid::new_v5(&namespace, name),
    };
    BytesWriter::copy_of(value.as_bytes())
}

fn formatted(arguments: &[Borrowed<'_>], simple: bool) -> Outcome<Owned> {
    let [object] = arguments else {
        return Err(raise(Exception::TypeError, c"format() takes exactly one argument"));
    };
    let value = read_uuid(*object)?;
    let text = if simple {
        value.simple().to_string()
    } else {
        value.hyphenated().to_string()
    };
    BytesWriter::copy_of(text.as_bytes())
}

macro_rules! entry_point {
    ($name:ident, |$arguments:ident| $body:expr) => {
        unsafe extern "C" fn $name(
            _module: *mut PyObject,
            args: *mut *mut PyObject,
            nargs: Py_ssize_t,
        ) -> *mut PyObject {
            let $arguments = unsafe { fastcall_arguments(args, nargs) };
            into_return($body)
        }
    };
}

entry_point!(parse_hex, |arguments| parse_hex_text(arguments));
entry_point!(normalize, |arguments| normalize_uuid(arguments));
entry_point!(set_version, |arguments| with_version(arguments));
entry_point!(uuid3, |arguments| name_uuid(arguments, 3));
entry_point!(uuid5, |arguments| name_uuid(arguments, 5));
entry_point!(format, |arguments| formatted(arguments, false));
entry_point!(format_hex, |arguments| formatted(arguments, true));

unsafe extern "C" fn uuid4(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let _ = args;
    into_return(if nargs != 0 {
        Err(raise(Exception::TypeError, c"uuid4() takes no arguments"))
    } else {
        BytesWriter::copy_of(Uuid::new_v4().as_bytes())
    })
}

static METHODS: [PyMethodDef; 9] = [
    fastcall(c"parse_hex", parse_hex, c"Parse 32 hexadecimal UUID digits"),
    fastcall(c"normalize", normalize, c"Validate and normalize a 16-byte UUID"),
    fastcall(c"set_version", set_version, c"Set the UUID variant and version bits"),
    fastcall(c"uuid3", uuid3, c"Generate a version 3 name UUID"),
    fastcall(c"uuid4", uuid4, c"Generate a random version 4 UUID"),
    fastcall(c"uuid5", uuid5, c"Generate a version 5 name UUID"),
    fastcall(
        c"format",
        format,
        c"Format a UUID using canonical hyphenated lowercase text",
    ),
    fastcall(c"format_hex", format_hex, c"Format a UUID as lowercase hexadecimal text"),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_uuid_rs",
    c"Rust UUID parsing, formatting, and generation",
    &METHODS,
);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__uuid_rs() -> *mut PyObject {
    MODULE.init()
}
