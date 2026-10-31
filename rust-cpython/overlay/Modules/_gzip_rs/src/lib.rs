use std::ffi::{CStr, c_uint, c_void};
use std::mem;
use std::ptr;
use std::sync::atomic::{AtomicPtr, Ordering};

use cpython_binding::arguments::{c_int_argument, exactly, long_long_argument};
use cpython_binding::ffi::{PyMethodDef, PyObject, Py_ssize_t};
use cpython_binding::values::boolean;
use cpython_binding::{
    BytesSink,
    Borrowed, Buffer, BytesWriter, CapsuleState, Sink, Exception, Module, Outcome, Owned, capsule_state,
    fastcall, fastcall_arguments, into_return, method_table_end, new_capsule, raise,
};
use cpython_deflate::{
    Deflater, InflateFlush, Inflater, RAW_WINDOW, StateAllocator, Z_BUF_ERROR,
    Z_FINISH, Z_NO_FLUSH, Z_OK, Z_STREAM_END, compress_capacity_hint, crc32, crc32_call,
    decompress_capacity_hint, setup_failure, zlib_failure,
};

struct Compressor {
    stream: Deflater,
    finished: bool,
}

impl CapsuleState for Compressor {
    const NAME: &'static CStr = c"_gzip_rs.Compressor";
}

struct Decompressor {
    stream: Inflater,
    eof: bool,
    needs_input: bool,
    hint: usize,
    pending: Vec<u8>,
    unused_data: Vec<u8>,
}

impl CapsuleState for Decompressor {
    const NAME: &'static CStr = c"_gzip_rs.Decompressor";
}

const BLOCK_HEADER: usize = 16;
const CACHE_MIN: usize = 64 * 1024;
static CACHED_BLOCK: AtomicPtr<u8> = AtomicPtr::new(ptr::null_mut());

unsafe extern "C" {
    fn malloc(size: usize) -> *mut c_void;
    fn free(pointer: *mut c_void);
}

unsafe extern "C" fn zalloc_cached(_opaque: *mut c_void, items: c_uint, size: c_uint) -> *mut c_void {
    let total = items as usize * size as usize;
    if total == 0 {
        return ptr::null_mut();
    }
    if total >= CACHE_MIN {
        let block = CACHED_BLOCK.swap(ptr::null_mut(), Ordering::AcqRel);
        if !block.is_null() {
            if unsafe { block.cast::<usize>().read() } == total {
                return unsafe { block.add(BLOCK_HEADER) }.cast();
            }
            unsafe { free(block.cast()) };
        }
    }
    let block = unsafe { malloc(total + BLOCK_HEADER) }.cast::<u8>();
    if block.is_null() {
        return ptr::null_mut();
    }
    unsafe { block.cast::<usize>().write(total) };
    unsafe { block.add(BLOCK_HEADER) }.cast()
}

unsafe extern "C" fn zfree_cached(_opaque: *mut c_void, pointer: *mut c_void) {
    if pointer.is_null() {
        return;
    }
    let block = unsafe { pointer.cast::<u8>().sub(BLOCK_HEADER) };
    if unsafe { block.cast::<usize>().read() } >= CACHE_MIN {
        let old = CACHED_BLOCK.swap(block, Ordering::AcqRel);
        if !old.is_null() {
            unsafe { free(old.cast()) };
        }
    } else {
        unsafe { free(block.cast()) };
    }
}

const CACHED_STATE: StateAllocator = StateAllocator {
    allocate: zalloc_cached,
    release: zfree_cached,
};

fn new_deflater(level: i32) -> Outcome<Deflater> {
    Deflater::new(level, RAW_WINDOW, Some(CACHED_STATE))
        .map_err(|code| setup_failure(code, "while creating compression object"))
}

fn level_argument(object: Borrowed<'_>) -> Outcome<i32> {
    let level = i64::from(c_int_argument(object)?);
    if !(-1..=9).contains(&level) {
        return Err(raise(Exception::ValueError, c"Bad compression level"));
    }
    Ok(level as i32)
}

fn compressor_new_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [level] = *exactly::<1>(arguments, c"compressor() takes exactly one argument")?;
    let level = level_argument(level)?;
    new_capsule(Compressor {
        stream: new_deflater(level)?,
        finished: false,
    })
}

