use std::ptr;

use cpython_binding::arguments::{exactly, long_long_argument, ssize_argument};
use cpython_binding::ffi::{
    Py_ssize_t, PyBytes_Type, PyDict_Contains, PyMethodDef, PyObject, PyTuple_GetItem,
    PyTuple_New, PyTuple_SetItem, PyTuple_Size, PyUnicode_Concat,
};
use cpython_binding::values::boolean;
use cpython_binding::{
    Borrowed, Buffer, BytesWriter, Exception, Module, Outcome, Owned, Stop, fastcall,
    fastcall_arguments, into_return, method_table_end, raise,
};
use cpython_deflate::{
    ExactBytesSink, InflateFlush, Inflater, RAW_WINDOW, Z_MEM_ERROR, Z_STREAM_END, out_of_memory,
};

fn contains(files: Borrowed<'_>, key: &Owned) -> Outcome<bool> {
    match unsafe { PyDict_Contains(files.as_ptr(), key.as_ptr()) } {
        found if found < 0 => Err(Stop::Raised),
        found => Ok(found != 0),
    }
}

fn concatenated(left: Borrowed<'_>, right: *mut PyObject) -> Outcome<Owned> {
    unsafe { Owned::from_new_reference(PyUnicode_Concat(left.as_ptr(), right)) }
}

fn module_matches_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [files, path, search_order] =
        *exactly::<3>(arguments, c"module_matches() takes exactly three arguments")?;
    let count = unsafe { PyTuple_Size(search_order.as_ptr()) };
    if count < 0 {
        return Err(Stop::Raised);
    }
    let result = unsafe { Owned::from_new_reference(PyTuple_New(count)) }?;
    for index in 0..count {
        let entry = unsafe { PyTuple_GetItem(search_order.as_ptr(), index) };
        if entry.is_null() {
            return Err(Stop::Raised);
        }
        let suffix = unsafe { PyTuple_GetItem(entry, 0) };
        if suffix.is_null() {
            return Err(Stop::Raised);
        }
        let candidate = concatenated(path, suffix)?;
        let matched = boolean(contains(files, &candidate)?);
        if unsafe { PyTuple_SetItem(result.as_ptr(), index, matched.into_raw()) } != 0 {
            return Err(Stop::Raised);
        }
    }
    Ok(result)
}

fn is_directory_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [files, path, separator] =
        *exactly::<3>(arguments, c"is_directory() takes exactly three arguments")?;
    let candidate = concatenated(path, separator.as_ptr())?;
    Ok(boolean(contains(files, &candidate)?))
}

fn inflate_raw(input: &[u8], capacity: usize) -> Outcome<Owned> {
    let mut stream = match Inflater::new(RAW_WINDOW) {
        Ok(stream) => stream,
        Err(Z_MEM_ERROR) => return Err(out_of_memory()),
        Err(_) => return Err(Stop::Unsupported),
    };
    let mut output = ExactBytesSink::with_capacity(capacity)?;
    let result = stream.run(input, InflateFlush::FinishLast, None, &mut output)?;
    if result.code != Z_STREAM_END {
        return Err(Stop::Unsupported);
    }
    stream.end();
    output.finish()
}

fn decompress_zip_data_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    if !(2..=3).contains(&arguments.len()) {
        return Err(raise(
            Exception::TypeError,
            c"decompress_zip_data() takes two or three arguments",
        ));
    }
    let compression = long_long_argument(arguments[0])?;
    if compression != 0 && compression != 8 {
        return Err(Stop::Unsupported);
    }
    let hint = match arguments.get(2) {
        Some(hint) => ssize_argument(*hint)?.max(0) as usize,
        None => 0,
    };
    let raw = arguments[1];
    if compression == 0 {
        if unsafe { (*raw.as_ptr()).ob_type } == ptr::addr_of_mut!(PyBytes_Type) {
            return Ok(raw.to_owned());
        }
        return BytesWriter::copy_of(Buffer::acquire(raw)?.as_bytes());
    }
    let input = Buffer::acquire(raw)?;
    let input = input.as_bytes();
    let ceiling = input.len().saturating_mul(1032).saturating_add(64);
    let hint = if hint == 0 { input.len().saturating_mul(4) } else { hint };
    inflate_raw(input, hint.clamp(1, ceiling))
}

macro_rules! entry_point {
    ($name:ident, $call:ident) => {
        unsafe extern "C" fn $name(
            _module: *mut PyObject,
            args: *mut *mut PyObject,
            nargs: Py_ssize_t,
        ) -> *mut PyObject {
            into_return($call(unsafe { fastcall_arguments(args, nargs) }))
        }
    };
}

entry_point!(module_matches, module_matches_call);
entry_point!(is_directory, is_directory_call);
entry_point!(decompress_zip_data, decompress_zip_data_call);

static METHODS: [PyMethodDef; 4] = [
    fastcall(
        c"module_matches",
        module_matches,
        c"Match ZIP import candidates against an archive directory.",
    ),
    fastcall(
        c"decompress_zip_data",
        decompress_zip_data,
        c"Extract stored or DEFLATE-compressed ZIP module data.",
    ),
    fastcall(
        c"is_directory",
        is_directory,
        c"Check whether an archive contains a directory path.",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_zipimport_rs",
    c"Rust ZIP import discovery and payload extraction.",
    &METHODS,
);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__zipimport_rs() -> *mut PyObject {
    MODULE.init()
}
