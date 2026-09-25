use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyLong_AsSsize_t;
use cpython_sys::PyLong_FromSsize_t;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyUnicode_FromString;
use cpython_sys::PyUnicode_GetLength;
use cpython_sys::PyUnicode_ReadChar;
use cpython_sys::Py_ssize_t;

const NONE: u32 = u32::MAX;

struct Input {
    object: *mut PyObject,
    length: usize,
}

impl Input {
    unsafe fn new(object: *mut PyObject) -> Option<Self> {
        let length = unsafe { PyUnicode_GetLength(object) };
        if length < 0 {
            return None;
        }
        Some(Self {
            object,
            length: length as usize,
        })
    }

    unsafe fn at(&self, index: usize) -> u32 {
        if index >= self.length {
            NONE
        } else {
            unsafe { PyUnicode_ReadChar(self.object, index as Py_ssize_t) }
        }
    }

    unsafe fn matches(&self, start: usize, value: &[u8]) -> bool {
        value.iter().enumerate().all(|(offset, byte)| unsafe {
            self.at(start + offset) == u32::from(*byte)
        })
    }

    unsafe fn matches_ascii_case_insensitive(&self, start: usize, value: &[u8]) -> bool {
        value.iter().enumerate().all(|(offset, byte)| unsafe {
            let actual = self.at(start + offset);
            if actual > 0x7f {
                return false;
            }
            let actual = actual as u8;
            actual.eq_ignore_ascii_case(byte)
        })
    }

    unsafe fn find_char(&self, start: usize, value: u32) -> Option<usize> {
        let mut index = start;
        while index < self.length {
            if unsafe { self.at(index) } == value {
                return Some(index);
            }
            index += 1;
        }
        None
    }

    unsafe fn find_ascii_sequence(&self, start: usize, value: &[u8]) -> Option<usize> {
        if value.is_empty() {
            return Some(start);
        }
        let last_start = self.length.saturating_sub(value.len());
        let mut index = start;
        while index <= last_start {
            if unsafe { self.matches(index, value) } {
                return Some(index);
            }
            index += 1;
        }
        None
    }
}

fn is_ascii_alpha(ch: u32) -> bool {
    (b'A' as u32..=b'Z' as u32).contains(&ch) || (b'a' as u32..=b'z' as u32).contains(&ch)
}

fn is_ascii_digit(ch: u32) -> bool {
    (b'0' as u32..=b'9' as u32).contains(&ch)
}

fn is_hex_digit(ch: u32) -> bool {
    is_ascii_digit(ch)
        || (b'A' as u32..=b'F' as u32).contains(&ch)
        || (b'a' as u32..=b'f' as u32).contains(&ch)
}

fn is_space(ch: u32) -> bool {
    matches!(ch, 0x09 | 0x0a | 0x0c | 0x0d | 0x20)
}

fn is_name_separator(ch: u32) -> bool {
    is_space(ch) || ch == b'/' as u32 || ch == b'>' as u32
}