fn compressor_compress_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [state, input] = *exactly::<2>(arguments, c"compress() takes exactly two arguments")?;
    let compressor = unsafe { capsule_state::<Compressor>(state) }?;
    let input = Buffer::acquire(input)?;
    if compressor.finished {
        return Err(raise(
            Exception::ValueError,
            c"compressor could not consume the input",
        ));
    }
    let input = input.as_bytes();
    let mut output = BytesSink::with_capacity(compress_capacity_hint(input.len()))?;
    compressor
        .stream
        .run(input, Z_NO_FLUSH, &mut output)
        .map_err(|error| compressor.stream.failure(error, "while compressing data"))?;
    output.finish()
}

fn compressor_flush_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [state, mode] = *exactly::<2>(arguments, c"flush() takes exactly two arguments")?;
    let compressor = unsafe { capsule_state::<Compressor>(state) }?;
    let mode = long_long_argument(mode)?;
    if !(0..=5).contains(&mode) {
        return Err(raise(Exception::ValueError, c"invalid compressor flush mode"));
    }
    if compressor.finished {
        return Err(raise(
            Exception::ValueError,
            c"compressor has already been flushed",
        ));
    }
    let mode = mode as i32;
    if mode == Z_NO_FLUSH {
        return BytesWriter::copy_of(b"");
    }
    let mut output = BytesSink::with_capacity(1024)?;
    let code = compressor
        .stream
        .run(&[], mode, &mut output)
        .map_err(|error| compressor.stream.failure(error, "while flushing"))?;
    if code == Z_STREAM_END && mode == Z_FINISH {
        compressor.finished = true;
        let code = compressor.stream.end();
        if code != Z_OK {
            return Err(zlib_failure(
                compressor.stream.stream(),
                code,
                "while finishing compression",
            ));
        }
    } else if code != Z_OK && code != Z_BUF_ERROR {
        return Err(zlib_failure(compressor.stream.stream(), code, "while flushing"));
    }
    output.finish()
}

const MEMBER_HEADER: usize = 10;
const MEMBER_TRAILER: usize = 8;

fn compress_member_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [input, level, mtime] =
        *exactly::<3>(arguments, c"compress_member() takes exactly three arguments")?;
    let input = Buffer::acquire(input)?;
    let level = level_argument(level)?;
    let Ok(mtime) = u32::try_from(long_long_argument(mtime)?) else {
        return Err(raise(Exception::ValueError, c"mtime out of range"));
    };
    let input = input.as_bytes();
    let mut compressor = new_deflater(level)?;
    let bound = compressor.bound(input.len());
    let mut output = BytesSink::with_capacity(bound.saturating_add(MEMBER_HEADER + MEMBER_TRAILER))?;
    let extra_flags = match level {
        9 => 2u8,
        1 => 4u8,
        _ => 0u8,
    };
    let mut header = [0x1f, 0x8b, 8, 0, 0, 0, 0, 0, extra_flags, 255];
    header[4..8].copy_from_slice(&mtime.to_le_bytes());
    output.append(&header)?;
    compressor
        .run(input, Z_FINISH, &mut output)
        .map_err(|error| compressor.failure(error, "while compressing data"))?;
    let code = compressor.end();
    if code != Z_OK {
        return Err(zlib_failure(
            compressor.stream(),
            code,
            "while finishing compression",
        ));
    }
    let mut trailer = [0u8; MEMBER_TRAILER];
    trailer[..4].copy_from_slice(&(crc32(0, input) as u32).to_le_bytes());
    trailer[4..].copy_from_slice(&(input.len() as u32).to_le_bytes());
    output.append(&trailer)?;
    output.finish()
}

fn decompressor_new_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    if arguments.len() > 1 {
        return Err(raise(
            Exception::TypeError,
            c"decompressor() takes at most one argument",
        ));
    }
    let hint = match arguments.first() {
        Some(hint) => long_long_argument(*hint)?.max(0) as usize,
        None => 0,
    };
    let stream = Inflater::new(RAW_WINDOW)
        .map_err(|code| setup_failure(code, "while creating decompression object"))?;
    new_capsule(Decompressor {
        stream,
        eof: false,
        needs_input: true,
        hint,
        pending: Vec::new(),
        unused_data: Vec::new(),
    })
}

