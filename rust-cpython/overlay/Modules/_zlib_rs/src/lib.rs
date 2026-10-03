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
use cpython_sys::PyExc_OverflowError;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyLong_AsLong;
use cpython_sys::PyLong_AsSsize_t;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::{
    PyABIInfo, PySlot, PySlot__bindgen_ty_1, PySlot__bindgen_ty_2,
    Py_mod_abi, Py_mod_doc, Py_mod_methods, Py_mod_name,
    Py_mod_state_clear, Py_mod_state_free, PySlot_INTPTR, PySlot_STATIC,
};
use cpython_sys::PyNumber_Index;
use cpython_sys::PyObject;
use cpython_sys::PyObject_GetBuffer;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_buffer;
use cpython_sys::Py_ssize_t;
use cpython_sys::_PyBytes_Resize;
use libz_rs_sys::{
    Z_BUF_ERROR, Z_DATA_ERROR, Z_FINISH, Z_MEM_ERROR, Z_NO_FLUSH, Z_OK, Z_STREAM_END,
    Z_STREAM_ERROR, Z_SYNC_FLUSH, deflate, deflateBound, deflateCopy, deflateEnd, deflateInit2_,
    inflate, inflateCopy, inflateEnd, inflateInit2_, z_stream, zlibVersion,
};

