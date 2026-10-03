//! JSON encoding and parsing over borrowed input and Python-owned storage.
#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::hash::{Hash, Hasher};
use core::ptr;
use core::slice;

mod ffi;

use ffi::METH_FASTCALL;
use ffi::PyBool_Type;
use ffi::PyDict_New;
use ffi::PyDict_Next;
use ffi::PyDict_SetItem;
use ffi::PyDict_Type;
use ffi::PyErr_Clear;
use ffi::PyErr_NoMemory;
use ffi::PyErr_Occurred;
use ffi::PyErr_SetString;
use ffi::PyExc_TypeError;
use ffi::PyFloat_AsDouble;
use ffi::PyFloat_FromDouble;
use ffi::PyFloat_Type;
use ffi::PyList_GetItem;
use ffi::PyList_New;
use ffi::PyList_SetItem;
use ffi::PyList_Size;
use ffi::PyList_Type;
use ffi::PyLong_AsLongLongAndOverflow;
use ffi::PyLong_FromLongLong;
use ffi::PyLong_FromString;
use ffi::PyLong_Type;
use ffi::PyMem_Free;
use ffi::PyMethodDef;
use ffi::PyMethodDefFuncPointer;
use ffi::PyModuleDef;
use ffi::PyModuleDef_HEAD_INIT;
use ffi::PyModuleDef_Init;
use ffi::PyOS_double_to_string;
use ffi::PyObject;
use ffi::PyObject_IsTrue;
use ffi::PyObject_Str;
use ffi::PyTuple_GetItem;
use ffi::PyTypeObject;
use ffi::_object;
use ffi::PyTuple_Size;
use ffi::PyTuple_Type;
use ffi::PyUnicode_AsUTF8AndSize;
use ffi::PyUnicode_DATA;
use ffi::PyUnicode_FromStringAndSize;
use ffi::PyUnicode_GetLength;
use ffi::PyUnicode_KIND;
use ffi::PyUnicode_New;
use ffi::PyUnicode_Type;
use ffi::Py_DecRef;
use ffi::Py_IncRef;
use ffi::Py_ssize_t;
use ffi::_Py_FalseStruct;
use ffi::_Py_NoneStruct;
use ffi::_Py_NotImplementedStruct;
use ffi::_Py_TrueStruct;

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" { fn abort() -> !; }

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! { unsafe { abort() } }

const MAX_DEPTH: usize = 128;
const HEX: &[u8; 16] = b"0123456789abcdef";

unsafe fn type_of(object: *mut PyObject) -> *mut PyTypeObject {
    unsafe { (*object.cast::<_object>()).ob_type }
}

unsafe fn none() -> *mut PyObject {
    ptr::addr_of_mut!(_Py_NoneStruct)
}

unsafe fn new_none() -> *mut PyObject {
    let none = unsafe { none() };
    unsafe { Py_IncRef(none) };
    none
}

unsafe fn decline() -> *mut PyObject {
    let marker = ptr::addr_of_mut!(_Py_NotImplementedStruct);
    unsafe { Py_IncRef(marker) };
    marker
}

unsafe fn new_unicode(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe { PyUnicode_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t) }
}

// ---------------------------------------------------------------------------
// Encoding: walk the Python object graph once, writing ASCII JSON directly.
// Only exact built-in types are handled; anything else declines so CPython's
// encoder keeps every other behavior.

// The document is encoded twice through the same walk: once to count bytes,
// then straight into the final str, so no intermediate buffer is ever grown.
trait Sink {
    fn push(&mut self, byte: u8);
    fn extend_from_slice(&mut self, bytes: &[u8]);
    fn extend_units<T: Copy + Into<u32>>(&mut self, units: &[T]);
}

struct Counter(usize);

impl Sink for Counter {
    fn push(&mut self, _byte: u8) {
        self.0 += 1;
    }

    fn extend_from_slice(&mut self, bytes: &[u8]) {
        self.0 += bytes.len();
    }

    fn extend_units<T: Copy + Into<u32>>(&mut self, units: &[T]) {
        self.0 += units.len();
    }
}

struct Buffer {
    data: *mut u8,
    capacity: usize,
    length: usize,
}