unsafe fn find_tag_end(input: &Input, mut index: usize) -> Option<usize> {
    let length = input.length;
    let mut attribute_separator = false;

    while index < length && !is_name_separator(unsafe { input.at(index) }) {
        index += 1;
    }

    loop {
        let separator_start = index;
        while index < length && (is_space(unsafe { input.at(index) }) || unsafe { input.at(index) } == b'/' as u32) {
            index += 1;
        }
        if index >= length {
            return None;
        }

        let current = unsafe { input.at(index) };
        if current == b'>' as u32 {
            return Some(index + 1);
        }
        if index == separator_start
            && !attribute_separator
            && unsafe { input.at(index - 1) } != b'\'' as u32
            && unsafe { input.at(index - 1) } != b'"' as u32
        {
            return None;
        }
        attribute_separator = false;

        // Attribute names may start immediately after a quoted value. Their
        // first character can be '=' or a quote, while later characters stop
        // at whitespace, slash, equals, or the tag close.
        if current == b'=' as u32 {
            index += 1;
        }
        while index < length {
            let ch = unsafe { input.at(index) };
            if is_space(ch)
                || ch == b'/' as u32
                || ch == b'=' as u32
                || ch == b'>' as u32
            {
                break;
            }
            index += 1;
        }

        let mut whitespace_after_name = false;
        while index < length && is_space(unsafe { input.at(index) }) {
            index += 1;
            whitespace_after_name = true;
        }
        if index < length && unsafe { input.at(index) } == b'=' as u32 {
            index += 1;
            while index < length && is_space(unsafe { input.at(index) }) {
                index += 1;
            }
            if index < length {
                let quote = unsafe { input.at(index) };
                if quote == b'\'' as u32 || quote == b'"' as u32 {
                    index += 1;
                    while index < length && unsafe { input.at(index) } != quote {
                        index += 1;
                    }
                    if index == length {
                        return None;
                    }
                    index += 1;
                } else {
                    while index < length {
                        let ch = unsafe { input.at(index) };
                        if is_space(ch) || ch == b'>' as u32 {
                            break;
                        }
                        index += 1;
                    }
                }
            } else {
                return None;
            }
        } else {
            attribute_separator = whitespace_after_name;
        }
    }
}

unsafe fn find_comment_end(input: &Input, start: usize) -> Option<usize> {
    let length = input.length;
    if start < length && unsafe { input.at(start) } == b'>' as u32 {
        return Some(start + 1);
    }
    if start + 1 < length
        && unsafe { input.at(start) } == b'-' as u32
        && unsafe { input.at(start + 1) } == b'>' as u32
    {
        return Some(start + 2);
    }

    let mut index = start;
    while index + 1 < length {
        if unsafe { input.matches(index, b"--") } {
            let mut close = index + 2;
            if close < length && unsafe { input.at(close) } == b'!' as u32 {
                close += 1;
            }
            if close < length && unsafe { input.at(close) } == b'>' as u32 {
                return Some(close + 1);
            }
        }
        index += 1;
    }
    None
}

unsafe fn cdata_close_at(input: &Input, index: usize, element: *mut PyObject) -> bool {
    let element_length = unsafe { PyUnicode_GetLength(element) };
    if element_length <= 0 || !unsafe { input.matches(index, b"</") } {
        return false;
    }
    let element_length = element_length as usize;
    for offset in 0..element_length {
        let expected = unsafe { PyUnicode_ReadChar(element, offset as Py_ssize_t) };
        let actual = unsafe { input.at(index + 2 + offset) };
        if expected > 0x7f || actual > 0x7f {
            if expected != actual {
                return false;
            }
        } else if !(expected as u8).eq_ignore_ascii_case(&(actual as u8)) {
            return false;
        }
    }
    is_space(unsafe { input.at(index + 2 + element_length) })
        || unsafe { input.at(index + 2 + element_length) } == b'/' as u32
        || unsafe { input.at(index + 2 + element_length) } == b'>' as u32
}

unsafe fn next_interesting(
    input: &Input,
    start: usize,
    convert_charrefs: bool,
    cdata_element: *mut PyObject,
    cdata_active: bool,
    escapable: bool,
) -> Option<usize> {
    if !cdata_active {
        if convert_charrefs {
            return unsafe { input.find_char(start, b'<' as u32) };
        }
        let open = unsafe { input.find_char(start, b'<' as u32) };
        let amp = unsafe { input.find_char(start, b'&' as u32) };
        return match (open, amp) {
            (Some(left), Some(right)) => Some(left.min(right)),
            (Some(index), None) | (None, Some(index)) => Some(index),
            (None, None) => None,
        };
    }

    let name_length = unsafe { PyUnicode_GetLength(cdata_element) };
    let plaintext = name_length == 9
        && (0..9).all(|offset| unsafe {
            PyUnicode_ReadChar(cdata_element, offset as Py_ssize_t)
                == b"plaintext"[offset] as u32
        });
    if plaintext {
        return None;
    }
    let mut close = None;
    let mut index = start;
    while index + 2 < input.length {
        if unsafe { cdata_close_at(input, index, cdata_element) } {
            close = Some(index);
            break;
        }
        index += 1;
    }
    let amp = if escapable && !convert_charrefs {
        unsafe { input.find_char(start, b'&' as u32) }
    } else {
        None
    };
    match (close, amp) {
        (Some(left), Some(right)) => Some(left.min(right)),
        (Some(index), None) | (None, Some(index)) => Some(index),
        (None, None) => None,
    }
}

