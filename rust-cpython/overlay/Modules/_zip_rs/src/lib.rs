use std::cell::UnsafeCell;
use std::ffi::{CStr, CString, c_char, c_int, c_void};
use std::mem::{self, MaybeUninit};
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyBuffer_Release;
use cpython_sys::PyBytes_AsString;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyCapsule_GetPointer;
use cpython_sys::PyCapsule_New;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_MemoryError;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyLong_AsLong;
use cpython_sys::PyLong_AsLongLong;
use cpython_sys::PyLong_AsUnsignedLongMask;
use cpython_sys::PyLong_FromUnsignedLong;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_buffer;
use cpython_sys::Py_ssize_t;
use cpython_sys::_PyBytes_Resize;
use libz_rs_sys::{
    Z_BUF_ERROR, Z_DATA_ERROR, Z_FINISH, Z_MEM_ERROR, Z_NO_FLUSH, Z_OK, Z_STREAM_END,
    Z_STREAM_ERROR, Z_SYNC_FLUSH, crc32_z, deflate, deflateEnd, deflateInit2_, inflate,
    inflateEnd, inflateInit2_, z_stream, zlibVersion,
};

const PYBUF_SIMPLE: c_int = 0;
const DEFLATED: c_int = 8;
const RAW_WBITS: c_int = -15;
const DEF_MEM_LEVEL: c_int = 8;
const Z_DEFAULT_STRATEGY: c_int = 0;
const COMPRESSOR_CAPSULE: &CStr = c"_zip_rs.Compressor";
const DECOMPRESSOR_CAPSULE: &CStr = c"_zip_rs.Decompressor";

