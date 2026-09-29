use std::borrow::Cow;
use std::cell::Cell;
use std::collections::HashMap;
use std::ffi::{c_char, c_int, c_void};
use std::hash::{BuildHasherDefault, Hasher};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyDict_GetItemWithError, PyDict_New, PyDict_SetDefaultRef,
    PyDict_SetItem, PyDict_Type, PyErr_Clear, PyErr_ExceptionMatches, PyErr_Occurred,
    PyErr_SetString, PyFloat_FromString, PyImport_ImportModule, PyList_Append, PyList_GetItem,
    PyList_New, PyList_Size, PyList_Type, PyLong_FromLongLong, PyLong_FromString, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyObject, PyObject_CallOneArg,
    PyObject_GetAttrString, PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, Py_DecRef,
    Py_IS_TYPE, Py_ssize_t,
};
use toml_parser::decoder::{Encoding, IntegerRadix, ScalarKind};
use toml_parser::lexer::{Token, TokenKind};
use toml_parser::parser::{EventReceiver, RecursionGuard, ValidateWhitespace, parse_document};
use toml_parser::{ErrorSink, ParseError, Raw, Source, Span};

/// Deepest inline nesting parsed here; deeper documents fall back to Python.
const MAX_DEPTH: u32 = 80;
/// Tokens buffered before parsing the complete statements gathered so far.
const CHUNK_TOKENS: usize = 1024;
/// Longest dotted key handled here; Python reports the recursion-limit error
/// for longer ones.
const MAX_KEY_PARTS: usize = 128;

/// Table declared by a header (or dotted key) and not reopenable by a header.
const EXPLICIT: u8 = 1;
/// Inline table or array: immutable, along with everything inside it.
const FROZEN: u8 = 2;

#[derive(Clone, Copy)]
enum Fail {
    /// The Python parser must handle the document (or raise its error).
    Fallback,
    /// A Python exception is set and must propagate.
    Error,
}

type Built = Result<*mut PyObject, Fail>;

#[derive(Default)]
struct PointerHasher(u64);

impl Hasher for PointerHasher {
    fn finish(&self) -> u64 {
        self.0
    }

    fn write(&mut self, bytes: &[u8]) {
        for byte in bytes {
            self.0 = (self.0 ^ u64::from(*byte)).wrapping_mul(0x0000_0100_0000_01b3);
        }
    }

    fn write_usize(&mut self, value: usize) {
        self.0 = ((value >> 4) as u64).wrapping_mul(0x9e37_79b9_7f4a_7c15);
    }
}

type Flags = HashMap<usize, u8, BuildHasherDefault<PointerHasher>>;

fn check(object: *mut PyObject) -> Built {
    if object.is_null() { Err(Fail::Error) } else { Ok(object) }
}

unsafe fn new_str(text: &str) -> Built {
    check(unsafe {
        PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t)
    })
}

unsafe fn is_dict(object: *mut PyObject) -> bool {
    unsafe { Py_IS_TYPE(object, ptr::addr_of_mut!(PyDict_Type)) != 0 }
}

unsafe fn is_list(object: *mut PyObject) -> bool {
    unsafe { Py_IS_TYPE(object, ptr::addr_of_mut!(PyList_Type)) != 0 }
}

enum FrameKind {
    Array,
    Table,
}

/// An open array or inline table, owning the object under construction.
struct Frame<'i> {
    kind: FrameKind,
    object: *mut PyObject,
    /// Key parts of the pending key/value pair (inline tables only).
    keys: Vec<Cow<'i, str>>,
}

#[derive(Clone, Copy, PartialEq)]
enum Header {
    None,
    Table,
    Array,
}

/// Turns parser events straight into Python objects, applying the table
/// rules of `tomllib`: no redefinition, immutable inline values, and
/// dotted-key tables that a later header cannot reopen.
struct Builder<'i, 'f> {
    input: &'i str,
    stop: &'f Cell<bool>,
    fail: Option<Fail>,
    root: *mut PyObject,
    current: *mut PyObject,
    frames: Vec<Frame<'i>>,
    keys: Vec<Cow<'i, str>>,
    header: Header,
    flags: Flags,
    pending: Vec<*mut PyObject>,
    /// Null when the default `float` is in use.
    parse_float: *mut PyObject,
    datetime: *mut PyObject,
    /// `fromisoformat` of `date`, `time`, and `datetime`, loaded on first use.
    constructors: [*mut PyObject; 3],
}