impl Sink for Buffer {
    fn push(&mut self, byte: u8) {
        if self.length < self.capacity {
            unsafe { *self.data.add(self.length) = byte };
        }
        self.length += 1;
    }

    fn extend_from_slice(&mut self, bytes: &[u8]) {
        if self.length + bytes.len() <= self.capacity {
            unsafe { ptr::copy_nonoverlapping(bytes.as_ptr(), self.data.add(self.length), bytes.len()) };
        }
        self.length += bytes.len();
    }

    fn extend_units<T: Copy + Into<u32>>(&mut self, units: &[T]) {
        if self.length + units.len() <= self.capacity {
            for (offset, unit) in units.iter().enumerate() {
                let byte: u32 = (*unit).into();
                unsafe { *self.data.add(self.length + offset) = byte as u8 };
            }
        }
        self.length += units.len();
    }
}

struct Encoder<S: Sink> {
    out: S,
}

impl<S: Sink> Encoder<S> {
    fn write_integer(&mut self, mut value: i64) {
        let mut buffer = [0u8; 20];
        let mut index = buffer.len();
        let negative = value < 0;
        // Work in the negative range so i64::MIN needs no special case.
        if !negative {
            value = -value;
        }
        loop {
            index -= 1;
            buffer[index] = b'0' + (-(value % 10)) as u8;
            value /= 10;
            if value == 0 {
                break;
            }
        }
        if negative {
            self.out.push(b'-');
        }
        self.out.extend_from_slice(&buffer[index..]);
    }

    fn write_escape(&mut self, codepoint: u32) {
        match codepoint {
            0x22 => self.out.extend_from_slice(b"\\\""),
            0x5c => self.out.extend_from_slice(b"\\\\"),
            0x08 => self.out.extend_from_slice(b"\\b"),
            0x0c => self.out.extend_from_slice(b"\\f"),
            0x0a => self.out.extend_from_slice(b"\\n"),
            0x0d => self.out.extend_from_slice(b"\\r"),
            0x09 => self.out.extend_from_slice(b"\\t"),
            _ if codepoint <= 0xffff => self.write_unit(codepoint),
            _ => {
                let scalar = codepoint - 0x1_0000;
                self.write_unit(0xd800 + (scalar >> 10));
                self.write_unit(0xdc00 + (scalar & 0x3ff));
            }
        }
    }

    fn write_unit(&mut self, unit: u32) {
        self.out.extend_from_slice(&[
            b'\\',
            b'u',
            HEX[((unit >> 12) & 0xf) as usize],
            HEX[((unit >> 8) & 0xf) as usize],
            HEX[((unit >> 4) & 0xf) as usize],
            HEX[(unit & 0xf) as usize],
        ]);
    }

    fn write_units<T: Copy + Into<u32>>(&mut self, units: &[T]) {
        self.out.push(b'"');
        let mut run = 0;
        for (index, unit) in units.iter().enumerate() {
            let codepoint: u32 = (*unit).into();
            if (0x20..=0x7e).contains(&codepoint) && codepoint != 0x22 && codepoint != 0x5c {
                continue;
            }
            if run < index {
                self.push_run(&units[run..index]);
            }
            self.write_escape(codepoint);
            run = index + 1;
        }
        if run < units.len() {
            self.push_run(&units[run..]);
        }
        self.out.push(b'"');
    }

    fn push_run<T: Copy + Into<u32>>(&mut self, units: &[T]) {
        self.out.extend_units(units);
    }

    unsafe fn write_string(&mut self, object: *mut PyObject) -> Result<(), ()> {
        let length = unsafe { PyUnicode_GetLength(object) };
        if length < 0 {
            return Err(());
        }
        let length = length as usize;
        let data = unsafe { PyUnicode_DATA(object) };
        match unsafe { PyUnicode_KIND(object) } {
            1 => self.write_units(unsafe { slice::from_raw_parts(data.cast::<u8>(), length) }),
            2 => self.write_units(unsafe { slice::from_raw_parts(data.cast::<u16>(), length) }),
            _ => self.write_units(unsafe { slice::from_raw_parts(data.cast::<u32>(), length) }),
        }
        Ok(())
    }