const PYBUF_SIMPLE: c_int = 0;
const DEFLATED: c_int = 8;
const DEF_MEM_LEVEL: c_int = 8;
const Z_DEFAULT_STRATEGY: c_int = 0;
const COMPRESSOR_CAPSULE: &CStr = c"_zlib_rs.Compressor";
const DECOMPRESSOR_CAPSULE: &CStr = c"_zlib_rs.Decompressor";

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
    fn new(level: c_int, wbits: c_int) -> Result<Self, c_int> {
        let mut z = Box::new(z_stream::default());
        let err = unsafe {
            deflateInit2_(
                &mut *z,
                level,
                DEFLATED,
                wbits,
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

    fn end(&mut self) -> c_int {
        if !self.live {
            return Z_OK;
        }
        self.live = false;
        unsafe { deflateEnd(&mut *self.z) }
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
    fn new(wbits: c_int) -> Result<Self, c_int> {
        let mut z = Box::new(z_stream::default());
        let err = unsafe {
            inflateInit2_(&mut *z, wbits, zlibVersion(), mem::size_of::<z_stream>() as c_int)
        };
        if err != Z_OK {
            return Err(err);
        }
        Ok(Self {
            z,
            live: true,
            eof: false,
            unused_data: Vec::new(),
            unconsumed_tail: Vec::new(),
        })
    }

    fn end(&mut self) -> c_int {
        if !self.live {
            return Z_OK;
        }
        self.live = false;
        unsafe { inflateEnd(&mut *self.z) }
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
/// re-raises it as `zlib.error`, matching the C module's wording.
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

/// An `int` argument that must fit a C `int`.
unsafe fn read_c_int(argument: *mut PyObject) -> Option<c_int> {
    let value = unsafe { PyLong_AsLong(argument) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return None;
    }
    match c_int::try_from(value) {
        Ok(value) => Some(value),
        Err(_) => {
            unsafe {
                PyErr_SetString(
                    PyExc_OverflowError,
                    c"Python int too large to convert to C int".as_ptr(),
                )
            };
            None
        }
    }
}

/// An index argument converted like the C module's `Py_ssize_t` parameters.
unsafe fn read_ssize(argument: *mut PyObject) -> Option<Py_ssize_t> {
    let index = unsafe { PyNumber_Index(argument) };
    if index.is_null() {
        return None;
    }
    let value = unsafe { PyLong_AsSsize_t(index) };
    unsafe { Py_DecRef(index) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return None;
    }
    Some(value)
}

fn valid_wbits(wbits: c_int) -> bool {
    if wbits != 15 && wbits != -15 {
        set_value_error(c"unsupported DEFLATE window size");
        return false;
    }
    true
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

/// Inflate `input` into `out`. `sync` selects `Z_SYNC_FLUSH` for every chunk
/// (`Decompress.decompress`); otherwise the last chunk uses `Z_FINISH`. Stops
/// at the end of the stream, at `limit` output bytes, or on a zlib error.
/// Returns the last inflate result and how much input was consumed.
unsafe fn inflate_run(
    d: &mut Decompressor,
    input: &[u8],
    sync: bool,
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
        let flush = if sync {
            Z_SYNC_FLUSH
        } else if last {
            Z_FINISH
        } else {
            Z_NO_FLUSH
        };
        loop {
            match out.arm(&mut d.z, limit) {
                Arm::Ready => {}
                Arm::Limit => return Ok((err, d.z.next_in as usize - base)),
                Arm::Fail => return Err(Fail::Python),
            }
            err = if d.live { unsafe { inflate(&mut *d.z, flush) } } else { Z_STREAM_ERROR };
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
/// output limit was reached, as the C module's `save_unconsumed_input` does.
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

unsafe extern "C" fn compress_once(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        set_type_error(c"compress() takes exactly three arguments");
        return ptr::null_mut();
    }
    let Some(input) = BorrowedBuffer::from_object(unsafe { *args }) else {
        return ptr::null_mut();
    };
    let Some(level) = (unsafe { read_c_int(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if !(-1..=9).contains(&level) {
        set_value_error(c"Bad compression level");
        return ptr::null_mut();
    }
    let Some(wbits) = (unsafe { read_c_int(*args.add(2)) }) else {
        return ptr::null_mut();
    };
    if !valid_wbits(wbits) {
        return ptr::null_mut();
    }
    let input = input.bytes();
    let mut compressor = match Compressor::new(level, wbits) {
        Ok(compressor) => compressor,
        Err(err) => {
            set_init_error(err, "while compressing data");
            return ptr::null_mut();
        }
    };
    let bound = unsafe { deflateBound(&mut *compressor.z, input.len() as _) } as usize;
    let Some(mut out) = PyBuf::new(bound) else {
        return ptr::null_mut();
    };
    match unsafe { deflate_run(&mut compressor, input, Z_FINISH, &mut out) } {
        Ok(_) => {}
        Err(Fail::Python) => return ptr::null_mut(),
        Err(Fail::Zlib(err)) => {
            set_zlib_error(&compressor.z, err, "while compressing data");
            return ptr::null_mut();
        }
    }
    let err = compressor.end();
    if err != Z_OK {
        set_zlib_error(&compressor.z, err, "while finishing compression");
        return ptr::null_mut();
    }
    out.finish()
}

unsafe extern "C" fn decompress_once(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"decompress() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(input) = BorrowedBuffer::from_object(unsafe { *args }) else {
        return ptr::null_mut();
    };
    let Some(wbits) = (unsafe { read_c_int(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if !valid_wbits(wbits) {
        return ptr::null_mut();
    }
    let input = input.bytes();
    let mut decompressor = match Decompressor::new(wbits) {
        Ok(decompressor) => decompressor,
        Err(err) => {
            set_init_error(err, "while preparing to decompress data");
            return ptr::null_mut();
        }
    };
    let Some(mut out) = PyBuf::new(decompress_estimate(input.len())) else {
        return ptr::null_mut();
    };
    let err = match unsafe { inflate_run(&mut decompressor, input, false, None, &mut out) } {
        Ok((err, _)) => err,
        Err(_) => return ptr::null_mut(),
    };
    if err != Z_STREAM_END {
        set_zlib_error(&decompressor.z, err, "while decompressing data");
        return ptr::null_mut();
    }
    let err = decompressor.end();
    if err != Z_OK {
        set_zlib_error(&decompressor.z, err, "while finishing decompression");
        return ptr::null_mut();
    }
    out.finish()
}

unsafe extern "C" fn compressor_new(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"compressor() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(level) = (unsafe { read_c_int(*args) }) else {
        return ptr::null_mut();
    };
    if !(-1..=9).contains(&level) {
        set_value_error(c"Bad compression level");
        return ptr::null_mut();
    }
    let Some(wbits) = (unsafe { read_c_int(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if !valid_wbits(wbits) {
        return ptr::null_mut();
    }
    match Compressor::new(level, wbits) {
        Ok(compressor) => unsafe { new_capsule(compressor, COMPRESSOR_CAPSULE, free_compressor) },
        Err(err) => {
            set_init_error(err, "while creating compression object");
            ptr::null_mut()
        }
    }
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
    let Some(mode) = (unsafe { read_c_int(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    // Flushing with Z_NO_FLUSH is a no-op.
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
        let err = compressor.end();
        if err != Z_OK {
            set_zlib_error(&compressor.z, err, "while finishing compression");
            return ptr::null_mut();
        }
    } else if err != Z_OK && err != Z_BUF_ERROR {
        set_zlib_error(&compressor.z, err, "while flushing");
        return ptr::null_mut();
    }
    out.finish()
}

unsafe extern "C" fn compressor_copy(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"copy() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(source) = (unsafe { read_capsule::<Compressor>(*args, COMPRESSOR_CAPSULE) }) else {
        return ptr::null_mut();
    };
    let source = unsafe { &mut *source };
    if !source.live {
        set_value_error(c"Inconsistent stream state");
        return ptr::null_mut();
    }
    let mut dest = Box::new(z_stream::default());
    match unsafe { deflateCopy(&mut *dest, &mut *source.z) } {
        Z_OK => {}
        Z_MEM_ERROR => {
            unsafe {
                PyErr_SetString(
                    PyExc_MemoryError,
                    c"Can't allocate memory for compression object".as_ptr(),
                )
            };
            return ptr::null_mut();
        }
        Z_STREAM_ERROR => {
            set_value_error(c"Inconsistent stream state");
            return ptr::null_mut();
        }
        err => {
            set_zlib_error(&source.z, err, "while copying compression object");
            return ptr::null_mut();
        }
    }
    let copy = Compressor { z: dest, live: true };
    unsafe { new_capsule(copy, COMPRESSOR_CAPSULE, free_compressor) }
}

unsafe extern "C" fn decompressor_new(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"decompressor() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(wbits) = (unsafe { read_c_int(*args) }) else {
        return ptr::null_mut();
    };
    if !valid_wbits(wbits) {
        return ptr::null_mut();
    }
    match Decompressor::new(wbits) {
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
    let Some(max_length) = (unsafe { read_ssize(*args.add(2)) }) else {
        return ptr::null_mut();
    };
    if max_length < 0 {
        set_value_error(c"max_length must be non-negative");
        return ptr::null_mut();
    }
    let input = input.bytes();
    let limit = if max_length == 0 { None } else { Some(max_length as usize) };
    let mut estimate = decompress_estimate(input.len());
    if let Some(limit) = limit {
        estimate = estimate.min(limit);
    }
    let Some(mut out) = PyBuf::new(estimate) else {
        return ptr::null_mut();
    };
    let (err, consumed) = match unsafe { inflate_run(decompressor, input, true, limit, &mut out) }
    {
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

unsafe extern "C" fn decompressor_flush(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        set_type_error(c"flush() takes exactly two arguments");
        return ptr::null_mut();
    }
    let Some(decompressor) =
        (unsafe { read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE) })
    else {
        return ptr::null_mut();
    };
    let decompressor = unsafe { &mut *decompressor };
    let Some(length) = (unsafe { read_ssize(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if length <= 0 {
        set_value_error(c"length must be greater than zero");
        return ptr::null_mut();
    }
    let input = mem::take(&mut decompressor.unconsumed_tail);
    let estimate = decompress_estimate(input.len()).min(length as usize);
    let Some(mut out) = PyBuf::new(estimate) else {
        decompressor.unconsumed_tail = input;
        return ptr::null_mut();
    };
    let (err, consumed) = match unsafe { inflate_run(decompressor, &input, false, None, &mut out) }
    {
        Ok(result) => result,
        Err(_) => {
            decompressor.unconsumed_tail = input;
            return ptr::null_mut();
        }
    };
    save_unconsumed(decompressor, &input, consumed, err);
    // At the end of the stream, release the zlib state.
    if err == Z_STREAM_END {
        decompressor.eof = true;
        let err = decompressor.end();
        if err != Z_OK {
            set_zlib_error(&decompressor.z, err, "while finishing decompression");
            return ptr::null_mut();
        }
    }
    out.finish()
}

unsafe extern "C" fn decompressor_copy(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        set_type_error(c"copy() takes exactly one argument");
        return ptr::null_mut();
    }
    let Some(source) = (unsafe { read_capsule::<Decompressor>(*args, DECOMPRESSOR_CAPSULE) })
    else {
        return ptr::null_mut();
    };
    let source = unsafe { &mut *source };
    if !source.live {
        set_value_error(c"Inconsistent stream state");
        return ptr::null_mut();
    }
    let mut dest = Box::new(z_stream::default());
    match unsafe { inflateCopy(&mut *dest, &*source.z) } {
        Z_OK => {}
        Z_MEM_ERROR => {
            unsafe {
                PyErr_SetString(
                    PyExc_MemoryError,
                    c"Can't allocate memory for decompression object".as_ptr(),
                )
            };
            return ptr::null_mut();
        }
        Z_STREAM_ERROR => {
            set_value_error(c"Inconsistent stream state");
            return ptr::null_mut();
        }
        err => {
            set_zlib_error(&source.z, err, "while copying decompression object");
            return ptr::null_mut();
        }
    }
    let copy = Decompressor {
        z: dest,
        live: true,
        eof: source.eof,
        unused_data: source.unused_data.clone(),
        unconsumed_tail: source.unconsumed_tail.clone(),
    };
    unsafe { new_capsule(copy, DECOMPRESSOR_CAPSULE, free_decompressor) }
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
    unsafe { PyBool_FromLong(if eof { 1 } else { 0 }) }
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

pub extern "C" fn _zlib_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _zlib_rs_free(_object: *mut c_void) {}

pub static _ZLIB_RS_MODULE_METHODS: [PyMethodDef; 14] = [
    PyMethodDef {
        ml_name: c"compress_once".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compress_once },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Compress one zlib or raw-DEFLATE stream.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompress_once".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompress_once },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Decompress one zlib or raw-DEFLATE stream.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"compressor".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compressor_new },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a zlib or raw-DEFLATE compressor.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"compress".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compressor_compress },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Compress one input block.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"flush".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compressor_flush },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Flush a compressor.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"compressor_copy".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: compressor_copy },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Copy a compressor.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompressor".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_new },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Create a zlib or raw-DEFLATE decompressor.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompress".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_decompress },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Decompress one input block.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"eof".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_eof },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return whether the DEFLATE stream ended.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"unused_data".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_unused_data },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return bytes following the DEFLATE stream.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"unconsumed_tail".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_unconsumed_tail },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return compressed input not yet consumed.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompressor_flush".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_flush },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Finish a decompressor object.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"decompressor_copy".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: decompressor_copy },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Copy a decompressor.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

// The loader reads these process-lifetime tables but never mutates them.
// Python references and copied module metadata belong to each interpreter.
struct ModuleSlots([PySlot; 9]);
unsafe impl Sync for ModuleSlots {}

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

// The full non-stable ABI is the locked CPython 3.16.0a0 GIL build.
// The loader validates the major/minor version and GIL ABI before installing
// methods; the build source lock supplies the exact interpreter revision.
static ABI_INFO: PyABIInfo = PyABIInfo {
    abiinfo_major_version: 1, abiinfo_minor_version: 0, flags: 2,
    build_version: 0x031000a0, abi_version: 0x031000a0,
};

#[cfg(not(target_pointer_width = "64"))]
compile_error!("zlib slot export requires the supported 64-bit CPython ABI");

const _: () = {
    assert!(std::mem::size_of::<PySlot>() == 16);
    assert!(std::mem::align_of::<PySlot>() == 8);
    assert!(std::mem::offset_of!(PySlot, sl_id) == 0);
    assert!(std::mem::offset_of!(PySlot, sl_flags) == 2);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_1) == 4);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_2) == 8);
    assert!(std::mem::size_of::<PyABIInfo>() == 12);
    assert!(std::mem::align_of::<PyABIInfo>() == 4);
};

const fn data_slot(id: u32, value: *mut c_void) -> PySlot {
    PySlot { sl_id: id as u16, sl_flags: PySlot_INTPTR as u16,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: value } }
}

// The loader retains method definitions after copying the slots. Their array
// is immutable and lives for the process, so its pointer has static ownership.
const fn static_data_slot(id: u32, value: *mut c_void) -> PySlot {
    let mut slot = data_slot(id, value);
    slot.sl_flags |= PySlot_STATIC as u16;
    slot
}

const fn function_slot(id: u32, value: unsafe extern "C" fn()) -> PySlot {
    PySlot { sl_id: id as u16, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_func: Some(value) } }
}

// The non-limited ABI uses these new slot IDs. The binding generator omits
// their function-like compatibility macros; the native oracle checks them
// against the interpreter headers before this helper is qualified.
const MODULE_EXEC_SLOT: u32 = 85;
const MODULE_MULTIPLE_INTERPRETERS_SLOT: u16 = 86;

// Codec capsules own all mutable state. The omitted state-size and traverse
// slots preserve zero module state and no traversal callback. Clear and free
// retain their existing no-op callbacks.
static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    data_slot(Py_mod_abi, &ABI_INFO as *const PyABIInfo as *mut c_void),
    data_slot(Py_mod_name, c"_zlib_rs".as_ptr() as *mut c_void),
    data_slot(Py_mod_doc, c"Rust DEFLATE codecs for zlib.".as_ptr() as *mut c_void),
    static_data_slot(Py_mod_methods, _ZLIB_RS_MODULE_METHODS.as_ptr() as *mut c_void),
    function_slot(MODULE_EXEC_SLOT, unsafe { std::mem::transmute::<
        unsafe extern "C" fn(*mut PyObject) -> c_int, unsafe extern "C" fn()>(module_exec) }),
    PySlot { sl_id: MODULE_MULTIPLE_INTERPRETERS_SLOT, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_uint64: 2 } },
    function_slot(Py_mod_state_clear, unsafe { std::mem::transmute::<
        extern "C" fn(*mut PyObject) -> c_int, unsafe extern "C" fn()>(_zlib_rs_clear) }),
    function_slot(Py_mod_state_free, unsafe { std::mem::transmute::<
        extern "C" fn(*mut c_void), unsafe extern "C" fn()>(_zlib_rs_free) }),
    PySlot { sl_id: 0, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: ptr::null_mut() } },
]);

#[unsafe(no_mangle)]
pub extern "C" fn PyModExport__zlib_rs() -> *mut PySlot {
    MODULE_SLOTS.0.as_ptr() as *mut PySlot
}