impl Drop for Builder<'_, '_> {
    fn drop(&mut self) {
        unsafe {
            for frame in &self.frames {
                Py_DecRef(frame.object);
            }
            for constructor in self.constructors {
                if !constructor.is_null() {
                    Py_DecRef(constructor);
                }
            }
            if !self.datetime.is_null() {
                Py_DecRef(self.datetime);
            }
            if !self.root.is_null() {
                Py_DecRef(self.root);
            }
        }
    }
}

impl<'i, 'f> Builder<'i, 'f> {
    fn record<T>(&mut self, result: Result<T, Fail>) -> Option<T> {
        match result {
            Ok(value) => Some(value),
            Err(fail) => {
                self.fail.get_or_insert(fail);
                self.stop.set(true);
                None
            }
        }
    }

    fn syntax_error(&mut self) {
        self.fail.get_or_insert(Fail::Fallback);
        self.stop.set(true);
    }

    fn raw(&self, span: Span, encoding: Option<Encoding>) -> Option<Raw<'i>> {
        let text = self.input.get(span.start()..span.end())?;
        Some(Raw::new_unchecked(text, encoding, span))
    }

    fn top_keys(&mut self) -> &mut Vec<Cow<'i, str>> {
        match self.frames.last_mut() {
            Some(frame) => &mut frame.keys,
            None => &mut self.keys,
        }
    }

    unsafe fn make_float(&self, raw: &str) -> Built {
        let text = unsafe { new_str(raw)? };
        let result = if self.parse_float.is_null() {
            let result = unsafe { PyFloat_FromString(text) };
            if result.is_null() && unsafe { PyErr_ExceptionMatches(cpython_sys::PyExc_ValueError) } != 0 {
                unsafe {
                    PyErr_Clear();
                    Py_DecRef(text);
                }
                return Err(Fail::Fallback);
            }
            result
        } else {
            unsafe { PyObject_CallOneArg(self.parse_float, text) }
        };
        unsafe { Py_DecRef(text) };
        check(result)
    }

    unsafe fn make_integer(&self, digits: &str, radix: IntegerRadix) -> Built {
        if let Ok(value) = i64::from_str_radix(digits, radix.value()) {
            return check(unsafe { PyLong_FromLongLong(value) });
        }
        let mut text = Vec::with_capacity(digits.len() + 1);
        text.extend_from_slice(digits.as_bytes());
        text.push(0);
        check(unsafe {
            PyLong_FromString(text.as_ptr().cast::<c_char>(), ptr::null_mut(), radix.value() as c_int)
        })
    }

    unsafe fn make_datetime(&mut self, decoded: &str, raw: &str) -> Built {
        let Ok(parsed) = decoded.parse::<toml_datetime::Datetime>() else {
            return Err(Fail::Fallback);
        };
        let kind = if parsed.date.is_some() && parsed.time.is_some() {
            2
        } else if parsed.date.is_some() {
            0
        } else {
            1
        };
        if self.constructors[kind].is_null() {
            if self.datetime.is_null() {
                self.datetime = check(unsafe { PyImport_ImportModule(c"datetime".as_ptr()) })?;
            }
            let name = [c"date", c"time", c"datetime"][kind];
            let class = check(unsafe { PyObject_GetAttrString(self.datetime, name.as_ptr()) })?;
            let method = unsafe { PyObject_GetAttrString(class, c"fromisoformat".as_ptr()) };
            unsafe { Py_DecRef(class) };
            self.constructors[kind] = check(method)?;
        }
        let mut text = raw.to_owned();
        if kind == 2 {
            if let Some(index) = text.find('t') {
                text.replace_range(index..=index, "T");
            }
            if text.ends_with(['z', 'Z']) {
                text.truncate(text.len() - 1);
                text.push_str("+00:00");
            }
        }
        let text = unsafe { new_str(&text)? };
        let result = unsafe { PyObject_CallOneArg(self.constructors[kind], text) };
        unsafe { Py_DecRef(text) };
        if result.is_null() {
            if unsafe { PyErr_ExceptionMatches(cpython_sys::PyExc_ValueError) } != 0 {
                unsafe { PyErr_Clear() };
                return Err(Fail::Fallback);
            }
            return Err(Fail::Error);
        }
        Ok(result)
    }

    /// Existing entry of `dict` (borrowed) or null when absent.
    unsafe fn lookup(dict: *mut PyObject, key: &str) -> Result<(*mut PyObject, *mut PyObject), Fail> {
        let key = unsafe { new_str(key)? };
        let found = unsafe { PyDict_GetItemWithError(dict, key) };
        if found.is_null() && !unsafe { PyErr_Occurred() }.is_null() {
            unsafe { Py_DecRef(key) };
            return Err(Fail::Error);
        }
        Ok((key, found))
    }

    /// Add a fresh empty dict under `key` (an owned key object, consumed).
    unsafe fn add_dict(dict: *mut PyObject, key: *mut PyObject) -> Built {
        let child = unsafe { PyDict_New() };
        if child.is_null() {
            unsafe { Py_DecRef(key) };
            return Err(Fail::Error);
        }
        let status = unsafe { PyDict_SetItem(dict, key, child) };
        unsafe { Py_DecRef(key) };
        if status != 0 {
            unsafe { Py_DecRef(child) };
            return Err(Fail::Error);
        }
        // The dict holds the reference now; hand back a borrowed pointer.
        unsafe { Py_DecRef(child) };
        Ok(child)
    }

    fn flags_of(&self, object: *mut PyObject) -> u8 {
        self.flags.get(&(object as usize)).copied().unwrap_or(0)
    }

    fn mark(&mut self, object: *mut PyObject, flag: u8) {
        *self.flags.entry(object as usize).or_insert(0) |= flag;
    }

    /// Store `value` (owned, consumed) at the dotted `keys` below `dict`.
    unsafe fn insert(
        &mut self,
        dict: *mut PyObject,
        keys: &[Cow<'i, str>],
        value: *mut PyObject,
        frozen: bool,
        document: bool,
    ) -> Result<(), Fail> {
        let result = unsafe { self.insert_inner(dict, keys, value, frozen, document) };
        unsafe { Py_DecRef(value) };
        result
    }

    unsafe fn insert_inner(
        &mut self,
        dict: *mut PyObject,
        keys: &[Cow<'i, str>],
        value: *mut PyObject,
        frozen: bool,
        document: bool,
    ) -> Result<(), Fail> {
        let Some((stem, parents)) = keys.split_last() else {
            return Err(Fail::Fallback);
        };
        let mut container = dict;
        for part in parents {
            let (key, found) = unsafe { Self::lookup(container, part)? };
            let next = if found.is_null() {
                unsafe { Self::add_dict(container, key)? }
            } else {
                unsafe { Py_DecRef(key) };
                let flags = self.flags_of(found);
                if flags & FROZEN != 0 || !unsafe { is_dict(found) } {
                    return Err(Fail::Fallback);
                }
                if document && flags & EXPLICIT != 0 {
                    return Err(Fail::Fallback);
                }
                found
            };
            if document {
                self.pending.push(next);
            }
            container = next;
        }
        if frozen {
            self.mark(value, FROZEN);
        }
        let key = unsafe { new_str(stem)? };
        let mut existing = ptr::null_mut();
        let status = unsafe { PyDict_SetDefaultRef(container, key, value, &mut existing) };
        unsafe { Py_DecRef(key) };
        match status {
            0 => {
                unsafe { Py_DecRef(existing) };
                Ok(())
            }
            1 => {
                unsafe { Py_DecRef(existing) };
                Err(Fail::Fallback)
            }
            _ => Err(Fail::Error),
        }
    }

    /// Finish one value: append to the open array, or store under the
    /// pending key of the open inline table or of the current table.
    unsafe fn value_done(&mut self, value: *mut PyObject, frozen: bool) -> Result<(), Fail> {
        match self.frames.last_mut() {
            Some(Frame { kind: FrameKind::Array, object, .. }) => {
                let list = *object;
                let status = unsafe { PyList_Append(list, value) };
                unsafe { Py_DecRef(value) };
                if status != 0 { Err(Fail::Error) } else { Ok(()) }
            }
            Some(Frame { kind: FrameKind::Table, object, keys }) => {
                let dict = *object;
                let keys_taken = std::mem::take(keys);
                let result = unsafe { self.insert(dict, &keys_taken, value, frozen, false) };
                let mut keys_taken = keys_taken;
                keys_taken.clear();
                if let Some(frame) = self.frames.last_mut() {
                    frame.keys = keys_taken;
                }
                result
            }
            None => {
                let keys_taken = std::mem::take(&mut self.keys);
                let current = self.current;
                let result = unsafe { self.insert(current, &keys_taken, value, frozen, true) };
                let mut keys_taken = keys_taken;
                keys_taken.clear();
                self.keys = keys_taken;
                result
            }
        }
    }

    /// Apply a `[table]` or `[[array]]` header to the current-table state.
    unsafe fn apply_header(&mut self, array: bool) -> Result<(), Fail> {
        for object in std::mem::take(&mut self.pending) {
            self.mark(object, EXPLICIT);
        }
        let keys = std::mem::take(&mut self.keys);
        let result = unsafe { self.apply_header_keys(&keys, array) };
        let mut keys = keys;
        keys.clear();
        self.keys = keys;
        result
    }

    unsafe fn apply_header_keys(&mut self, keys: &[Cow<'i, str>], array: bool) -> Result<(), Fail> {
        let Some((stem, parents)) = keys.split_last() else {
            return Err(Fail::Fallback);
        };
        let mut container = self.root;
        for part in parents {
            let (key, found) = unsafe { Self::lookup(container, part)? };
            let mut next = if found.is_null() {
                unsafe { Self::add_dict(container, key)? }
            } else {
                unsafe { Py_DecRef(key) };
                if self.flags_of(found) & FROZEN != 0 {
                    return Err(Fail::Fallback);
                }
                found
            };
            if unsafe { is_list(next) } {
                let size = unsafe { PyList_Size(next) };
                if size <= 0 {
                    return Err(Fail::Fallback);
                }
                next = unsafe { PyList_GetItem(next, size - 1) };
            }
            if next.is_null() || !unsafe { is_dict(next) } {
                return Err(Fail::Fallback);
            }
            container = next;
        }
        let (key, found) = unsafe { Self::lookup(container, stem)? };
        if array {
            let list = if found.is_null() {
                let list = unsafe { PyList_New(0) };
                if list.is_null() {
                    unsafe { Py_DecRef(key) };
                    return Err(Fail::Error);
                }
                let status = unsafe { PyDict_SetItem(container, key, list) };
                unsafe {
                    Py_DecRef(key);
                    Py_DecRef(list);
                }
                if status != 0 {
                    return Err(Fail::Error);
                }
                self.mark(list, EXPLICIT);
                list
            } else {
                unsafe { Py_DecRef(key) };
                if self.flags_of(found) & FROZEN != 0 || !unsafe { is_list(found) } {
                    return Err(Fail::Fallback);
                }
                found
            };
            let element = unsafe { PyDict_New() };
            if element.is_null() {
                return Err(Fail::Error);
            }
            let status = unsafe { PyList_Append(list, element) };
            unsafe { Py_DecRef(element) };
            if status != 0 {
                return Err(Fail::Error);
            }
            self.current = element;
        } else {
            let table = if found.is_null() {
                unsafe { Self::add_dict(container, key)? }
            } else {
                unsafe { Py_DecRef(key) };
                if self.flags_of(found) & (FROZEN | EXPLICIT) != 0 || !unsafe { is_dict(found) } {
                    return Err(Fail::Fallback);
                }
                found
            };
            self.mark(table, EXPLICIT);
            self.current = table;
        }
        Ok(())
    }

    unsafe fn scalar_value(&mut self, span: Span, encoding: Option<Encoding>) -> Result<(), Fail> {
        let raw = self.raw(span, encoding).ok_or(Fail::Fallback)?;
        let mut decoded: Cow<'i, str> = Cow::Borrowed("");
        let mut bad = false;
        let kind = {
            let mut sink = |_error: ParseError| bad = true;
            raw.decode_scalar(&mut decoded, &mut sink)
        };
        if bad {
            return Err(Fail::Fallback);
        }
        let value = match kind {
            ScalarKind::String => unsafe { new_str(&decoded)? },
            ScalarKind::Boolean(value) => check(unsafe { PyBool_FromLong(c_int::from(value).into()) })?,
            ScalarKind::DateTime => unsafe { self.make_datetime(&decoded, raw.as_str())? },
            ScalarKind::Float => unsafe { self.make_float(raw.as_str())? },
            ScalarKind::Integer(radix) => unsafe { self.make_integer(&decoded, radix)? },
        };
        unsafe { self.value_done(value, false) }
    }

    unsafe fn open(&mut self, kind: FrameKind) -> Result<(), Fail> {
        let object = match kind {
            FrameKind::Array => unsafe { PyList_New(0) },
            FrameKind::Table => unsafe { PyDict_New() },
        };
        let object = check(object)?;
        self.frames.push(Frame { kind, object, keys: Vec::new() });
        Ok(())
    }

    unsafe fn close(&mut self) -> Result<(), Fail> {
        let Some(frame) = self.frames.pop() else {
            return Err(Fail::Fallback);
        };
        unsafe { self.value_done(frame.object, true) }
    }
}

macro_rules! guarded {
    ($self:ident, $body:expr) => {
        if $self.stop.get() {
            return;
        }
        let result = $body;
        $self.record(result);
    };
}

impl<'i, 'f> EventReceiver for Builder<'i, 'f> {
    fn std_table_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.header = Header::Table;
    }

    fn std_table_close(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        guarded!(self, unsafe { self.apply_header(false) });
        self.header = Header::None;
    }

    fn array_table_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.header = Header::Array;
    }

    fn array_table_close(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        guarded!(self, unsafe { self.apply_header(true) });
        self.header = Header::None;
    }

    fn inline_table_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) -> bool {
        if !self.stop.get() {
            let result = unsafe { self.open(FrameKind::Table) };
            self.record(result);
        }
        true
    }

    fn inline_table_close(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        guarded!(self, unsafe { self.close() });
    }

    fn array_open(&mut self, _span: Span, _error: &mut dyn ErrorSink) -> bool {
        if !self.stop.get() {
            let result = unsafe { self.open(FrameKind::Array) };
            self.record(result);
        }
        true
    }

    fn array_close(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        guarded!(self, unsafe { self.close() });
    }

    fn simple_key(&mut self, span: Span, encoding: Option<Encoding>, _error: &mut dyn ErrorSink) {
        if self.stop.get() {
            return;
        }
        let Some(raw) = self.raw(span, encoding) else {
            self.syntax_error();
            return;
        };
        let mut key: Cow<'i, str> = Cow::Borrowed("");
        let mut bad = false;
        {
            let mut sink = |_error: ParseError| bad = true;
            raw.decode_key(&mut key, &mut sink);
        }
        if bad {
            self.syntax_error();
            return;
        }
        let keys = self.top_keys();
        keys.push(key);
        if keys.len() > MAX_KEY_PARTS {
            self.syntax_error();
        }
    }

    fn scalar(&mut self, span: Span, encoding: Option<Encoding>, _error: &mut dyn ErrorSink) {
        guarded!(self, unsafe { self.scalar_value(span, encoding) });
    }

    fn error(&mut self, _span: Span, _error: &mut dyn ErrorSink) {
        self.syntax_error();
    }
}