    unsafe fn write_object(&mut self, object: *mut PyObject, depth: usize) -> Result<(), ()> {
        if depth > MAX_DEPTH {
            return Err(());
        }
        let object_type = unsafe { type_of(object) };
        if object_type == ptr::addr_of_mut!(PyUnicode_Type) {
            unsafe { self.write_string(object) }
        } else if object_type == ptr::addr_of_mut!(PyLong_Type) {
            let mut overflow = 0;
            let value = unsafe { PyLong_AsLongLongAndOverflow(object, &mut overflow) };
            if overflow == 0 {
                if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
                    return Err(());
                }
                self.write_integer(value);
                return Ok(());
            }
            let text = unsafe { PyObject_Str(object) };
            if text.is_null() {
                return Err(());
            }
            let mut length = 0;
            let data = unsafe { PyUnicode_AsUTF8AndSize(text, &mut length) };
            let result = if data.is_null() || length < 0 {
                Err(())
            } else {
                self.out.extend_from_slice(unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) });
                Ok(())
            };
            unsafe { Py_DecRef(text) };
            result
        } else if object_type == ptr::addr_of_mut!(PyDict_Type) {
            self.out.push(b'{');
            let mut position = 0;
            let mut first = true;
            loop {
                let mut key = ptr::null_mut();
                let mut value = ptr::null_mut();
                if unsafe { PyDict_Next(object, &mut position, &mut key, &mut value) } == 0 {
                    break;
                }
                if unsafe { type_of(key) } != ptr::addr_of_mut!(PyUnicode_Type) {
                    return Err(());
                }
                if !first {
                    self.out.extend_from_slice(b", ");
                }
                first = false;
                unsafe { self.write_string(key) }?;
                self.out.extend_from_slice(b": ");
                unsafe { self.write_object(value, depth + 1) }?;
            }
            self.out.push(b'}');
            Ok(())
        } else if object_type == ptr::addr_of_mut!(PyList_Type)
            || object_type == ptr::addr_of_mut!(PyTuple_Type)
        {
            let is_list = object_type == ptr::addr_of_mut!(PyList_Type);
            let length = unsafe {
                if is_list { PyList_Size(object) } else { PyTuple_Size(object) }
            };
            if length < 0 {
                return Err(());
            }
            self.out.push(b'[');
            for index in 0..length {
                let item = unsafe {
                    if is_list { PyList_GetItem(object, index) } else { PyTuple_GetItem(object, index) }
                };
                if item.is_null() {
                    return Err(());
                }
                if index > 0 {
                    self.out.extend_from_slice(b", ");
                }
                unsafe { self.write_object(item, depth + 1) }?;
            }
            self.out.push(b']');
            Ok(())
        } else if object_type == ptr::addr_of_mut!(PyFloat_Type) {
            let value = unsafe { PyFloat_AsDouble(object) };
            if !value.is_finite() {
                return Err(());
            }
            // Py_DTSF_ADD_DOT_0 gives float.__repr__ formatting.
            let text = unsafe { PyOS_double_to_string(value, b'r' as c_char, 0, 2, ptr::null_mut()) };
            if text.is_null() {
                return Err(());
            }
            let length = unsafe { core::ffi::CStr::from_ptr(text) }.to_bytes().len();
            self.out.extend_from_slice(unsafe { slice::from_raw_parts(text.cast::<u8>(), length) });
            unsafe { PyMem_Free(text.cast::<c_void>()) };
            Ok(())
        } else if object_type == ptr::addr_of_mut!(PyBool_Type) {
            let truth = unsafe { PyObject_IsTrue(object) };
            if truth < 0 {
                return Err(());
            }
            self.out.extend_from_slice(if truth != 0 { b"true" } else { b"false" });
            Ok(())
        } else if object == unsafe { none() } {
            self.out.extend_from_slice(b"null");
            Ok(())
        } else {
            Err(())
        }
    }
}

unsafe extern "C" fn dumps(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"dumps() takes exactly one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let mut counter = Encoder { out: Counter(0) };
    if unsafe { counter.write_object(*args, 0) }.is_err() {
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { new_none() };
    }
    let size = counter.out.0;
    if size > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    // The output is ASCII, so the str is a compact one-byte-per-character object.
    let text = unsafe { PyUnicode_New(size as Py_ssize_t, 127) };
    if text.is_null() {
        return ptr::null_mut();
    }
    let mut writer = Encoder {
        out: Buffer { data: unsafe { PyUnicode_DATA(text) }.cast::<u8>(), capacity: size, length: 0 },
    };
    if unsafe { writer.write_object(*args, 0) }.is_err() || writer.out.length != size {
        unsafe { Py_DecRef(text) };
        if !unsafe { PyErr_Occurred() }.is_null() {
            return ptr::null_mut();
        }
        return unsafe { new_none() };
    }
    text
}