unsafe fn is_incomplete_charref(input: &Input, start: usize) -> bool {
    if unsafe { input.at(start) } != b'&' as u32
        || unsafe { input.at(start + 1) } != b'#' as u32
    {
        return false;
    }
    let first = unsafe { input.at(start + 2) };
    if is_ascii_digit(first) {
        return true;
    }
    (first == b'x' as u32 || first == b'X' as u32)
        && is_hex_digit(unsafe { input.at(start + 3) })
}

unsafe fn entityref_end(input: &Input, start: usize) -> Option<usize> {
    if unsafe { input.at(start) } != b'&' as u32 || !is_ascii_alpha(unsafe { input.at(start + 1) }) {
        return None;
    }
    let mut index = start + 2;
    while index < input.length {
        let ch = unsafe { input.at(index) };
        if is_ascii_alpha(ch)
            || is_ascii_digit(ch)
            || ch == b'-' as u32
            || ch == b'.' as u32
        {
            index += 1;
        } else {
            return Some(if ch == b';' as u32 { index + 1 } else { index });
        }
    }
    None
}

unsafe fn charref_end(input: &Input, start: usize) -> Option<usize> {
    if unsafe { input.at(start) } != b'&' as u32 || unsafe { input.at(start + 1) } != b'#' as u32 {
        return None;
    }
    let mut index = start + 2;
    let first = unsafe { input.at(index) };
    if is_ascii_digit(first) {
        while is_ascii_digit(unsafe { input.at(index) }) {
            index += 1;
        }
    } else if first == b'x' as u32 || first == b'X' as u32 {
        index += 1;
        if !is_hex_digit(unsafe { input.at(index) }) {
            return None;
        }
        while is_hex_digit(unsafe { input.at(index) }) {
            index += 1;
        }
    } else {
        return None;
    }
    let trailing = unsafe { input.at(index) };
    if trailing == NONE || is_hex_digit(trailing) {
        None
    } else {
        Some(if trailing == b';' as u32 { index + 1 } else { index })
    }
}