/// A borrowed `Py_buffer` over the caller's object; zlib reads it in place.
struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    fn from_object(object: *mut PyObject) -> Option<Self> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        unsafe {
            if PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) != 0 {
                return None;
            }
            Some(Self { view: view.assume_init() })
        }
    }

    fn bytes(&self) -> &[u8] {
        if self.view.len <= 0 {
            return &[];
        }
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

/// A `bytes` object that zlib writes into directly and that is resized to the
/// written length at the end, so no intermediate buffer or copy is made.
struct PyBuf {
    object: *mut PyObject,
    ptr: *mut u8,
    cap: usize,
    len: usize,
    armed: usize,
}

enum Arm {
    Ready,
    Limit,
    Fail,
}

fn set_memory_error() {
    unsafe { PyErr_SetString(PyExc_MemoryError, c"output too large".as_ptr()) };
}

impl PyBuf {
    /// On failure a Python exception is set.
    fn new(cap: usize) -> Option<Self> {
        let cap = cap.max(1);
        if cap > Py_ssize_t::MAX as usize {
            set_memory_error();
            return None;
        }
        let object = unsafe { PyBytes_FromStringAndSize(ptr::null(), cap as Py_ssize_t) };
        if object.is_null() {
            return None;
        }
        let ptr = unsafe { PyBytes_AsString(object) }.cast::<u8>();
        Some(Self { object, ptr, cap, len: 0, armed: 0 })
    }

    fn resize(&mut self, cap: usize) -> bool {
        if cap > Py_ssize_t::MAX as usize {
            set_memory_error();
            return false;
        }
        if unsafe { _PyBytes_Resize(&mut self.object, cap as Py_ssize_t) } != 0 {
            // The failed resize released the object and set MemoryError.
            self.object = ptr::null_mut();
            return false;
        }
        self.ptr = unsafe { PyBytes_AsString(self.object) }.cast::<u8>();
        self.cap = cap;
        true
    }

    /// Point `z` at the free tail, doubling the capacity (never past `limit`)
    /// when it is full.
    fn arm(&mut self, z: &mut z_stream, limit: Option<usize>) -> Arm {
        if self.len == self.cap {
            let Some(mut cap) = self.cap.checked_mul(2) else {
                set_memory_error();
                return Arm::Fail;
            };
            if let Some(limit) = limit {
                if self.cap >= limit {
                    return Arm::Limit;
                }
                cap = cap.min(limit);
            }
            if !self.resize(cap) {
                return Arm::Fail;
            }
        }
        let room = (self.cap - self.len).min(u32::MAX as usize);
        z.next_out = unsafe { self.ptr.add(self.len) };
        z.avail_out = room as u32;
        self.armed = room;
        Arm::Ready
    }

    fn disarm(&mut self, z: &z_stream) {
        self.len += self.armed - z.avail_out as usize;
        self.armed = 0;
    }

    /// The result object, resized to the written length.
    fn finish(mut self) -> *mut PyObject {
        if self.len == 0 {
            return unsafe { PyBytes_FromStringAndSize(c"".as_ptr(), 0) };
        }
        if self.len != self.cap && !self.resize(self.len) {
            return ptr::null_mut();
        }
        let object = self.object;
        self.object = ptr::null_mut();
        object
    }
}

impl Drop for PyBuf {
    fn drop(&mut self) {
        if !self.object.is_null() {
            unsafe { Py_DecRef(self.object) };
        }
    }
}

struct Compressor {
    z: Box<z_stream>,
    live: bool,
}

impl Compressor {
    fn new(level: c_int) -> Result<Self, c_int> {
        let mut z = Box::new(z_stream::default());
        let err = unsafe {
            deflateInit2_(
                &mut *z,
                level,
                DEFLATED,
                RAW_WBITS,
                DEF_MEM_LEVEL,
                Z_DEFAULT_STRATEGY,
                zlibVersion(),
                mem::size_of::<z_stream>() as c_int,
            )
        };
        if err != Z_OK {
            return Err(err);
        }
        Ok(Self { z, live: true })
    }

    fn end(&mut self) {
        if self.live {
            self.live = false;
            unsafe { deflateEnd(&mut *self.z) };
        }
    }
}

impl Drop for Compressor {
    fn drop(&mut self) {
        self.end();
    }
}

struct Decompressor {
    z: Box<z_stream>,
    live: bool,
    eof: bool,
    unused_data: Vec<u8>,
    unconsumed_tail: Vec<u8>,
}

impl Decompressor {
    fn new() -> Result<Self, c_int> {
        let mut z = Box::new(z_stream::default());
        let err = unsafe {
            inflateInit2_(&mut *z, RAW_WBITS, zlibVersion(), mem::size_of::<z_stream>() as c_int)
        };
        if err != Z_OK {
            return Err(err);
        }
        Ok(Self { z, live: true, eof: false, unused_data: Vec::new(), unconsumed_tail: Vec::new() })
    }

    fn end(&mut self) {
        if self.live {
            self.live = false;
            unsafe { inflateEnd(&mut *self.z) };
        }
    }
}

impl Drop for Decompressor {
    fn drop(&mut self) {
        self.end();
    }
}

fn set_type_error(message: &'static CStr) {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) }
}

fn set_value_error(message: &'static CStr) {
    unsafe { PyErr_SetString(PyExc_ValueError, message.as_ptr()) }
}

/// Raise `ValueError("Error <err> <what>: <zlib message>")`; the Python side
/// re-raises it as `zlib.error`.
fn set_zlib_error(z: &z_stream, err: c_int, what: &str) {
    let zmsg: Option<String> = if !z.msg.is_null() {
        Some(unsafe { CStr::from_ptr(z.msg) }.to_string_lossy().chars().take(200).collect())
    } else {
        match err {
            Z_BUF_ERROR => Some("incomplete or truncated stream".to_owned()),
            Z_STREAM_ERROR => Some("inconsistent stream state".to_owned()),
            Z_DATA_ERROR => Some("invalid input data".to_owned()),
            _ => None,
        }
    };
    let text = match zmsg {
        Some(zmsg) => format!("Error {err} {what}: {zmsg}"),
        None => format!("Error {err} {what}"),
    };
    let text = CString::new(text).unwrap_or_default();
    unsafe { PyErr_SetString(PyExc_ValueError, text.as_ptr()) }
}

fn set_init_error(err: c_int, what: &str) {
    if err == Z_MEM_ERROR {
        unsafe { PyErr_SetString(PyExc_MemoryError, c"Out of memory".as_ptr()) };
    } else {
        set_zlib_error(&z_stream::default(), err, what);
    }
}

unsafe fn read_capsule<T>(argument: *mut PyObject, name: &'static CStr) -> Option<*mut T> {
    let pointer = unsafe { PyCapsule_GetPointer(argument, name.as_ptr()) };
    if pointer.is_null() {
        return None;
    }
    Some(pointer.cast::<T>())
}

unsafe fn new_capsule<T>(
    value: T,
    name: &'static CStr,
    destructor: unsafe extern "C" fn(*mut PyObject),
) -> *mut PyObject {
    let pointer = Box::into_raw(Box::new(value));
    let capsule =
        unsafe { PyCapsule_New(pointer.cast::<c_void>(), name.as_ptr(), Some(destructor)) };
    if capsule.is_null() {
        unsafe { drop(Box::from_raw(pointer)) };
    }
    capsule
}

unsafe extern "C" fn free_compressor(capsule: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, COMPRESSOR_CAPSULE.as_ptr()) };
    if !pointer.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<Compressor>())) };
    }
}