// ---------------------------------------------------------------------------
// Decoding: a strict JSON parser that builds Python objects directly. Every
// input CPython's decoder treats differently (NaN/Infinity, lone surrogates,
// errors, depth or size limits) declines so CPython reports its own result.

#[derive(Default)]
struct FastHasher(u64);

impl Hasher for FastHasher {
    fn finish(&self) -> u64 {
        self.0
    }

    fn write(&mut self, bytes: &[u8]) {
        let mut hash = self.0 ^ 0xcbf2_9ce4_8422_2325;
        for byte in bytes {
            hash = (hash ^ u64::from(*byte)).wrapping_mul(0x0000_0100_0000_01b3);
        }
        self.0 = hash;
    }
}

// Unsupported syntax and preexisting conversion failures keep their decoder
// fallback. New workspace allocation failures must propagate MemoryError.
#[derive(Copy, Clone)]
enum DecodeFailure { Decline, Allocation }

// Releasing an unattached Python result may invoke allocator callbacks. Keep
// the new workspace allocation exception alive across that early cleanup too.
unsafe fn release_failed_owner(object: *mut PyObject, failure: DecodeFailure) {
    let error = if matches!(failure, DecodeFailure::Allocation) {
        unsafe { ffi::PyErr_GetRaisedException() }
    } else { ptr::null_mut() };
    unsafe { Py_DecRef(object) };
    if matches!(failure, DecodeFailure::Allocation) {
        if error.is_null() { unsafe { PyErr_NoMemory(); } }
        else { unsafe { ffi::PyErr_SetRaisedException(error); } }
    }
}

// Growable scratch storage owns only plain Copy values; Python references are
// owned separately by the parser and memo. Reallocation failure preserves the
// prior allocation and propagates MemoryError after call-local cleanup.
struct Workspace<T: Copy> {
    data: *mut T,
    length: usize,
    capacity: usize,
}

impl<T: Copy> Workspace<T> {
    fn new() -> Self {
        Self { data: ptr::null_mut(), length: 0, capacity: 0 }
    }

    fn len(&self) -> usize { self.length }

    fn reserve(&mut self, additional: usize) -> Result<(), DecodeFailure> {
        let required = self.length.checked_add(additional).ok_or_else(|| { unsafe { PyErr_NoMemory(); } DecodeFailure::Allocation })?;
        if required <= self.capacity { return Ok(()); }
        let capacity = required.max(self.capacity.checked_mul(2).unwrap_or(required)).max(8);
        let bytes = capacity.checked_mul(core::mem::size_of::<T>())
            .filter(|&bytes| bytes <= Py_ssize_t::MAX as usize)
            .ok_or_else(|| { unsafe { PyErr_NoMemory(); } DecodeFailure::Allocation })?;
        let data = unsafe { ffi::PyMem_Realloc(self.data.cast(), bytes) }.cast::<T>();
        if data.is_null() {
            unsafe { PyErr_NoMemory(); }
            return Err(DecodeFailure::Allocation);
        }
        self.data = data;
        self.capacity = capacity;
        Ok(())
    }

    fn push(&mut self, value: T) -> Result<(), DecodeFailure> {
        self.reserve(1)?;
        unsafe { self.data.add(self.length).write(value) };
        self.length += 1;
        Ok(())
    }

    fn extend_from_slice(&mut self, values: &[T]) -> Result<(), DecodeFailure> {
        self.reserve(values.len())?;
        if !values.is_empty() {
            unsafe { ptr::copy_nonoverlapping(values.as_ptr(), self.data.add(self.length), values.len()) };
        }
        self.length += values.len();
        Ok(())
    }

    fn pop(&mut self) -> Option<T> {
        if self.length == 0 { return None; }
        self.length -= 1;
        Some(unsafe { self.data.add(self.length).read() })
    }