unsafe fn py_none() -> *mut PyObject {
    let none = ptr::addr_of_mut!(cpython_sys::_Py_NoneStruct);
    unsafe { cpython_sys::Py_IncRef(none) };
    none
}

/// Lex and parse in bounded batches of whole statements, so neither the token
/// list nor an intermediate document tree is ever held for the full input.
fn run(source: &str, builder: &mut Builder<'_, '_>, stop: &Cell<bool>) {
    let source = Source::new(source);
    let mut sink = |_error: ParseError| stop.set(true);
    let mut whitespace = ValidateWhitespace::new(builder, source);
    let mut receiver = RecursionGuard::new(&mut whitespace, MAX_DEPTH);
    let mut tokens: Vec<Token> = Vec::with_capacity(CHUNK_TOKENS + 64);
    let mut depth = 0i32;
    for token in source.lex() {
        let kind = token.kind();
        tokens.push(token);
        match kind {
            TokenKind::LeftSquareBracket | TokenKind::LeftCurlyBracket => depth += 1,
            TokenKind::RightSquareBracket | TokenKind::RightCurlyBracket => {
                depth = (depth - 1).max(0);
            }
            TokenKind::Newline if depth == 0 && tokens.len() >= CHUNK_TOKENS => {
                parse_document(&tokens, &mut receiver, &mut sink);
                tokens.clear();
                if stop.get() {
                    return;
                }
            }
            _ => {}
        }
    }
    parse_document(&tokens, &mut receiver, &mut sink);
}