unsafe extern "C" fn free_decompressor(capsule: *mut PyObject) {
    let pointer = unsafe { PyCapsule_GetPointer(capsule, DECOMPRESSOR_CAPSULE.as_ptr()) };
    if !pointer.is_null() {
        unsafe { drop(Box::from_raw(pointer.cast::<Decompressor>())) };
    }
}

unsafe fn bytes_from_slice(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        set_memory_error();
        return ptr::null_mut();
    }
    unsafe { PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

enum Fail {
    /// A Python exception is already set.
    Python,
    /// zlib reported this code.
    Zlib(c_int),
}

/// Feed `input` to deflate, applying `final_flush` to the last chunk, and write
/// the output into `out`. Returns the last deflate result.
unsafe fn deflate_run(
    c: &mut Compressor,
    input: &[u8],
    final_flush: c_int,
    out: &mut PyBuf,
) -> Result<c_int, Fail> {
    let mut offset = 0usize;
    let mut err;
    loop {
        let chunk = (input.len() - offset).min(u32::MAX as usize);
        c.z.next_in = unsafe { input.as_ptr().add(offset) };
        c.z.avail_in = chunk as u32;
        let last = offset + chunk == input.len();
        let flush = if last { final_flush } else { Z_NO_FLUSH };
        loop {
            match out.arm(&mut c.z, None) {
                Arm::Ready => {}
                Arm::Limit | Arm::Fail => return Err(Fail::Python),
            }
            err = if c.live { unsafe { deflate(&mut *c.z, flush) } } else { Z_STREAM_ERROR };
            out.disarm(&c.z);
            if err == Z_STREAM_ERROR {
                return Err(Fail::Zlib(err));
            }
            if err == Z_STREAM_END || c.z.avail_out != 0 {
                break;
            }
        }
        if last {
            return Ok(err);
        }
        offset += chunk;
    }
}

/// Inflate `input` into `out` with `Z_SYNC_FLUSH`. Stops at the end of the
/// stream, at `limit` output bytes, or on a zlib error. Returns the last
/// inflate result and how much input was consumed.
unsafe fn inflate_run(
    d: &mut Decompressor,
    input: &[u8],
    limit: Option<usize>,
    out: &mut PyBuf,
) -> Result<(c_int, usize), Fail> {
    let base = input.as_ptr() as usize;
    let mut offset = 0usize;
    let mut err = Z_OK;
    loop {
        let chunk = (input.len() - offset).min(u32::MAX as usize);
        d.z.next_in = unsafe { input.as_ptr().add(offset) };
        d.z.avail_in = chunk as u32;
        let last = offset + chunk == input.len();
        loop {
            match out.arm(&mut d.z, limit) {
                Arm::Ready => {}
                Arm::Limit => return Ok((err, d.z.next_in as usize - base)),
                Arm::Fail => return Err(Fail::Python),
            }
            err = if d.live { unsafe { inflate(&mut *d.z, Z_SYNC_FLUSH) } } else { Z_STREAM_ERROR };
            out.disarm(&d.z);
            match err {
                Z_OK | Z_BUF_ERROR => {}
                Z_STREAM_END => break,
                Z_MEM_ERROR => {
                    unsafe { PyErr_SetString(PyExc_MemoryError, c"Out of memory".as_ptr()) };
                    return Err(Fail::Python);
                }
                _ => return Ok((err, d.z.next_in as usize - base)),
            }
            if d.z.avail_out != 0 {
                break;
            }
        }
        if err == Z_STREAM_END || last {
            return Ok((err, d.z.next_in as usize - base));
        }
        offset += chunk;
    }
}

/// Keep unused input after the end of the stream and the input left when the
/// output limit was reached, as zlib's decompress objects do.
fn save_unconsumed(d: &mut Decompressor, input: &[u8], consumed: usize, err: c_int) {
    let leftover = &input[consumed.min(input.len())..];
    let mut has_input = !leftover.is_empty();
    if err == Z_STREAM_END && has_input {
        d.unused_data.extend_from_slice(leftover);
        has_input = false;
    }
    if has_input || !d.unconsumed_tail.is_empty() {
        d.unconsumed_tail = leftover.to_vec();
    }
}

fn compress_estimate(len: usize) -> usize {
    (len / 4 + 64).clamp(1024, 1 << 20)
}

fn decompress_estimate(len: usize) -> usize {
    len.saturating_mul(4).clamp(4096, 1 << 26)
}

unsafe extern "C" fn compressor_new(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"compressor() takes exactly one argument");
        return ptr::null_mut();
    }
    let level = unsafe { PyLong_AsLong(*args) };
    if level == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if !(-1..=9).contains(&level) {
        set_value_error(c"compression level must be between 0 and 9");
        return ptr::null_mut();
    }
    match Compressor::new(level as c_int) {
        Ok(compressor) => unsafe { new_capsule(compressor, COMPRESSOR_CAPSULE, free_compressor) },
        Err(err) => {
            set_init_error(err, "while creating compression object");
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn crc32(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !(1..=2).contains(&nargs) {
        set_type_error(c"crc32() takes one or two arguments");
        return ptr::null_mut();
    }
    let Some(input) = BorrowedBuffer::from_object(unsafe { *args }) else {
        return ptr::null_mut();
    };
    let initial = if nargs == 2 {
        let value = unsafe { PyLong_AsUnsignedLongMask(*args.add(1)) };
        if value == std::ffi::c_ulong::MAX && !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        value & 0xffff_ffff
    } else {
        0
    };
    let bytes = input.bytes();
    let value = unsafe { crc32_z(initial, bytes.as_ptr(), bytes.len()) };
    unsafe { PyLong_FromUnsignedLong(value) }
}

unsafe extern "C" fn compressor_compress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"compress() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(compressor) = (unsafe { read_capsule::<Compressor>(*args, COMPRESSOR_CAPSULE) })
    else {
        return ptr::null_mut();
    };
    let compressor = unsafe { &mut *compressor };
    let Some(input) = BorrowedBuffer::from_object(unsafe { *args.add(1) }) else {
        return ptr::null_mut();
    };
    let input = input.bytes();
    let Some(mut out) = PyBuf::new(compress_estimate(input.len())) else {
        return ptr::null_mut();
    };
    match unsafe { deflate_run(compressor, input, Z_NO_FLUSH, &mut out) } {
        Ok(_) => out.finish(),
        Err(Fail::Python) => ptr::null_mut(),
        Err(Fail::Zlib(err)) => {
            set_zlib_error(&compressor.z, err, "while compressing data");
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn compressor_flush(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"flush() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(compressor) = (unsafe { read_capsule::<Compressor>(*args, COMPRESSOR_CAPSULE) })
    else {
        return ptr::null_mut();
    };
    let compressor = unsafe { &mut *compressor };
    let mode = unsafe { PyLong_AsLongLong(*args.add(1)) };
    if mode == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if !(0..=5).contains(&mode) {
        set_value_error(c"invalid compressor flush mode");
        return ptr::null_mut();
    }
    let mode = mode as c_int;
    if mode == Z_NO_FLUSH {
        return unsafe { PyBytes_FromStringAndSize(c"".as_ptr(), 0) };
    }
    let Some(mut out) = PyBuf::new(1024) else {
        return ptr::null_mut();
    };
    let err = match unsafe { deflate_run(compressor, &[], mode, &mut out) } {
        Ok(err) => err,
        Err(Fail::Python) => return ptr::null_mut(),
        Err(Fail::Zlib(err)) => {
            set_zlib_error(&compressor.z, err, "while flushing");
            return ptr::null_mut();
        }
    };
    if err == Z_STREAM_END && mode == Z_FINISH {
        compressor.end();
    } else if err != Z_OK && err != Z_BUF_ERROR {
        set_zlib_error(&compressor.z, err, "while flushing");
        return ptr::null_mut();
    }
    out.finish()
}

unsafe extern "C" fn decompressor_new(
    _module: *mut PyObject,
    _args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 0 {
        set_type_error(c"decompressor() takes no arguments");
        return ptr::null_mut();
    }
    match Decompressor::new() {
        Ok(decompressor) => unsafe {
            new_capsule(decompressor, DECOMPRESSOR_CAPSULE, free_decompressor)
        },
        Err(err) => {
            set_init_error(err, "while creating decompression object");
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn decompressor_decompress(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        set_type_error(c"decompress() takes exactly three arguments");
        return ptr::null_mut();
    }
    let Some(decompressor) =
        (unsafe { read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE) })
    else {
        return ptr::null_mut();
    };
    let decompressor = unsafe { &mut *decompressor };
    let Some(input) = BorrowedBuffer::from_object(unsafe { *args.add(1) }) else {
        return ptr::null_mut();
    };
    let max_length = unsafe { PyLong_AsLongLong(*args.add(2)) };
    if max_length == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return ptr::null_mut();
    }
    if max_length < 0 {
        set_value_error(c"max_length must be non-negative");
        return ptr::null_mut();
    }
    let input = input.bytes();
    if decompressor.eof {
        decompressor.unused_data.extend_from_slice(input);
        return unsafe { PyBytes_FromStringAndSize(c"".as_ptr(), 0) };
    }
    let limit = if max_length == 0 { None } else { Some(max_length as usize) };
    let mut estimate = decompress_estimate(input.len());
    if let Some(limit) = limit {
        estimate = estimate.min(limit);
    }
    let Some(mut out) = PyBuf::new(estimate) else {
        return ptr::null_mut();
    };
    let (err, consumed) = match unsafe { inflate_run(decompressor, input, limit, &mut out) } {
        Ok(result) => result,
        Err(_) => return ptr::null_mut(),
    };
    save_unconsumed(decompressor, input, consumed, err);
    if err == Z_STREAM_END {
        decompressor.eof = true;
    } else if err != Z_OK && err != Z_BUF_ERROR {
        set_zlib_error(&decompressor.z, err, "while decompressing data");
        return ptr::null_mut();
    }
    out.finish()
}

unsafe extern "C" fn decompressor_eof(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"eof() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(decompressor) =
        (unsafe { read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE) })
    else {
        return ptr::null_mut();
    };
    let eof = unsafe { (*decompressor).eof };
    unsafe { PyBool_FromLong(eof as _) }
}

unsafe extern "C" fn decompressor_unconsumed_tail(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"unconsumed_tail() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(decompressor) =
        (unsafe { read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE) })
    else {
        return ptr::null_mut();
    };
    unsafe { bytes_from_slice(&(*decompressor).unconsumed_tail) }
}

unsafe extern "C" fn decompressor_unused_data(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"unused_data() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(decompressor) =
        (unsafe { read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE) })
    else {
        return ptr::null_mut();
    };
    unsafe { bytes_from_slice(&(*decompressor).unused_data) }
}

pub extern "C" fn _zip_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _zip_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

macro_rules! method {
    ($name:expr, $func:ident, $doc:expr) => {
        PyMethodDef {
            ml_name: $name.as_ptr() as *mut c_char,
            ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: $func },
            ml_flags: METH_FASTCALL,
            ml_doc: $doc.as_ptr() as *mut c_char,
        }
    };
}