unsafe fn next_token(
    input: &Input,
    start: usize,
    end: bool,
    convert_charrefs: bool,
    cdata_element: *mut PyObject,
    escapable: bool,
    support_cdata: bool,
) -> (&'static std::ffi::CStr, usize) {
    if start >= input.length {
        return (c"eof", start);
    }

    let cdata_active = unsafe { PyObject_IsTrue(cdata_element) } == 1;
    let mut marker = unsafe {
        next_interesting(
            input,
            start,
            convert_charrefs,
            cdata_element,
            cdata_active,
            escapable,
        )
    };
    if !cdata_active && convert_charrefs && marker.is_none() {
        let lookbehind = start.max(input.length.saturating_sub(34));
        let amp = unsafe {
            let mut found = None;
            let mut index = lookbehind;
            while index < input.length {
                if input.at(index) == b'&' as u32 {
                    found = Some(index);
                }
                index += 1;
            }
            found
        };
        if let Some(amp) = amp {
            let mut has_terminator = false;
            let mut index = amp;
            while index < input.length {
                let ch = unsafe { input.at(index) };
                if is_space(ch) || ch == b';' as u32 {
                    has_terminator = true;
                    break;
                }
                index += 1;
            }
            if !has_terminator {
                return if end {
                    (c"data", input.length)
                } else {
                    (c"incomplete", start)
                };
            }
        }
    }
    if marker.is_none() {
        if cdata_active && !end {
            return (c"incomplete", start);
        }
        marker = Some(input.length);
    }
    let marker = marker.unwrap();
    if marker > start {
        return (c"data", marker);
    }

    let current = unsafe { input.at(start) };
    if current == b'<' as u32 {
        if start + 1 < input.length && is_ascii_alpha(unsafe { input.at(start + 1) }) {
            return match unsafe { find_tag_end(input, start + 2) } {
                Some(token_end) => (c"starttag", token_end),
                None => (c"incomplete", start),
            };
        }
        if start + 1 < input.length && unsafe { input.at(start + 1) } == b'/' as u32 {
            if start + 2 < input.length && unsafe { input.at(start + 2) } == b'>' as u32 {
                return (c"ignored", start + 3);
            }
            if start + 2 < input.length && is_ascii_alpha(unsafe { input.at(start + 2) }) {
                return match unsafe { find_tag_end(input, start + 3) } {
                    Some(token_end) => (c"endtag", token_end),
                    None => (c"incomplete", start),
                };
            }
            return match unsafe { input.find_char(start + 2, b'>' as u32) } {
                Some(close) => (c"endtag", close + 1),
                None => (c"incomplete", start),
            };
        }
        if unsafe { input.matches(start, b"<!--") } {
            return match unsafe { find_comment_end(input, start + 4) } {
                Some(token_end) => (c"comment", token_end),
                None => (c"incomplete", start),
            };
        }
        if unsafe { input.matches(start, b"<?") } {
            return match unsafe { input.find_char(start + 2, b'>' as u32) } {
                Some(close) => (c"pi", close + 1),
                None => (c"incomplete", start),
            };
        }
        if unsafe { input.matches(start, b"<!") } {
            if support_cdata && unsafe { input.matches(start, b"<![CDATA[") } {
                return match unsafe { input.find_ascii_sequence(start + 9, b"]]>") } {
                    Some(close) => (c"declaration", close + 3),
                    None => (c"incomplete", start),
                };
            }
            if unsafe { input.matches_ascii_case_insensitive(start, b"<!doctype") } {
                return match unsafe { input.find_char(start + 9, b'>' as u32) } {
                    Some(close) => (c"declaration", close + 1),
                    None => (c"incomplete", start),
                };
            }
            return match unsafe { input.find_char(start + 2, b'>' as u32) } {
                Some(close) => (c"declaration", close + 1),
                None => (c"incomplete", start),
            };
        }
        if start + 1 < input.length || end {
            return (c"data", start + 1);
        }
        return (c"incomplete", start);
    }

    if current == b'&' as u32 && (!cdata_active || (escapable && !convert_charrefs)) {
        if unsafe { input.matches(start, b"&#") } {
            if let Some(token_end) = unsafe { charref_end(input, start) } {
                return (c"charref", token_end);
            }
            if unsafe { is_incomplete_charref(input, start) } {
                return if end {
                    (c"incomplete_charref", input.length)
                } else {
                    (c"incomplete", start)
                };
            }
            if input.length > start + 3 {
                return (c"data", start + 2);
            }
            return if end {
                (c"data", input.length)
            } else {
                (c"incomplete", start)
            };
        }
        if let Some(token_end) = unsafe { entityref_end(input, start) } {
            return (c"entityref", token_end);
        }
        if start + 1 < input.length && is_ascii_alpha(unsafe { input.at(start + 1) }) {
            return if end {
                (c"entityref", input.length)
            } else {
                (c"incomplete", start)
            };
        }
        if start + 1 < input.length {
            return (c"data", start + 1);
        }
        return if end {
            (c"data", input.length)
        } else {
            (c"incomplete", start)
        };
    }

    (c"data", (marker + 1).min(input.length))
}

unsafe fn read_bool(object: *mut PyObject) -> Option<bool> {
    let value = unsafe { PyObject_IsTrue(object) };
    if value < 0 {
        None
    } else {
        Some(value != 0)
    }
}

unsafe fn read_index(object: *mut PyObject) -> Option<usize> {
    let value = unsafe { PyLong_AsSsize_t(object) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return None;
    }
    if value < 0 {
        unsafe { PyErr_SetString(PyExc_ValueError, c"token offset must be nonnegative".as_ptr()) };
        return None;
    }
    Some(value as usize)
}