unsafe fn parse_source(source: *mut PyObject, parse_float: *mut PyObject) -> *mut PyObject {
    let mut source_len: Py_ssize_t = 0;
    let source_ptr = unsafe { PyUnicode_AsUTF8AndSize(source, &mut source_len) };
    if source_ptr.is_null() {
        unsafe { PyErr_Clear() };
        return unsafe { py_none() };
    }
    let source_bytes = unsafe {
        std::slice::from_raw_parts(source_ptr.cast::<u8>(), source_len as usize)
    };
    let source = match std::str::from_utf8(source_bytes) {
        Ok(source) => source,
        Err(_) => {
            unsafe {
                PyErr_SetString(
                    cpython_sys::PyExc_RuntimeError,
                    c"CPython returned non-UTF-8 TOML input".as_ptr(),
                );
            }
            return ptr::null_mut();
        }
    };

    let root = unsafe { PyDict_New() };
    if root.is_null() {
        return ptr::null_mut();
    }
    let float_type = ptr::addr_of_mut!(cpython_sys::PyFloat_Type).cast::<PyObject>();
    let stop = Cell::new(false);
    let mut builder = Builder {
        input: source,
        stop: &stop,
        fail: None,
        root,
        current: root,
        frames: Vec::new(),
        keys: Vec::new(),
        header: Header::None,
        flags: Flags::default(),
        pending: Vec::new(),
        parse_float: if parse_float == float_type { ptr::null_mut() } else { parse_float },
        datetime: ptr::null_mut(),
        constructors: [ptr::null_mut(); 3],
    };
    run(source, &mut builder, &stop);
    match builder.fail {
        Some(Fail::Error) => ptr::null_mut(),
        Some(Fail::Fallback) => unsafe { py_none() },
        None if stop.get() || !builder.frames.is_empty() || builder.header != Header::None => unsafe {
            py_none()
        },
        None => std::mem::replace(&mut builder.root, ptr::null_mut()),
    }
}