    fn clear(&mut self) { self.length = 0; }
    fn truncate(&mut self, length: usize) { self.length = length; }
    fn as_slice(&self) -> &[T] {
        if self.length == 0 { &[] } else { unsafe { slice::from_raw_parts(self.data, self.length) } }
    }
    fn as_ptr(&self) -> *const T { self.data }
}

impl<T: Copy> Drop for Workspace<T> {
    fn drop(&mut self) {
        if !self.data.is_null() { unsafe { PyMem_Free(self.data.cast()) }; }
    }
}

#[derive(Copy, Clone)]
struct KeyEntry<'a> {
    hash: u64,
    bytes: &'a [u8],
    object: *mut PyObject,
}

// Borrowed byte keys are valid for the complete call. Each occupied slot owns
// one Unicode reference; byte equality resolves every hash collision. Rehash
// copies slots without changing ownership and commits only after allocation.
struct KeyMemo<'a> {
    slots: Workspace<Option<KeyEntry<'a>>>,
    length: usize,
}

impl<'a> KeyMemo<'a> {
    fn new() -> Self { Self { slots: Workspace::new(), length: 0 } }

    fn hash(bytes: &[u8]) -> u64 {
        let mut hasher = FastHasher::default();
        bytes.hash(&mut hasher);
        hasher.finish()
    }

    fn get(&self, bytes: &[u8]) -> Option<*mut PyObject> {
        let capacity = self.slots.len();
        if capacity == 0 { return None; }
        let hash = Self::hash(bytes);
        let mut index = hash as usize & (capacity - 1);
        loop {
            match self.slots.as_slice()[index] {
                Some(entry) if entry.hash == hash && entry.bytes == bytes => return Some(entry.object),
                Some(_) => index = (index + 1) & (capacity - 1),
                None => return None,
            }
        }
    }

    fn insert(&mut self, bytes: &'a [u8], object: *mut PyObject) -> Result<(), DecodeFailure> {
        let capacity = self.slots.len();
        if self.length >= capacity / 2 {
            let new_capacity = if capacity == 0 { 8 } else {
                capacity.checked_mul(2).ok_or_else(|| { unsafe { PyErr_NoMemory(); } DecodeFailure::Allocation })?
            };
            let mut slots = Workspace::new();
            slots.reserve(new_capacity)?;
            for _ in 0..new_capacity { slots.push(None)?; }
            for entry in self.slots.as_slice().iter().flatten().copied() {
                Self::place(&mut slots, entry);
            }
            self.slots = slots;
        }
        Self::place(&mut self.slots, KeyEntry { hash: Self::hash(bytes), bytes, object });
        self.length += 1;
        unsafe { Py_IncRef(object) };
        Ok(())
    }

    fn place(slots: &mut Workspace<Option<KeyEntry<'a>>>, entry: KeyEntry<'a>) {
        let mut index = entry.hash as usize & (slots.len() - 1);
        while slots.as_slice()[index].is_some() { index = (index + 1) & (slots.len() - 1); }
        unsafe { slots.data.add(index).write(Some(entry)) };
    }
}

impl Drop for KeyMemo<'_> {
    fn drop(&mut self) {
        for entry in self.slots.as_slice().iter().flatten() {
            unsafe { Py_DecRef(entry.object) };
        }
    }
}

struct Parser<'a> {
    input: &'a [u8],
    position: usize,
    // Owned references not yet attached to a parent; released on failure.
    stack: Workspace<*mut PyObject>,
    keys: KeyMemo<'a>,
    scratch: Workspace<u8>,
}

impl Drop for Parser<'_> {
    fn drop(&mut self) {
        while let Some(object) = self.stack.pop() { unsafe { Py_DecRef(object) }; }
    }
}

impl<'a> Parser<'a> {
    // On failure the new reference has not entered the stack's ownership.
    unsafe fn push_owned(&mut self, object: *mut PyObject) -> Result<(), DecodeFailure> {
        if let Err(error) = self.stack.push(object) {
            unsafe { release_failed_owner(object, error) };
            return Err(error);
        }
        Ok(())
    }

    fn skip_whitespace(&mut self) {
        while let Some(byte) = self.input.get(self.position) {
            if matches!(byte, b' ' | b'\t' | b'\n' | b'\r') {
                self.position += 1;
            } else {
                break;
            }
        }
    }