fn decompressor_decompress_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [state, data, max_length] =
        *exactly::<3>(arguments, c"decompress() takes exactly three arguments")?;
    let decompressor = unsafe { capsule_state::<Decompressor>(state) }?;
    let data = Buffer::acquire(data)?;
    let max_length = long_long_argument(max_length)?;
    if max_length < 0 {
        return Err(raise(
            Exception::ValueError,
            c"max_length must be non-negative",
        ));
    }
    let data = data.as_bytes();
    if decompressor.eof {
        decompressor.unused_data.extend_from_slice(data);
        return BytesWriter::copy_of(b"");
    }
    let mut held = mem::take(&mut decompressor.pending);
    let input: &[u8] = if held.is_empty() {
        data
    } else {
        held.extend_from_slice(data);
        &held
    };
    let limit = (max_length != 0).then_some(max_length as usize);
    let mut capacity = match (limit, mem::take(&mut decompressor.hint)) {
        (None, hint) if hint != 0 => hint
            .saturating_add(64)
            .min(input.len().saturating_mul(1032).saturating_add(4096)),
        _ => decompress_capacity_hint(input.len()),
    };
    if let Some(limit) = limit {
        capacity = capacity.min(limit);
    }
    let mut output = BytesSink::with_capacity(capacity)?;
    let result = decompressor
        .stream
        .run(input, InflateFlush::Sync, limit, &mut output)?;
    let rest = &input[result.consumed.min(input.len())..];
    if result.code == Z_STREAM_END {
        decompressor.eof = true;
        decompressor.needs_input = false;
        if !rest.is_empty() {
            decompressor.unused_data = rest.to_vec();
        }
        let code = decompressor.stream.end();
        if code != Z_OK {
            return Err(zlib_failure(
                decompressor.stream.stream(),
                code,
                "while finishing decompression",
            ));
        }
    } else if result.code != Z_OK && result.code != Z_BUF_ERROR {
        return Err(zlib_failure(
            decompressor.stream.stream(),
            result.code,
            "while decompressing data",
        ));
    } else if rest.is_empty() {
        decompressor.needs_input = limit != Some(output.written());
    } else {
        decompressor.needs_input = false;
        decompressor.pending = rest.to_vec();
    }
    output.finish()
}

fn decompressor_eof_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [state] = *exactly::<1>(arguments, c"eof() takes exactly one argument")?;
    Ok(boolean(unsafe { capsule_state::<Decompressor>(state) }?.eof))
}

fn decompressor_needs_input_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [state] = *exactly::<1>(arguments, c"needs_input() takes exactly one argument")?;
    Ok(boolean(unsafe { capsule_state::<Decompressor>(state) }?.needs_input))
}

fn decompressor_unused_data_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    let [state] = *exactly::<1>(arguments, c"unused_data() takes exactly one argument")?;
    BytesWriter::copy_of(&unsafe { capsule_state::<Decompressor>(state) }?.unused_data)
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

entry_point!(compressor_new, compressor_new_call);
entry_point!(compressor_compress, compressor_compress_call);
entry_point!(compressor_flush, compressor_flush_call);
entry_point!(compress_member, compress_member_call);
entry_point!(crc32_update, crc32_call);
entry_point!(decompressor_new, decompressor_new_call);
entry_point!(decompressor_decompress, decompressor_decompress_call);
entry_point!(decompressor_eof, decompressor_eof_call);
entry_point!(decompressor_needs_input, decompressor_needs_input_call);
entry_point!(decompressor_unused_data, decompressor_unused_data_call);

static METHODS: [PyMethodDef; 11] = [
    fastcall(c"compressor", compressor_new, c"Create a raw-DEFLATE compressor."),
    fastcall(c"compress", compressor_compress, c"Compress one input block."),
    fastcall(c"flush", compressor_flush, c"Flush a raw-DEFLATE compressor."),
    fastcall(c"decompressor", decompressor_new, c"Create a raw-DEFLATE decompressor."),
    fastcall(c"decompress", decompressor_decompress, c"Decompress one input block."),
    fastcall(c"eof", decompressor_eof, c"Return whether the DEFLATE stream ended."),
    fastcall(
        c"needs_input",
        decompressor_needs_input,
        c"Return whether more compressed input is needed.",
    ),
    fastcall(c"unused_data", decompressor_unused_data, c"Return bytes following the DEFLATE stream."),
    fastcall(c"compress_member", compress_member, c"Compress data into one complete gzip member."),
    fastcall(c"crc32", crc32_update, c"Update a running CRC-32 with data."),
    method_table_end(),
];

static MODULE: Module = Module::new(c"_gzip_rs", c"Rust raw-DEFLATE codecs for gzip.", &METHODS);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__gzip_rs() -> *mut PyObject {
    MODULE.init()
}
