use std::ffi::{CStr, CString, c_int, c_ulong};
use std::mem;

use cpython_binding::arguments::unsigned_long_mask_argument;
use cpython_binding::values::unsigned_long;
use cpython_binding::{Borrowed, Buffer, Exception, Outcome, Owned, Sink, Stop, raise};
use libz_rs_sys::{
    crc32_z, deflate, deflateBound, deflateCopy, deflateEnd, deflateInit2_, inflate, inflateCopy,
    inflateEnd, inflateInit2_, z_stream, zlibVersion,
};

pub use libz_rs_sys::{
    Z_BUF_ERROR, Z_DATA_ERROR, Z_FINISH, Z_MEM_ERROR, Z_NO_FLUSH, Z_OK, Z_STREAM_END,
    Z_STREAM_ERROR, Z_SYNC_FLUSH, alloc_func, free_func,
};

const DEFLATED: c_int = 8;
const DEF_MEM_LEVEL: c_int = 8;
const Z_DEFAULT_STRATEGY: c_int = 0;
const MESSAGE_LIMIT: usize = 200;

pub fn crc32(initial: c_ulong, data: &[u8]) -> c_ulong {
    unsafe { crc32_z(initial, data.as_ptr(), data.len()) }
}

/// `crc32(data, value=0)` as the Python modules expose it.
pub fn crc32_call(arguments: &[Borrowed<'_>]) -> Outcome<Owned> {
    if !(1..=2).contains(&arguments.len()) {
        return Err(raise(
            Exception::TypeError,
            c"crc32() takes one or two arguments",
        ));
    }
    let input = Buffer::acquire(arguments[0])?;
    let initial = match arguments.get(1) {
        Some(initial) => unsigned_long_mask_argument(*initial)? & 0xffff_ffff,
        None => 0,
    };
    unsigned_long(crc32(initial, input.as_bytes()))
}

pub fn compress_capacity_hint(input_len: usize) -> usize {
    (input_len / 4 + 64).clamp(1024, 1 << 20)
}

pub fn decompress_capacity_hint(input_len: usize) -> usize {
    input_len.saturating_mul(4).clamp(4096, 1 << 26)
}

/// A custom zlib allocator for the engine state.
#[derive(Clone, Copy)]
pub struct StateAllocator {
    pub allocate: alloc_func,
    pub release: free_func,
}

/// Raise `ValueError("Error <code> <what>: <zlib message>")`, which the
/// Python side re-raises as `zlib.error` with the C module's wording.
pub fn zlib_failure(stream: &z_stream, code: c_int, what: &str) -> Stop {
    let detail = if !stream.msg.is_null() {
        Some(
            unsafe { CStr::from_ptr(stream.msg) }
                .to_string_lossy()
                .chars()
                .take(MESSAGE_LIMIT)
                .collect::<String>(),
        )
    } else {
        match code {
            Z_BUF_ERROR => Some("incomplete or truncated stream".to_owned()),
            Z_STREAM_ERROR => Some("inconsistent stream state".to_owned()),
            Z_DATA_ERROR => Some("invalid input data".to_owned()),
            _ => None,
        }
    };
    let text = match detail {
        Some(detail) => format!("Error {code} {what}: {detail}"),
        None => format!("Error {code} {what}"),
    };
    raise(
        Exception::ValueError,
        &CString::new(text).unwrap_or_default(),
    )
}

/// The failure of a stream that could not be created or copied.
pub fn setup_failure(code: c_int, what: &str) -> Stop {
    if code == Z_MEM_ERROR {
        return out_of_memory();
    }
    zlib_failure(&z_stream::default(), code, what)
}

/// The failure of a stream copy.
pub fn copy_failure(stream: &z_stream, code: c_int, memory: &CStr, what: &str) -> Stop {
    match code {
        Z_MEM_ERROR => raise(Exception::MemoryError, memory),
        Z_STREAM_ERROR => raise(Exception::ValueError, c"Inconsistent stream state"),
        code => zlib_failure(stream, code, what),
    }
}

pub fn out_of_memory() -> Stop {
    raise(Exception::MemoryError, c"Out of memory")
}

fn output_too_large() -> Stop {
    raise(Exception::MemoryError, c"output too large")
}

/// Double the full sink, never past `ceiling` bytes.
fn double<S: Sink>(sink: &mut S, ceiling: usize) -> Outcome<()> {
    let capacity = sink.written();
    let doubled = capacity
        .checked_mul(2)
        .ok_or_else(output_too_large)?
        .min(ceiling);
    sink.grow(doubled.max(capacity + 1) - capacity)
}

/// Point `stream` at the sink's room and return how much there is.
fn point<S: Sink>(sink: &mut S, stream: &mut z_stream) -> usize {
    let spare = sink.spare();
    let room = spare.len().min(u32::MAX as usize);
    stream.next_out = spare.as_mut_ptr().cast();
    stream.avail_out = room as u32;
    room
}

fn disarm<S: Sink>(sink: &mut S, stream: &z_stream, room: usize) {
    unsafe { sink.advance(room - stream.avail_out as usize) };
}

#[derive(Debug)]
pub enum RunError {
    /// A Python exception is already set.
    Raised,
    Zlib(c_int),
}

impl From<Stop> for RunError {
    fn from(_: Stop) -> Self {
        Self::Raised
    }
}

/// The `window_bits` of a zlib or raw-DEFLATE stream.
pub const ZLIB_WINDOW: c_int = 15;
pub const RAW_WINDOW: c_int = -15;

pub struct Deflater {
    stream: Box<z_stream>,
    live: bool,
}

impl Deflater {
    pub fn new(
        level: c_int,
        window_bits: c_int,
        allocator: Option<StateAllocator>,
    ) -> Result<Self, c_int> {
        let mut stream = Box::new(z_stream::default());
        if let Some(allocator) = allocator {
            stream.zalloc = Some(allocator.allocate);
            stream.zfree = Some(allocator.release);
        }
        let code = unsafe {
            deflateInit2_(
                &mut *stream,
                level,
                DEFLATED,
                window_bits,
                DEF_MEM_LEVEL,
                Z_DEFAULT_STRATEGY,
                zlibVersion(),
                mem::size_of::<z_stream>() as c_int,
            )
        };
        if code != Z_OK {
            return Err(code);
        }
        Ok(Self { stream, live: true })
    }

    pub fn is_live(&self) -> bool {
        self.live
    }

    pub fn stream(&self) -> &z_stream {
        &self.stream
    }

    pub fn bound(&mut self, input_len: usize) -> usize {
        unsafe { deflateBound(&mut *self.stream, input_len as c_ulong) as usize }
    }

    pub fn end(&mut self) -> c_int {
        if !self.live {
            return Z_OK;
        }
        self.live = false;
        unsafe { deflateEnd(&mut *self.stream) }
    }

    pub fn duplicate(&mut self) -> Result<Self, c_int> {
        let mut stream = Box::new(z_stream::default());
        match unsafe { deflateCopy(&mut *stream, &mut *self.stream) } {
            Z_OK => Ok(Self { stream, live: true }),
            code => Err(code),
        }
    }

    pub fn failure(&self, error: RunError, what: &str) -> Stop {
        match error {
            RunError::Raised => Stop::Raised,
            RunError::Zlib(code) => zlib_failure(&self.stream, code, what),
        }
    }

    /// Compress `input`, applying `final_flush` to its last chunk, and write
    /// the output to `sink`. Returns the last deflate result.
    pub fn run<S: Sink>(
        &mut self,
        input: &[u8],
        final_flush: c_int,
        sink: &mut S,
    ) -> Result<c_int, RunError> {
        let mut offset = 0usize;
        loop {
            let chunk = (input.len() - offset).min(u32::MAX as usize);
            self.stream.next_in = unsafe { input.as_ptr().add(offset) };
            self.stream.avail_in = chunk as u32;
            let last = offset + chunk == input.len();
            let flush = if last { final_flush } else { Z_NO_FLUSH };
            let code = loop {
                if sink.spare().is_empty() {
                    double(sink, usize::MAX)?;
                }
                let room = point(sink, &mut self.stream);
                let code = if self.live {
                    unsafe { deflate(&mut *self.stream, flush) }
                } else {
                    Z_STREAM_ERROR
                };
                disarm(sink, &self.stream, room);
                if code == Z_STREAM_ERROR {
                    return Err(RunError::Zlib(code));
                }
                if code == Z_STREAM_END || self.stream.avail_out != 0 {
                    break code;
                }
            };
            if last {
                return Ok(code);
            }
            offset += chunk;
        }
    }
}

impl Drop for Deflater {
    fn drop(&mut self) {
        self.end();
    }
}

/// How `Inflater::run` flushes each chunk of input.
#[derive(Clone, Copy)]
pub enum InflateFlush {
    /// `Z_SYNC_FLUSH` for every chunk, as incremental decompression does.
    Sync,
    /// `Z_FINISH` for the last chunk, as a one-shot decompression does.
    FinishLast,
}

#[derive(Debug)]
pub struct Inflated {
    pub code: c_int,
    pub consumed: usize,
}

pub struct Inflater {
    stream: Box<z_stream>,
    live: bool,
}

impl Inflater {
    pub fn new(window_bits: c_int) -> Result<Self, c_int> {
        let mut stream = Box::new(z_stream::default());
        let code = unsafe {
            inflateInit2_(
                &mut *stream,
                window_bits,
                zlibVersion(),
                mem::size_of::<z_stream>() as c_int,
            )
        };
        if code != Z_OK {
            return Err(code);
        }
        Ok(Self { stream, live: true })
    }

    pub fn is_live(&self) -> bool {
        self.live
    }

    pub fn stream(&self) -> &z_stream {
        &self.stream
    }

    pub fn end(&mut self) -> c_int {
        if !self.live {
            return Z_OK;
        }
        self.live = false;
        unsafe { inflateEnd(&mut *self.stream) }
    }

    pub fn duplicate(&self) -> Result<Self, c_int> {
        let mut stream = Box::new(z_stream::default());
        match unsafe { inflateCopy(&mut *stream, &*self.stream) } {
            Z_OK => Ok(Self { stream, live: true }),
            code => Err(code),
        }
    }

    /// Decompress `input` into `sink`. Stops at the end of the stream, at
    /// `limit` output bytes, or on a zlib error other than running out of
    /// memory, which raises. Returns the last inflate result and how much
    /// input was consumed.
    pub fn run<S: Sink>(
        &mut self,
        input: &[u8],
        flush_mode: InflateFlush,
        limit: Option<usize>,
        sink: &mut S,
    ) -> Outcome<Inflated> {
        let base = input.as_ptr() as usize;
        let mut offset = 0usize;
        let mut code = Z_OK;
        loop {
            let chunk = (input.len() - offset).min(u32::MAX as usize);
            self.stream.next_in = unsafe { input.as_ptr().add(offset) };
            self.stream.avail_in = chunk as u32;
            let last = offset + chunk == input.len();
            let flush = match flush_mode {
                InflateFlush::Sync => Z_SYNC_FLUSH,
                InflateFlush::FinishLast if last => Z_FINISH,
                InflateFlush::FinishLast => Z_NO_FLUSH,
            };
            loop {
                if sink.spare().is_empty() {
                    if limit.is_some_and(|limit| sink.written() >= limit) {
                        return Ok(self.inflated(code, base));
                    }
                    double(sink, limit.unwrap_or(usize::MAX))?;
                }
                let room = point(sink, &mut self.stream);
                code = if self.live {
                    unsafe { inflate(&mut *self.stream, flush) }
                } else {
                    Z_STREAM_ERROR
                };
                disarm(sink, &self.stream, room);
                match code {
                    Z_OK | Z_BUF_ERROR => {}
                    Z_STREAM_END => break,
                    Z_MEM_ERROR => return Err(out_of_memory()),
                    _ => return Ok(self.inflated(code, base)),
                }
                if self.stream.avail_out != 0 {
                    break;
                }
            }
            if code == Z_STREAM_END || last {
                return Ok(self.inflated(code, base));
            }
            offset += chunk;
        }
    }

    fn inflated(&self, code: c_int, base: usize) -> Inflated {
        Inflated {
            code,
            consumed: self.stream.next_in as usize - base,
        }
    }
}

impl Drop for Inflater {
    fn drop(&mut self) {
        self.end();
    }
}