    fn expect(&mut self, literal: &[u8]) -> Result<(), DecodeFailure> {
        if self.input[self.position..].starts_with(literal) {
            self.position += literal.len();
            Ok(())
        } else {
            Err(DecodeFailure::Decline)
        }
    }

    unsafe fn parse_value(&mut self, depth: usize) -> Result<*mut PyObject, DecodeFailure> {
        if depth > MAX_DEPTH {
            return Err(DecodeFailure::Decline);
        }
        self.skip_whitespace();
        let byte = *self.input.get(self.position).ok_or(DecodeFailure::Decline)?;
        match byte {
            b'"' => {
                let text = unsafe { self.parse_string_object(false) }?;
                Ok(text)
            }
            b'{' => unsafe { self.parse_object(depth) },
            b'[' => unsafe { self.parse_array(depth) },
            b't' => {
                self.expect(b"true")?;
                let value = ptr::addr_of_mut!(_Py_TrueStruct).cast::<PyObject>();
                unsafe { Py_IncRef(value) };
                Ok(value)
            }
            b'f' => {
                self.expect(b"false")?;
                let value = ptr::addr_of_mut!(_Py_FalseStruct).cast::<PyObject>();
                unsafe { Py_IncRef(value) };
                Ok(value)
            }
            b'n' => {
                self.expect(b"null")?;
                Ok(unsafe { new_none() })
            }
            b'-' | b'0'..=b'9' => unsafe { self.parse_number() },
            _ => Err(DecodeFailure::Decline),
        }
    }

    unsafe fn parse_array(&mut self, depth: usize) -> Result<*mut PyObject, DecodeFailure> {
        self.position += 1;
        let base = self.stack.len();
        self.skip_whitespace();
        if self.input.get(self.position) == Some(&b']') {
            self.position += 1;
        } else {
            loop {
                let item = unsafe { self.parse_value(depth + 1) }?;
                unsafe { self.push_owned(item) }?;
                self.skip_whitespace();
                match self.input.get(self.position) {
                    Some(b',') => self.position += 1,
                    Some(b']') => {
                        self.position += 1;
                        break;
                    }
                    _ => return Err(DecodeFailure::Decline),
                }
            }
        }
        let count = self.stack.len() - base;
        let list = unsafe { PyList_New(count as Py_ssize_t) };
        if list.is_null() {
            return Err(DecodeFailure::Decline);
        }
        for index in 0..count {
            let item = self.stack.as_slice()[base + index];
            // PyList_SetItem steals the reference.
            unsafe { PyList_SetItem(list, index as Py_ssize_t, item) };
        }
        self.stack.truncate(base);
        Ok(list)
    }

    unsafe fn parse_object(&mut self, depth: usize) -> Result<*mut PyObject, DecodeFailure> {
        self.position += 1;
        let dict = unsafe { PyDict_New() };
        if dict.is_null() {
            return Err(DecodeFailure::Decline);
        }
        unsafe { self.push_owned(dict) }?;
        self.skip_whitespace();
        if self.input.get(self.position) == Some(&b'}') {
            self.position += 1;
            self.stack.pop();
            return Ok(dict);
        }
        loop {
            self.skip_whitespace();
            if self.input.get(self.position) != Some(&b'"') {
                return Err(DecodeFailure::Decline);
            }
            let key = unsafe { self.parse_string_object(true) }?;
            unsafe { self.push_owned(key) }?;
            self.skip_whitespace();
            if self.input.get(self.position) != Some(&b':') {
                return Err(DecodeFailure::Decline);
            }
            self.position += 1;
            let value = unsafe { self.parse_value(depth + 1) }?;
            let status = unsafe { PyDict_SetItem(dict, key, value) };
            unsafe { Py_DecRef(value) };
            if status != 0 {
                return Err(DecodeFailure::Decline);
            }
            self.stack.pop();
            unsafe { Py_DecRef(key) };
            self.skip_whitespace();
            match self.input.get(self.position) {
                Some(b',') => self.position += 1,
                Some(b'}') => {
                    self.position += 1;
                    break;
                }
                _ => return Err(DecodeFailure::Decline),
            }
        }
        self.stack.pop();
        Ok(dict)
    }

