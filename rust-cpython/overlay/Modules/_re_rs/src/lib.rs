use std::cell::UnsafeCell;
use std::collections::{HashMap, VecDeque};
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;
use std::str;
use std::sync::{Mutex, OnceLock};

use cpython_sys::{
    METH_FASTCALL, PyBool_FromLong, PyErr_Clear, PyErr_Occurred, PyLong_AsLong,
    PyLong_FromLong, PyLong_FromSsize_t, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyObject, PyTuple_New, PyTuple_SetItem,
    PyUnicode_AsUTF8AndSize, Py_DecRef, Py_ssize_t,
};
use regex::bytes::{Regex, RegexBuilder};

const CACHE_LIMIT: usize = 512;

struct RegexCache {
    expressions: HashMap<String, Regex>,
    insertion_order: VecDeque<String>,
}

impl RegexCache {
    fn new() -> Self {
        Self {
            expressions: HashMap::new(),
            insertion_order: VecDeque::new(),
        }
    }
}

static REGEX_CACHE: OnceLock<Mutex<RegexCache>> = OnceLock::new();

fn regex_cache() -> &'static Mutex<RegexCache> {
    REGEX_CACHE.get_or_init(|| Mutex::new(RegexCache::new()))
}

fn portable_expression(pattern: &str) -> Option<Regex> {
    if !pattern.is_ascii() || !portable_syntax(pattern.as_bytes()) {
        return None;
    }

    {
        let cache = regex_cache()
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if let Some(expression) = cache.expressions.get(pattern) {
            return Some(expression.clone());
        }
    }

    // Patterns and subjects are ASCII, so byte-mode ASCII classes match exactly
    // what the Unicode classes would, without Unicode tables or their NFAs.
    let expression = RegexBuilder::new(pattern).unicode(false).build().ok()?;
    let mut cache = regex_cache()
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    if let Some(cached) = cache.expressions.get(pattern) {
        return Some(cached.clone());
    }
    if cache.expressions.len() >= CACHE_LIMIT {
        if let Some(oldest) = cache.insertion_order.pop_front() {
            cache.expressions.remove(&oldest);
        }
    }
    cache
        .insertion_order
        .push_back(pattern.to_owned());
    cache
        .expressions
        .insert(pattern.to_owned(), expression.clone());
    Some(expression)
}

fn portable_syntax(pattern: &[u8]) -> bool {
    let mut in_class = false;
    let mut class_has_character = false;
    let mut group_depth = 0usize;
    let mut index = 0usize;

    while index < pattern.len() {
        let byte = pattern[index];
        if byte == b'\\' {
            let Some(&escaped) = pattern.get(index + 1) else {
                return false;
            };
            let supported = match escaped {
                b'd' | b'D' | b's' | b'S' | b'w' | b'W' | b'n' | b'r' | b't' | b'f'
                | b'v' => true,
                b'b' if !in_class => true,
                b'A' | b'z' if !in_class => true,
                b'\\' | b'.' | b'^' | b'$' | b'*' | b'+' | b'?' | b'{' | b'}' | b'['
                | b']' | b'(' | b')' | b'|' | b'-' | b'#' | b'&' | b'~' | b' ' => true,
                _ => false,
            };
            if !supported {
                return false;
            }
            if in_class {
                class_has_character = true;
            }
            index += 2;
            continue;
        }

        if in_class {
            match byte {
                b'[' | b'&' | b'~' => return false,
                b']' => {
                    if !class_has_character {
                        return false;
                    }
                    in_class = false;
                }
                b'^' if !class_has_character => {}
                _ => class_has_character = true,
            }
            index += 1;
            continue;
        }

        match byte {
            b'[' => {
                in_class = true;
                class_has_character = false;
            }
            b']' | b'$' => return false,
            b'(' => {
                if pattern.get(index + 1) == Some(&b'?') {
                    if pattern.get(index + 2) != Some(&b':') {
                        return false;
                    }
                    index += 2;
                }
                group_depth += 1;
            }
            b')' => {
                let Some(depth) = group_depth.checked_sub(1) else {
                    return false;
                };
                group_depth = depth;
            }
            b'*' | b'+' | b'?' | b'}' => {
                if pattern.get(index + 1) == Some(&b'+') {
                    return false;
                }
            }
            _ => {}
        }
        index += 1;
    }

    !in_class && group_depth == 0
}

unsafe fn ascii_unicode(object: *mut PyObject) -> Option<String> {
    let mut length: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if data.is_null() || length < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    let bytes = unsafe { slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    if !bytes.is_ascii() {
        return None;
    }
    str::from_utf8(bytes).ok().map(str::to_owned)
}

unsafe fn supported_flags(object: *mut PyObject) -> bool {
    let flags = unsafe { PyLong_AsLong(object) };
    let error = unsafe { PyErr_Occurred() };
    if flags == -1 && !error.is_null() {
        unsafe { PyErr_Clear() };
        return false;
    }
    flags == 0 || flags == 32
}

unsafe fn prepare_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 2 {
        return unsafe { PyBool_FromLong(0) };
    }
    let pattern = unsafe { ascii_unicode(*args) };
    let flags_ok = unsafe { supported_flags(*args.add(1)) };
    let prepared = pattern
        .as_deref()
        .filter(|_| flags_ok)
        .and_then(portable_expression)
        .is_some();
    unsafe { PyBool_FromLong(if prepared { 1 } else { 0 }) }
}

unsafe fn search_result(status: c_int, start: usize, end: usize) -> *mut PyObject {
    let result = unsafe { PyTuple_New(3) };
    if result.is_null() {
        return ptr::null_mut();
    }
    let values = [
        unsafe { PyLong_FromLong(status.into()) },
        unsafe { PyLong_FromSsize_t(start as Py_ssize_t) },
        unsafe { PyLong_FromSsize_t(end as Py_ssize_t) },
    ];
    for (index, value) in values.into_iter().enumerate() {
        if value.is_null()
            || unsafe { PyTuple_SetItem(result, index as Py_ssize_t, value) } != 0
        {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

unsafe fn search_impl(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 3 {
        return unsafe { search_result(0, 0, 0) };
    }
    let pattern = unsafe { ascii_unicode(*args) };
    let subject = unsafe { ascii_unicode(*args.add(1)) };
    let flags_ok = unsafe { supported_flags(*args.add(2)) };
    let Some((pattern, subject)) = pattern.zip(subject).filter(|_| flags_ok) else {
        return unsafe { search_result(0, 0, 0) };
    };
    let Some(expression) = portable_expression(&pattern) else {
        return unsafe { search_result(0, 0, 0) };
    };
    match expression.find(subject.as_bytes()) {
        Some(found) => unsafe { search_result(2, found.start(), found.end()) },
        None => unsafe { search_result(1, 0, 0) },
    }
}

unsafe extern "C" fn prepare(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { prepare_impl(args, nargs) }
}

unsafe extern "C" fn search(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { search_impl(args, nargs) }
}

pub extern "C" fn _re_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _re_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _RE_RS_MODULE_METHODS: [PyMethodDef; 3] = [
    PyMethodDef {
        ml_name: c"prepare".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: prepare,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Prepare a supported regular expression for searching.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"search".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: search,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Search an ASCII string with a supported expression.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _RE_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_re_rs".as_ptr() as *mut _,
        m_doc: c"Rust regular-expression search for a compatible ASCII subset.".as_ptr()
            as *mut _,
        m_size: 0,
        m_methods: &_RE_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_re_rs_clear),
        m_free: Some(_re_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__re_rs() -> *mut PyObject {
    _RE_RS_MODULE.init_multi_phase()
}
