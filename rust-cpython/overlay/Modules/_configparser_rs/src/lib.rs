//! Rust reading and writing of plain INI files for `configparser`.
//!
//! `read_ini` parses the lines of a file straight into the parser's section
//! dicts, and `write_ini` serializes them straight to `fp.write`. Both take
//! only the simple, unambiguous subset (no continuation lines, no valueless
//! options, no duplicates, standard delimiters); anything else is reported
//! back so the Python implementation handles it and raises its own errors.

use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyDict_Contains;
use cpython_sys::PyDict_New;
use cpython_sys::PyDict_Next;
use cpython_sys::PyDict_SetDefaultRef;
use cpython_sys::PyDict_SetItem;
use cpython_sys::PyDict_Size;
use cpython_sys::PyDict_Type;
use cpython_sys::PyDict_Update;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyList_Append;
use cpython_sys::PyList_New;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyObject;
use cpython_sys::PyObject_CallFunctionObjArgs;
use cpython_sys::PyObject_CallOneArg;
use cpython_sys::PyObject_GetIter;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyIter_Next;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::PyUnicode_InternInPlace;
use cpython_sys::PyUnicode_Type;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_IS_TYPE;
use cpython_sys::Py_NewRef;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;

/// Owned reference, released on drop.
struct Obj(*mut PyObject);

impl Obj {
    fn new(object: *mut PyObject) -> Option<Obj> {
        if object.is_null() { None } else { Some(Obj(object)) }
    }
}

impl Drop for Obj {
    fn drop(&mut self) {
        unsafe { Py_DecRef(self.0) };
    }
}

/// `str.isspace` for one character (CPython's `Py_UNICODE_ISSPACE`).
fn is_space(c: char) -> bool {
    matches!(
        c,
        '\t'..='\r'
            | '\x1c'..='\x1f'
            | ' '
            | '\u{85}'
            | '\u{a0}'
            | '\u{1680}'
            | '\u{2000}'..='\u{200a}'
            | '\u{2028}'
            | '\u{2029}'
            | '\u{202f}'
            | '\u{205f}'
            | '\u{3000}'
    )
}

unsafe fn is_str(object: *mut PyObject) -> bool {
    unsafe { Py_IS_TYPE(object, ptr::addr_of_mut!(PyUnicode_Type)) != 0 }
}

unsafe fn is_dict(object: *mut PyObject) -> bool {
    unsafe { Py_IS_TYPE(object, ptr::addr_of_mut!(PyDict_Type)) != 0 }
}

/// UTF-8 view of a `str`; `None` (error cleared) when it cannot be encoded.
unsafe fn borrow_str<'a>(object: *mut PyObject) -> Option<&'a str> {
    let mut size: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut size) };
    if data.is_null() {
        unsafe { PyErr_Clear() };
        return None;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), size as usize) };
    Some(unsafe { std::str::from_utf8_unchecked(bytes) })
}

unsafe fn new_str(text: &[u8]) -> *mut PyObject {
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), text.len() as Py_ssize_t) }
}

/// Equal names and values share their payload while parser graphs are alive.
/// Mortal interning releases the entry when the last owning reference drops.
unsafe fn new_shared_str(text: &[u8]) -> *mut PyObject {
    let mut object = unsafe { new_str(text) };
    if !object.is_null() {
        unsafe { PyUnicode_InternInPlace(&mut object) };
    }
    object
}

