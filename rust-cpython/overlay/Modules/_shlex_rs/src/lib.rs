use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_ValueError;
use cpython_sys::PyList_Append;
use cpython_sys::PyList_New;
use cpython_sys::PyMem_Free;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyUnicode_AsUCS4Copy;
use cpython_sys::PyUnicode_FromKindAndData;
use cpython_sys::PyUnicode_GetLength;
use cpython_sys::Py_ssize_t;

#[derive(Clone, Copy)]
enum State {
    Whitespace,
    Word,
    SingleQuote,
    DoubleQuote,
    Escape(Option<u32>),
}

#[derive(Clone, Copy)]
enum SplitError {
    MissingQuote,
    MissingEscape,
}

struct OwnedUcs4(*mut u32);

impl Drop for OwnedUcs4 {
    fn drop(&mut self) {
        unsafe { PyMem_Free(self.0.cast()) };
    }
}

fn is_whitespace(character: u32) -> bool {
    matches!(character, 0x20 | 0x09 | 0x0a | 0x0d)
}

fn skip_comment(input: &[u32], index: &mut usize) {
    while *index < input.len() {
        let character = input[*index];
        *index += 1;
        if character == 0x0a {
            break;
        }
    }
}

fn split_codepoints(
    input: &[u32],
    comments: bool,
    posix: bool,
) -> Result<Vec<Vec<u32>>, SplitError> {
    let mut result = Vec::new();
    let mut index = 0;

    while index < input.len() {
        let mut token = Vec::new();
        let mut state = State::Whitespace;
        let mut quoted = false;

        loop {
            match state {
                State::Whitespace => {
                    if index == input.len() {
                        break;
                    }
                    let character = input[index];
                    index += 1;
                    if is_whitespace(character) {
                        continue;
                    }
                    if comments && character == u32::from(b'#') {
                        skip_comment(input, &mut index);
                        continue;
                    }
                    if posix && character == u32::from(b'\\') {
                        state = State::Escape(None);
                    } else if character == u32::from(b'\'') {
                        if !posix {
                            token.push(character);
                        }
                        state = State::SingleQuote;
                    } else if character == u32::from(b'"') {
                        if !posix {
                            token.push(character);
                        }
                        state = State::DoubleQuote;
                    } else {
                        token.push(character);
                        state = State::Word;
                    }
                }
                State::Word => {
                    if index == input.len() {
                        if !token.is_empty() || (posix && quoted) {
                            result.push(token);
                        }
                        break;
                    }
                    let character = input[index];
                    index += 1;
                    if is_whitespace(character) {
                        state = State::Whitespace;
                        if !token.is_empty() || (posix && quoted) {
                            result.push(token);
                            break;
                        }
                        continue;
                    }
                    if comments && character == u32::from(b'#') {
                        skip_comment(input, &mut index);
                        if posix {
                            state = State::Whitespace;
                            if !token.is_empty() || quoted {
                                result.push(token);
                                break;
                            }
                        }
                        continue;
                    }
                    if posix && character == u32::from(b'\'') {
                        state = State::SingleQuote;
                    } else if posix && character == u32::from(b'"') {
                        state = State::DoubleQuote;
                    } else if posix && character == u32::from(b'\\') {
                        state = State::Escape(None);
                    } else {
                        token.push(character);
                    }
                }
                State::SingleQuote | State::DoubleQuote => {
                    quoted = true;
                    if index == input.len() {
                        return Err(SplitError::MissingQuote);
                    }
                    let character = input[index];
                    index += 1;
                    let quote = match state {
                        State::SingleQuote => u32::from(b'\''),
                        State::DoubleQuote => u32::from(b'"'),
                        _ => unreachable!(),
                    };
                    if character == quote {
                        if posix {
                            state = State::Word;
                        } else {
                            token.push(character);
                            result.push(token);
                            break;
                        }
                    } else if posix
                        && quote == u32::from(b'"')
                        && character == u32::from(b'\\')
                    {
                        state = State::Escape(Some(quote));
                    } else {
                        token.push(character);
                    }
                }
                State::Escape(quote) => {
                    if index == input.len() {
                        return Err(SplitError::MissingEscape);
                    }
                    let character = input[index];
                    index += 1;
                    if let Some(quote) = quote {
                        if character != u32::from(b'\\') && character != quote {
                            token.push(u32::from(b'\\'));
                        }
                    }
                    token.push(character);
                    state = match quote {
                        Some(quote) if quote == u32::from(b'"') => State::DoubleQuote,
                        Some(_) => State::SingleQuote,
                        None => State::Word,
                    };
                }
            }
        }
    }

    Ok(result)
}