    /// Parse the string at `position` (an opening quote) into a new reference.
    /// Keys without escapes are shared within one document.
    unsafe fn parse_string_object(&mut self, is_key: bool) -> Result<*mut PyObject, DecodeFailure> {
        let input = self.input;
        let start = self.position + 1;
        let mut end = start;
        loop {
            match input.get(end) {
                Some(b'"') => {
                    let text: &'a [u8] = &input[start..end];
                    self.position = end + 1;
                    if !is_key {
                        let object = unsafe { new_unicode(text) };
                        return if object.is_null() { Err(DecodeFailure::Decline) } else { Ok(object) };
                    }
                    if let Some(object) = self.keys.get(text) {
                        unsafe { Py_IncRef(object) };
                        return Ok(object);
                    }
                    let object = unsafe { new_unicode(text) };
                    if object.is_null() {
                        return Err(DecodeFailure::Decline);
                    }
                    if let Err(error) = self.keys.insert(text, object) {
                        unsafe { release_failed_owner(object, error) };
                        return Err(error);
                    }
                    return Ok(object);
                }
                Some(b'\\') => break,
                Some(byte) if *byte < 0x20 => return Err(DecodeFailure::Decline),
                Some(_) => end += 1,
                None => return Err(DecodeFailure::Decline),
            }
        }
        // Slow path: the string contains escapes.
        self.scratch.clear();
        self.scratch.extend_from_slice(&input[start..end])?;
        let mut index = end;
        loop {
            match input.get(index) {
                Some(b'"') => {
                    self.position = index + 1;
                    let object = unsafe { new_unicode(self.scratch.as_slice()) };
                    return if object.is_null() { Err(DecodeFailure::Decline) } else { Ok(object) };
                }
                Some(b'\\') => {
                    index += 1;
                    let escape = *input.get(index).ok_or(DecodeFailure::Decline)?;
                    index += 1;
                    let replacement = match escape {
                        b'"' => b'"',
                        b'\\' => b'\\',
                        b'/' => b'/',
                        b'b' => 0x08,
                        b'f' => 0x0c,
                        b'n' => b'\n',
                        b'r' => b'\r',
                        b't' => b'\t',
                        b'u' => {
                            let mut codepoint = Self::hex4(input, index)?;
                            index += 4;
                            if (0xd800..0xdc00).contains(&codepoint) {
                                if input.get(index) != Some(&b'\\') || input.get(index + 1) != Some(&b'u') {
                                    return Err(DecodeFailure::Decline);
                                }
                                let low = Self::hex4(input, index + 2)?;
                                if !(0xdc00..0xe000).contains(&low) {
                                    return Err(DecodeFailure::Decline);
                                }
                                index += 6;
                                codepoint = 0x1_0000 + ((codepoint - 0xd800) << 10) + (low - 0xdc00);
                            } else if (0xdc00..0xe000).contains(&codepoint) {
                                return Err(DecodeFailure::Decline);
                            }
                            let character = char::from_u32(codepoint).ok_or(DecodeFailure::Decline)?;
                            let mut buffer = [0; 4];
                            self.scratch.extend_from_slice(character.encode_utf8(&mut buffer).as_bytes())?;
                            continue;
                        }
                        _ => return Err(DecodeFailure::Decline),
                    };
                    self.scratch.push(replacement)?;
                }
                Some(byte) if *byte < 0x20 => return Err(DecodeFailure::Decline),
                Some(byte) => {
                    self.scratch.push(*byte)?;
                    index += 1;
                }
                None => return Err(DecodeFailure::Decline),
            }
        }
    }

    fn hex4(input: &[u8], index: usize) -> Result<u32, DecodeFailure> {
        let digits = input.get(index..index + 4).ok_or(DecodeFailure::Decline)?;
        let mut value = 0;
        for digit in digits {
            value = value * 16
                + match digit {
                    b'0'..=b'9' => u32::from(digit - b'0'),
                    b'a'..=b'f' => u32::from(digit - b'a' + 10),
                    b'A'..=b'F' => u32::from(digit - b'A' + 10),
                    _ => return Err(DecodeFailure::Decline),
                };
        }
        Ok(value)
    }