unsafe fn token_result(kind: &'static std::ffi::CStr, end: usize) -> *mut PyObject {
    if end > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    let tuple = unsafe { PyTuple_New(2) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    let kind = unsafe { PyUnicode_FromString(kind.as_ptr()) };
    let position = unsafe { PyLong_FromSsize_t(end as Py_ssize_t) };
    if kind.is_null() || position.is_null() {
        unsafe {
            cpython_sys::Py_DecRef(tuple);
            if !kind.is_null() {
                cpython_sys::Py_DecRef(kind);
            }
            if !position.is_null() {
                cpython_sys::Py_DecRef(position);
            }
        }
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(tuple, 0, kind) } != 0
        || unsafe { PyTuple_SetItem(tuple, 1, position) } != 0
    {
        unsafe { cpython_sys::Py_DecRef(tuple) };
        return ptr::null_mut();
    }
    tuple
}

unsafe extern "C" fn scan(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 7 {
        unsafe {
            PyErr_SetString(
                PyExc_ValueError,
                c"next_token() expects seven arguments".as_ptr(),
            )
        };
        return ptr::null_mut();
    }
    let text = unsafe { *args };
    let Some(input) = (unsafe { Input::new(text) }) else {
        return ptr::null_mut();
    };
    let Some(start) = (unsafe { read_index(*args.add(1)) }) else {
        return ptr::null_mut();
    };
    if start > input.length {
        unsafe { PyErr_SetString(PyExc_ValueError, c"token offset exceeds input length".as_ptr()) };
        return ptr::null_mut();
    }
    let Some(end) = (unsafe { read_bool(*args.add(2)) }) else {
        return ptr::null_mut();
    };
    let Some(convert_charrefs) = (unsafe { read_bool(*args.add(3)) }) else {
        return ptr::null_mut();
    };
    let cdata_element = unsafe { *args.add(4) };
    let Some(escapable) = (unsafe { read_bool(*args.add(5)) }) else {
        return ptr::null_mut();
    };
    let Some(support_cdata) = (unsafe { read_bool(*args.add(6)) }) else {
        return ptr::null_mut();
    };
    let (kind, token_end) = unsafe {
        next_token(
            &input,
            start,
            end,
            convert_charrefs,
            cdata_element,
            escapable,
            support_cdata,
        )
    };
    unsafe { token_result(kind, token_end) }
}

pub extern "C" fn _html_parser_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _html_parser_rs_free(_object: *mut std::ffi::c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _HTML_PARSER_RS_MODULE_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"next_token".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: scan },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return the next HTML token boundary.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

// The scanner has no interpreter-owned state or global Python objects.
pub struct ModuleSlots {
    ffi: UnsafeCell<[PyModuleDef_Slot; 2]>,
}

impl ModuleSlots {
    const fn as_mut_ptr(&self) -> *mut PyModuleDef_Slot {
        self.ffi.get().cast::<PyModuleDef_Slot>()
    }
}

// CPython reads this initialized table while creating each module instance.
unsafe impl Sync for ModuleSlots {}

pub static _HTML_PARSER_RS_MODULE_SLOTS: ModuleSlots = ModuleSlots {
    ffi: UnsafeCell::new([
        PyModuleDef_Slot {
            slot: PY_MOD_MULTIPLE_INTERPRETERS,
            value: 2usize as *mut c_void,
        },
        PyModuleDef_Slot {
            slot: 0,
            value: ptr::null_mut(),
        },
    ]),
};

pub static _HTML_PARSER_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_html_parser_rs".as_ptr() as *mut _,
        m_doc: c"Rust HTML token scanner.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_HTML_PARSER_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: _HTML_PARSER_RS_MODULE_SLOTS.as_mut_ptr(),
        m_traverse: None,
        m_clear: Some(_html_parser_rs_clear),
        m_free: Some(_html_parser_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__html_parser_rs() -> *mut PyObject {
    _HTML_PARSER_RS_MODULE.init_multi_phase()
}