fn can_use_shlex_crate(input: &[u32], comments: bool) -> bool {
    !comments
        && !input
            .iter()
            .any(|character| matches!(*character, 0x23 | 0x0d | 0xd800..=0xdfff))
        && !input
            .windows(2)
            .any(|pair| pair == [u32::from(b'\\'), 0x0a])
        // The crate removes these escapes inside double quotes; shlex keeps the backslash.
        && !input.windows(2).any(|pair| {
            pair[0] == u32::from(b'\\')
                && (pair[1] == u32::from(b'$') || pair[1] == u32::from(b'`'))
        })
}

fn split_input(input: &[u32], comments: bool, posix: bool) -> Result<Vec<Vec<u32>>, SplitError> {
    if posix && can_use_shlex_crate(input, comments) {
        let mut text = String::with_capacity(input.len());
        for &codepoint in input {
            let Some(character) = char::from_u32(codepoint) else {
                return split_codepoints(input, comments, posix);
            };
            text.push(character);
        }
        if let Some(words) = shlex::split(&text) {
            return Ok(words
                .into_iter()
                .map(|word| word.chars().map(u32::from).collect())
                .collect());
        }
    }
    split_codepoints(input, comments, posix)
}

unsafe extern "C" fn split(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_ValueError,
                c"internal shlex split requires three arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let source = unsafe { *args };
    let source_len = unsafe { PyUnicode_GetLength(source) };
    if source_len < 0 {
        return ptr::null_mut();
    }
    let source_chars = unsafe { PyUnicode_AsUCS4Copy(source) };
    if source_chars.is_null() {
        return ptr::null_mut();
    }
    let source_chars = OwnedUcs4(source_chars);
    let input = unsafe { std::slice::from_raw_parts(source_chars.0, source_len as usize) };

    let posix = unsafe { PyObject_IsTrue(*args.add(2)) };
    if posix < 0 {
        return ptr::null_mut();
    }
    let comments = unsafe { PyObject_IsTrue(*args.add(1)) };
    if comments < 0 {
        return ptr::null_mut();
    }

    let words = match split_input(input, comments != 0, posix != 0) {
        Ok(words) => words,
        Err(SplitError::MissingQuote) => {
            unsafe {
                PyErr_SetString(PyExc_ValueError, c"No closing quotation".as_ptr());
            }
            return ptr::null_mut();
        }
        Err(SplitError::MissingEscape) => {
            unsafe {
                PyErr_SetString(PyExc_ValueError, c"No escaped character".as_ptr());
            }
            return ptr::null_mut();
        }
    };

    let list = unsafe { PyList_New(0) };
    if list.is_null() {
        return ptr::null_mut();
    }
    for word in words {
        let word_len = match Py_ssize_t::try_from(word.len()) {
            Ok(length) => length,
            Err(_) => {
                unsafe {
                    PyErr_NoMemory();
                    Py_DecRef(list);
                }
                return ptr::null_mut();
            }
        };
        let word_obj = unsafe {
            PyUnicode_FromKindAndData(4, word.as_ptr().cast::<c_void>(), word_len)
        };
        if word_obj.is_null() {
            unsafe { Py_DecRef(list) };
            return ptr::null_mut();
        }
        let status = unsafe { PyList_Append(list, word_obj) };
        unsafe { Py_DecRef(word_obj) };
        if status < 0 {
            unsafe { Py_DecRef(list) };
            return ptr::null_mut();
        }
    }
    list
}

pub extern "C" fn _shlex_rs_clear(_obj: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _shlex_rs_free(_obj: *mut c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static MODULE_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"split".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: split,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Split shell-like words using Rust parsing.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_shlex_rs".as_ptr() as *mut _,
        m_doc: c"Rust implementation used by the shlex module.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_shlex_rs_clear),
        m_free: Some(_shlex_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__shlex_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