    unsafe fn parse_number(&mut self) -> Result<*mut PyObject, DecodeFailure> {
        let input = self.input;
        let start = self.position;
        let mut index = start;
        if input.get(index) == Some(&b'-') {
            index += 1;
        }
        match input.get(index) {
            Some(b'0') => index += 1,
            Some(b'1'..=b'9') => {
                while matches!(input.get(index), Some(b'0'..=b'9')) {
                    index += 1;
                }
            }
            _ => return Err(DecodeFailure::Decline),
        }
        let integer_end = index;
        let mut is_float = false;
        if input.get(index) == Some(&b'.') {
            index += 1;
            let digits = index;
            while matches!(input.get(index), Some(b'0'..=b'9')) {
                index += 1;
            }
            if index == digits {
                return Err(DecodeFailure::Decline);
            }
            is_float = true;
        }
        if matches!(input.get(index), Some(b'e' | b'E')) {
            index += 1;
            if matches!(input.get(index), Some(b'+' | b'-')) {
                index += 1;
            }
            let digits = index;
            while matches!(input.get(index), Some(b'0'..=b'9')) {
                index += 1;
            }
            if index == digits {
                return Err(DecodeFailure::Decline);
            }
            is_float = true;
        }
        self.position = index;
        let text = &input[start..index];
        let object = if is_float {
            let text = unsafe { core::str::from_utf8_unchecked(text) };
            let value = text.parse::<f64>().map_err(|_| DecodeFailure::Decline)?;
            unsafe { PyFloat_FromDouble(value) }
        } else if integer_end - start <= 18 {
            let negative = text[0] == b'-';
            let mut value: i64 = 0;
            for digit in &text[usize::from(negative)..] {
                value = value * 10 + i64::from(digit - b'0');
            }
            unsafe { PyLong_FromLongLong(if negative { -value } else { value }) }
        } else {
            self.scratch.clear();
            self.scratch.extend_from_slice(text)?;
            self.scratch.push(0)?;
            unsafe { PyLong_FromString(self.scratch.as_ptr().cast::<c_char>(), ptr::null_mut(), 10) }
        };
        if object.is_null() { Err(DecodeFailure::Decline) } else { Ok(object) }
    }
}

unsafe extern "C" fn loads(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"loads() takes exactly one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let mut length = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(*args, &mut length) };
    if data.is_null() {
        // A lone surrogate cannot be represented as UTF-8; let CPython's
        // decoder handle it.
        unsafe { PyErr_Clear() };
        return unsafe { decline() };
    }
    if length < 0 {
        return unsafe { decline() };
    }
    let input = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    let mut parser = Parser {
        input,
        position: 0,
        stack: Workspace::new(),
        keys: KeyMemo::new(),
        scratch: Workspace::new(),
    };
    let mut result = unsafe { parser.parse_value(0) };
    if let Ok(value) = result {
        parser.skip_whitespace();
        if parser.position != input.len() {
            unsafe { Py_DecRef(value) };
            result = Err(DecodeFailure::Decline);
        }
    }
    // Hold the actual allocation exception while reference and buffer cleanup
    // can invoke Python allocator callbacks. Restore it after all owners die.
    let allocation_error = if matches!(result, Err(DecodeFailure::Allocation)) {
        unsafe { ffi::PyErr_GetRaisedException() }
    } else {
        ptr::null_mut()
    };
    drop(parser);
    match result {
        Ok(value) => value,
        Err(DecodeFailure::Allocation) => {
            if allocation_error.is_null() {
                unsafe { PyErr_NoMemory(); }
            } else {
                unsafe { ffi::PyErr_SetRaisedException(allocation_error); }
            }
            ptr::null_mut()
        }
        Err(DecodeFailure::Decline) => {
            // Preexisting syntax/conversion declines retain CPython fallback.
            unsafe { PyErr_Clear() };
            unsafe { decline() }
        }
    }
}

pub extern "C" fn _json_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _json_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _JSON_RS_MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"dumps".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: dumps },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize a supported Python document".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"loads".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: loads },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a complete JSON document".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _JSON_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_json_rs".as_ptr() as *mut _,
        m_doc: c"Rust JSON document codec".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_JSON_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_json_rs_clear),
        m_free: Some(_json_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__json_rs() -> *mut PyObject {
    _JSON_RS_MODULE.init_multi_phase()
}