/// Parse one complete TOML document into Python objects, or return None when
/// the Python parser must handle it. Floats go through `parse_float`.
pub unsafe extern "C" fn loads(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe {
            PyErr_SetString(
                cpython_sys::PyExc_TypeError,
                c"_tomllib_rs.loads() takes exactly two arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }
    unsafe { parse_source(*args, *args.add(1)) }
}

pub extern "C" fn _tomllib_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _tomllib_rs_free(_o: *mut c_void) {}

pub struct ModuleDef {
    ffi: std::cell::UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _TOMLLIB_RS_MODULE_METHODS: [cpython_sys::PyMethodDef; 2] = [
    cpython_sys::PyMethodDef {
        ml_name: c"loads".as_ptr() as *mut c_char,
        ml_meth: cpython_sys::PyMethodDefFuncPointer {
            PyCFunctionFast: loads,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a complete TOML document into Python objects".as_ptr() as *mut c_char,
    },
    cpython_sys::PyMethodDef::zeroed(),
];

pub static _TOMLLIB_RS_MODULE: ModuleDef = ModuleDef {
    ffi: std::cell::UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_tomllib_rs".as_ptr() as *mut _,
        m_doc: c"Rust implementation of complete TOML document parsing".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_TOMLLIB_RS_MODULE_METHODS as *const cpython_sys::PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_tomllib_rs_clear),
        m_free: Some(_tomllib_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__tomllib_rs() -> *mut PyObject {
    _TOMLLIB_RS_MODULE.init_multi_phase()
}