pub static _ZIP_RS_MODULE_METHODS: [PyMethodDef; 10] = [
    method!(c"crc32", crc32, c"Compute a seeded ZIP CRC-32 checksum."),
    method!(c"compressor", compressor_new, c"Create a raw-DEFLATE compressor."),
    method!(c"compress", compressor_compress, c"Compress one input block."),
    method!(c"flush", compressor_flush, c"Flush a raw-DEFLATE compressor."),
    method!(c"decompressor", decompressor_new, c"Create a raw-DEFLATE decompressor."),
    method!(c"decompress", decompressor_decompress, c"Decompress one input block."),
    method!(c"eof", decompressor_eof, c"Return whether the DEFLATE stream ended."),
    method!(
        c"unconsumed_tail",
        decompressor_unconsumed_tail,
        c"Return compressed bytes not yet consumed."
    ),
    method!(
        c"unused_data",
        decompressor_unused_data,
        c"Return bytes following the DEFLATE stream."
    ),
    PyMethodDef::zeroed(),
];

pub static _ZIP_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_zip_rs".as_ptr() as *mut _,
        m_doc: c"Rust raw-DEFLATE codecs for ZIP entries.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_ZIP_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_zip_rs_clear),
        m_free: Some(_zip_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub unsafe extern "C" fn PyInit__zip_rs() -> *mut PyObject {
    _ZIP_RS_MODULE.init()
}