unsafe fn none_result() -> *mut PyObject {
    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

enum Step {
    Next,
    /// The Python parser must handle this file.
    Bail,
    /// A Python exception is set.
    Error,
}

struct Reader {
    /// Interned lowercased option names, shared between sections.
    names: Obj,
    /// Sections seen in this file, in order, each with its options.
    sections: Obj,
    defaults: Option<Obj>,
    /// Options dict of the section being read (borrowed from the above).
    current: *mut PyObject,
    /// Every consumed line, each preceded by its length, for the fallback.
    raw: Vec<u8>,
    scratch: Vec<u8>,
}

impl Reader {
    unsafe fn line(
        &mut self,
        text: &str,
        default_section: &str,
        parser_sections: *mut PyObject,
        lower: *mut PyObject,
    ) -> Step {
        let trimmed = text.trim_matches(is_space);
        if trimmed.is_empty() || trimmed.starts_with(['#', ';']) {
            return Step::Next;
        }
        if text.starts_with(is_space) {
            return Step::Bail;
        }
        if trimmed.starts_with('[') {
            return unsafe { self.header(trimmed, default_section, parser_sections) };
        }
        if self.current.is_null() {
            return Step::Bail;
        }
        unsafe { self.option(trimmed, lower) }
    }

    unsafe fn header(
        &mut self,
        trimmed: &str,
        default_section: &str,
        parser_sections: *mut PyObject,
    ) -> Step {
        let bytes = trimmed.as_bytes();
        if bytes.len() < 3
            || bytes[bytes.len() - 1] != b']'
            || bytes[1..].iter().filter(|&&b| b == b']').count() != 1
        {
            return Step::Bail;
        }
        let name = &trimmed[1..trimmed.len() - 1];
        if name.starts_with(is_space) || name.ends_with(is_space) {
            return Step::Bail;
        }
        let Some(name_object) = Obj::new(unsafe { new_shared_str(name.as_bytes()) }) else {
            return Step::Error;
        };
        let known = unsafe { PyDict_Contains(parser_sections, name_object.0) };
        if known < 0 {
            return Step::Error;
        }
        if known == 0 && name == default_section {
            let defaults = match &self.defaults {
                Some(defaults) => defaults.0,
                None => {
                    let Some(created) = Obj::new(unsafe { PyDict_New() }) else {
                        return Step::Error;
                    };
                    let pointer = created.0;
                    self.defaults = Some(created);
                    pointer
                }
            };
            self.current = defaults;
            return Step::Next;
        }
        let Some(options) = Obj::new(unsafe { PyDict_New() }) else {
            return Step::Error;
        };
        let mut existing = ptr::null_mut();
        let status = unsafe {
            PyDict_SetDefaultRef(self.sections.0, name_object.0, options.0, &mut existing)
        };
        match status {
            0 => {
                unsafe { Py_DecRef(existing) };
                self.current = options.0;
                Step::Next
            }
            1 => {
                unsafe { Py_DecRef(existing) };
                Step::Bail
            }
            _ => Step::Error,
        }
    }

    unsafe fn option(&mut self, trimmed: &str, lower: *mut PyObject) -> Step {
        let Some(at) = trimmed.find(['=', ':']) else {
            return Step::Bail;
        };
        let name = trimmed[..at].trim_end_matches(is_space);
        if name.is_empty() {
            return Step::Bail;
        }
        let value = trimmed[at + 1..].trim_matches(is_space);

        let name_object = if name.is_ascii() {
            self.scratch.clear();
            self.scratch.extend(name.bytes().map(|b| b.to_ascii_lowercase()));
            unsafe { new_str(&self.scratch) }
        } else {
            let Some(raw) = Obj::new(unsafe { new_str(name.as_bytes()) }) else {
                return Step::Error;
            };
            unsafe { PyObject_CallOneArg(lower, raw.0) }
        };
        let Some(name_object) = Obj::new(name_object) else {
            return Step::Error;
        };
        let mut shared = ptr::null_mut();
        if unsafe { PyDict_SetDefaultRef(self.names.0, name_object.0, name_object.0, &mut shared) }
            < 0
        {
            return Step::Error;
        }
        let Some(shared) = Obj::new(shared) else {
            return Step::Error;
        };
        let Some(value_object) = Obj::new(unsafe { new_shared_str(value.as_bytes()) }) else {
            return Step::Error;
        };
        let mut existing = ptr::null_mut();
        match unsafe { PyDict_SetDefaultRef(self.current, shared.0, value_object.0, &mut existing) }
        {
            0 => {
                unsafe { Py_DecRef(existing) };
                Step::Next
            }
            1 => {
                unsafe { Py_DecRef(existing) };
                Step::Bail
            }
            _ => Step::Error,
        }
    }

    fn remember(&mut self, text: &str) {
        self.raw.extend_from_slice(&(text.len() as u32).to_ne_bytes());
        self.raw.extend_from_slice(text.as_bytes());
    }
}

/// Every line in `raw` plus `current` plus the rest of `lines`, as a list.
unsafe fn fallback(raw: &[u8], current: *mut PyObject, lines: *mut PyObject) -> *mut PyObject {
    let Some(list) = Obj::new(unsafe { PyList_New(0) }) else {
        return ptr::null_mut();
    };
    let mut at = 0;
    while at < raw.len() {
        let size = u32::from_ne_bytes(raw[at..at + 4].try_into().unwrap()) as usize;
        at += 4;
        let Some(line) = Obj::new(unsafe { new_str(&raw[at..at + size]) }) else {
            return ptr::null_mut();
        };
        at += size;
        if unsafe { PyList_Append(list.0, line.0) } < 0 {
            return ptr::null_mut();
        }
    }
    if !current.is_null() && unsafe { PyList_Append(list.0, current) } < 0 {
        return ptr::null_mut();
    }
    loop {
        let line = unsafe { PyIter_Next(lines) };
        if line.is_null() {
            if unsafe { PyErr_Occurred() }.is_null() {
                break;
            }
            return ptr::null_mut();
        }
        let line = Obj(line);
        if unsafe { PyList_Append(list.0, line.0) } < 0 {
            return ptr::null_mut();
        }
    }
    let result = list.0;
    std::mem::forget(list);
    result
}

/// Merge the sections read into the parser's own dicts.
unsafe fn commit(
    reader: &Reader,
    parser: *mut PyObject,
    parser_sections: *mut PyObject,
    proxies: *mut PyObject,
    defaults: *mut PyObject,
    make_proxy: *mut PyObject,
) -> bool {
    if let Some(read) = &reader.defaults {
        if unsafe { PyDict_Update(defaults, read.0) } < 0 {
            return false;
        }
    }
    let mut position: Py_ssize_t = 0;
    let mut name = ptr::null_mut();
    let mut options = ptr::null_mut();
    while unsafe { PyDict_Next(reader.sections.0, &mut position, &mut name, &mut options) } != 0 {
        let existing = unsafe { PyDict_Contains(parser_sections, name) };
        if existing < 0 {
            return false;
        }
        if existing == 1 {
            let target = unsafe { cpython_sys::PyDict_GetItemWithError(parser_sections, name) };
            if target.is_null() || unsafe { PyDict_Update(target, options) } < 0 {
                return false;
            }
            continue;
        }
        if unsafe { PyDict_SetItem(parser_sections, name, options) } < 0 {
            return false;
        }
        let proxy = unsafe {
            PyObject_CallFunctionObjArgs(make_proxy, parser, name, ptr::null_mut::<PyObject>())
        };
        let Some(proxy) = Obj::new(proxy) else {
            return false;
        };
        if unsafe { PyDict_SetItem(proxies, name, proxy.0) } < 0 {
            return false;
        }
    }
    true
}

unsafe fn type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

/// read_ini(fp, default_section, sections, proxies, defaults, make_proxy,
/// parser, lower): parse `fp` into the parser; returns `None` when done or a
/// list of every line of `fp` when the Python parser must read them instead.
unsafe extern "C" fn read_ini(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 8 {
        return unsafe { type_error(c"read_ini() takes exactly eight arguments") };
    }
    let arg = |index: usize| unsafe { *args.add(index) };
    let (fp, default_object) = (arg(0), arg(1));
    let (parser_sections, proxies, defaults) = (arg(2), arg(3), arg(4));
    let (make_proxy, parser, lower) = (arg(5), arg(6), arg(7));
    unsafe {
        if !is_str(default_object)
            || !is_dict(parser_sections)
            || !is_dict(proxies)
            || !is_dict(defaults)
        {
            return type_error(c"read_ini() got an argument of the wrong type");
        }
    }
    let Some(lines) = Obj::new(unsafe { PyObject_GetIter(fp) }) else {
        return ptr::null_mut();
    };
    let Some(default_section) = (unsafe { borrow_str(default_object) }) else {
        return unsafe { fallback(&[], ptr::null_mut(), lines.0) };
    };
    let (Some(names), Some(sections)) = (
        Obj::new(unsafe { PyDict_New() }),
        Obj::new(unsafe { PyDict_New() }),
    ) else {
        return ptr::null_mut();
    };
    let mut reader = Reader {
        names,
        sections,
        defaults: None,
        current: ptr::null_mut(),
        raw: Vec::with_capacity(16384),
        scratch: Vec::with_capacity(64),
    };

    loop {
        let item = unsafe { PyIter_Next(lines.0) };
        if item.is_null() {
            if unsafe { PyErr_Occurred() }.is_null() {
                break;
            }
            return ptr::null_mut();
        }
        let item = Obj(item);
        let step = if unsafe { is_str(item.0) } {
            match unsafe { borrow_str(item.0) } {
                Some(text) => {
                    let step =
                        unsafe { reader.line(text, default_section, parser_sections, lower) };
                    if matches!(step, Step::Next) {
                        reader.remember(text);
                    }
                    step
                }
                None => Step::Bail,
            }
        } else {
            Step::Bail
        };
        match step {
            Step::Next => {}
            Step::Bail => return unsafe { fallback(&reader.raw, item.0, lines.0) },
            Step::Error => return ptr::null_mut(),
        }
    }

    if !unsafe { commit(&reader, parser, parser_sections, proxies, defaults, make_proxy) } {
        return ptr::null_mut();
    }
    unsafe { none_result() }
}

/// One option value as written by `RawConfigParser._write_section`: every
/// line ending becomes a newline followed by a tab.
fn push_value(out: &mut Vec<u8>, value: &str) {
    let bytes = value.as_bytes();
    let mut at = 0;
    while at < bytes.len() {
        match bytes[at] {
            b'\r' => {
                out.extend_from_slice(b"\n\t");
                if bytes.get(at + 1) == Some(&b'\n') {
                    at += 1;
                }
            }
            b'\n' => out.extend_from_slice(b"\n\t"),
            byte => out.push(byte),
        }
        at += 1;
    }
}

/// Section text as `str` pieces are flushed to `write` at this size.
const FLUSH_BYTES: usize = 4096;

unsafe fn flush(out: &mut Vec<u8>, write: *mut PyObject) -> bool {
    let Some(piece) = Obj::new(unsafe { new_str(out) }) else {
        return false;
    };
    out.clear();
    let Some(_result) = Obj::new(unsafe { PyObject_CallOneArg(write, piece.0) }) else {
        return false;
    };
    true
}

/// Every key and value of the options dict is an encodable `str` (or `None`
/// for a value) that `_write_section` would write as-is.
unsafe fn writable(options: *mut PyObject) -> bool {
    let mut position: Py_ssize_t = 0;
    let mut key = ptr::null_mut();
    let mut value = ptr::null_mut();
    while unsafe { PyDict_Next(options, &mut position, &mut key, &mut value) } != 0 {
        if !unsafe { is_str(key) } {
            return false;
        }
        let Some(key) = (unsafe { borrow_str(key) }) else {
            return false;
        };
        if key.starts_with('[') || key.contains(['=', ':']) {
            return false;
        }
        let none = ptr::addr_of_mut!(_Py_NoneStruct);
        if value != none
            && !(unsafe { is_str(value) } && unsafe { borrow_str(value) }.is_some())
        {
            return false;
        }
    }
    true
}

unsafe fn write_section(
    out: &mut Vec<u8>,
    name: &str,
    options: *mut PyObject,
    delimiter: &[u8],
    write: *mut PyObject,
) -> bool {
    out.push(b'[');
    out.extend_from_slice(name.as_bytes());
    out.extend_from_slice(b"]\n");
    let mut position: Py_ssize_t = 0;
    let mut key = ptr::null_mut();
    let mut value = ptr::null_mut();
    while unsafe { PyDict_Next(options, &mut position, &mut key, &mut value) } != 0 {
        let key = unsafe { borrow_str(key) }.unwrap_or("");
        out.extend_from_slice(key.as_bytes());
        out.extend_from_slice(delimiter);
        if unsafe { is_str(value) } {
            push_value(out, unsafe { borrow_str(value) }.unwrap_or(""));
        } else {
            out.extend_from_slice(b"None");
        }
        out.push(b'\n');
    }
    out.push(b'\n');
    out.len() < FLUSH_BYTES || unsafe { flush(out, write) }
}

/// write_ini(write, defaults, sections, default_section, spaced): write the
/// parser's sections through `write`; returns False, having written nothing,
/// when the Python writer must do it.
unsafe extern "C" fn write_ini(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 5 {
        return unsafe { type_error(c"write_ini() takes exactly five arguments") };
    }
    let arg = |index: usize| unsafe { *args.add(index) };
    let (write, defaults, sections) = (arg(0), arg(1), arg(2));
    let (default_object, spaced) = (arg(3), arg(4));
    unsafe {
        if !is_dict(defaults) || !is_dict(sections) || !is_str(default_object) {
            return type_error(c"write_ini() got an argument of the wrong type");
        }
    }
    let refuse = || unsafe { PyBool_FromLong(0) };
    let Some(default_section) = (unsafe { borrow_str(default_object) }) else {
        return refuse();
    };

    if !unsafe { writable(defaults) } {
        return refuse();
    }
    let mut position: Py_ssize_t = 0;
    let mut name = ptr::null_mut();
    let mut options = ptr::null_mut();
    while unsafe { PyDict_Next(sections, &mut position, &mut name, &mut options) } != 0 {
        if !unsafe { is_str(name) && borrow_str(name).is_some() && is_dict(options) && writable(options) }
        {
            return refuse();
        }
    }

    let spaced = unsafe { PyObject_IsTrue(spaced) };
    if spaced < 0 {
        return ptr::null_mut();
    }
    let delimiter: &[u8] = if spaced > 0 { b" = " } else { b"=" };
    let mut out: Vec<u8> = Vec::with_capacity(FLUSH_BYTES + 1024);
    if unsafe { PyDict_Size(defaults) } > 0
        && !unsafe { write_section(&mut out, default_section, defaults, delimiter, write) }
    {
        return ptr::null_mut();
    }
    position = 0;
    while unsafe { PyDict_Next(sections, &mut position, &mut name, &mut options) } != 0 {
        let section = unsafe { borrow_str(name) }.unwrap_or("");
        if !unsafe { write_section(&mut out, section, options, delimiter, write) } {
            return ptr::null_mut();
        }
    }
    if !out.is_empty() && !unsafe { flush(&mut out, write) } {
        return ptr::null_mut();
    }
    unsafe { PyBool_FromLong(1) }
}

pub extern "C" fn _configparser_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _configparser_rs_free(_obj: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: usize = 2;

struct ModuleSlots(UnsafeCell<[PyModuleDef_Slot; 2]>);

unsafe impl Sync for ModuleSlots {}

// The module retains no Python references or mutable process state. Mortal
// intern entries belong to the current interpreter and end with their owners.
static MODULE_SLOTS: ModuleSlots = ModuleSlots(UnsafeCell::new([
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]));

pub static _CONFIGPARSER_RS_MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"read_ini".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: read_ini,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Parse a simple INI file into a parser".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"write_ini".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: write_ini,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Serialize a parser's sections as INI text".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _CONFIGPARSER_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_configparser_rs".as_ptr() as *mut _,
        m_doc: c"Rust INI parsing and serialization".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_CONFIGPARSER_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: MODULE_SLOTS.0.get().cast(),
        m_traverse: None,
        m_clear: Some(_configparser_rs_clear),
        m_free: Some(_configparser_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__configparser_rs() -> *mut PyObject {
    _CONFIGPARSER_RS_MODULE.init_multi_phase()
}
