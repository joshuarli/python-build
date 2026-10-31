//! Shell-like word splitting for `shlex.split`.
//!
//! The crate is `no_std` and declares the few C-API entry points it uses
//! itself: linking Rust `std` (and `cpython-sys`, which depends on it) adds
//! roughly 400 KiB of panic, backtrace, and I/O code to the extension image.
//! The state machine works in one scratch buffer (input copy plus one token)
//! that lives on the stack for short strings and in a single `PyMem`
//! allocation otherwise.
#![no_std]

use core::ffi::c_void;
use core::mem::MaybeUninit;
use core::ptr;

use cpython_binding::ffi::{
    PyErr_NoMemory, PyErr_SetString, PyExc_ValueError, PyList_Append, PyList_New, PyMem_Free,
    PyMem_Malloc, PyMethodDef, PyObject, PyObject_IsTrue, PyUnicode_AsUCS4,
    PyUnicode_FromKindAndData, PyUnicode_GetLength, Py_DecRef, Py_ssize_t,
};
use cpython_binding::{Module, fastcall, method_table_end};

/// Stack scratch capacity in code points (input copy plus token buffer).
const STACK_CODEPOINTS: usize = 512;

#[derive(Clone, Copy, PartialEq)]
enum State {
    Whitespace,
    Word,
    SingleQuote,
    DoubleQuote,
    Escape,
}

/// A failed split. `Python` means an exception is already set.
#[derive(Clone, Copy)]
enum SplitError {
    MissingQuote,
    MissingEscape,
    Python,
}

const NUL: u32 = 0;
const SPACE: u32 = 0x20;
const TAB: u32 = 0x09;
const LF: u32 = 0x0a;
const CR: u32 = 0x0d;
const HASH: u32 = b'#' as u32;
const BACKSLASH: u32 = b'\\' as u32;
const SQUOTE: u32 = b'\'' as u32;
const DQUOTE: u32 = b'"' as u32;

fn is_whitespace(character: u32) -> bool {
    matches!(character, SPACE | TAB | LF | CR)
}

fn skip_comment(input: &[u32], index: &mut usize) {
    while *index < input.len() {
        let character = input[*index];
        *index += 1;
        if character == LF {
            break;
        }
    }
}

unsafe fn emit(list: *mut PyObject, token: &[u32]) -> Result<(), SplitError> {
    let word = unsafe {
        PyUnicode_FromKindAndData(4, token.as_ptr().cast::<c_void>(), token.len() as Py_ssize_t)
    };
    if word.is_null() {
        return Err(SplitError::Python);
    }
    let status = unsafe { PyList_Append(list, word) };
    unsafe { Py_DecRef(word) };
    if status < 0 {
        return Err(SplitError::Python);
    }
    Ok(())
}

/// Split `input` into words, appending each to `list`. `token` must hold at
/// least `input.len()` code points, which bounds any single token.
unsafe fn split_into(
    list: *mut PyObject,
    input: &[u32],
    token: &mut [u32],
    comments: bool,
    posix: bool,
) -> Result<(), SplitError> {
    let mut index = 0;
    let mut length = 0;
    let mut state = State::Whitespace;
    // Quote that an escape returns to (`NUL` for a bare escape), and whether the
    // current token has seen a quote (an empty quoted token is kept in POSIX mode).
    let mut escape_quote = NUL;
    let mut quoted = false;

    macro_rules! push {
        ($character:expr) => {{
            token[length] = $character;
            length += 1;
        }};
    }
    macro_rules! finish {
        () => {{
            if length > 0 || (posix && quoted) {
                unsafe { emit(list, &token[..length]) }?;
            }
            length = 0;
            quoted = false;
        }};
    }

    loop {
        match state {
            State::Whitespace => {
                if index == input.len() {
                    return Ok(());
                }
                let character = input[index];
                index += 1;
                if is_whitespace(character) {
                    continue;
                }
                if comments && character == HASH {
                    skip_comment(input, &mut index);
                    continue;
                }
                if posix && character == BACKSLASH {
                    escape_quote = NUL;
                    state = State::Escape;
                } else if character == SQUOTE {
                    if !posix {
                        push!(character);
                    }
                    state = State::SingleQuote;
                } else if character == DQUOTE {
                    if !posix {
                        push!(character);
                    }
                    state = State::DoubleQuote;
                } else {
                    push!(character);
                    state = State::Word;
                }
            }
            State::Word => {
                if index == input.len() {
                    finish!();
                    return Ok(());
                }
                let character = input[index];
                index += 1;
                if is_whitespace(character) {
                    state = State::Whitespace;
                    finish!();
                    continue;
                }
                if comments && character == HASH {
                    skip_comment(input, &mut index);
                    if posix {
                        state = State::Whitespace;
                        finish!();
                    }
                    continue;
                }
                if posix && character == SQUOTE {
                    state = State::SingleQuote;
                } else if posix && character == DQUOTE {
                    state = State::DoubleQuote;
                } else if posix && character == BACKSLASH {
                    escape_quote = NUL;
                    state = State::Escape;
                } else {
                    push!(character);
                }
            }
            State::SingleQuote | State::DoubleQuote => {
                quoted = true;
                if index == input.len() {
                    return Err(SplitError::MissingQuote);
                }
                let character = input[index];
                index += 1;
                let quote = if state == State::SingleQuote { SQUOTE } else { DQUOTE };
                if character == quote {
                    if posix {
                        state = State::Word;
                    } else {
                        push!(character);
                        unsafe { emit(list, &token[..length]) }?;
                        length = 0;
                        quoted = false;
                        state = State::Whitespace;
                    }
                } else if posix && quote == DQUOTE && character == BACKSLASH {
                    escape_quote = quote;
                    state = State::Escape;
                } else {
                    push!(character);
                }
            }
            State::Escape => {
                if index == input.len() {
                    return Err(SplitError::MissingEscape);
                }
                let character = input[index];
                index += 1;
                if escape_quote != NUL && character != BACKSLASH && character != escape_quote {
                    push!(BACKSLASH);
                }
                push!(character);
                state = if escape_quote == DQUOTE { State::DoubleQuote } else { State::Word };
            }
        }
    }
}

unsafe fn run(
    list: *mut PyObject,
    source: *mut PyObject,
    length: usize,
    comments: bool,
    posix: bool,
) -> Result<(), SplitError> {
    let mut stack = [MaybeUninit::<u32>::uninit(); STACK_CODEPOINTS];
    let mut heap: *mut u32 = ptr::null_mut();
    let base: *mut u32 = if length <= STACK_CODEPOINTS / 2 {
        stack.as_mut_ptr().cast()
    } else {
        let Some(bytes) = length.checked_mul(2 * size_of::<u32>()) else {
            unsafe { PyErr_NoMemory() };
            return Err(SplitError::Python);
        };
        heap = unsafe { PyMem_Malloc(bytes) }.cast();
        if heap.is_null() {
            unsafe { PyErr_NoMemory() };
            return Err(SplitError::Python);
        }
        heap
    };

    let result = if unsafe { PyUnicode_AsUCS4(source, base, length as Py_ssize_t, 0) }.is_null() {
        Err(SplitError::Python)
    } else {
        let input = unsafe { core::slice::from_raw_parts(base, length) };
        let token = unsafe { core::slice::from_raw_parts_mut(base.add(length), length) };
        unsafe { split_into(list, input, token, comments, posix) }
    };
    if !heap.is_null() {
        unsafe { PyMem_Free(heap.cast()) };
    }
    result
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
    let posix = unsafe { PyObject_IsTrue(*args.add(2)) };
    if posix < 0 {
        return ptr::null_mut();
    }
    let comments = unsafe { PyObject_IsTrue(*args.add(1)) };
    if comments < 0 {
        return ptr::null_mut();
    }

    let list = unsafe { PyList_New(0) };
    if list.is_null() {
        return ptr::null_mut();
    }
    match unsafe { run(list, source, source_len as usize, comments != 0, posix != 0) } {
        Ok(()) => list,
        Err(error) => {
            unsafe {
                match error {
                    SplitError::MissingQuote => {
                        PyErr_SetString(PyExc_ValueError, c"No closing quotation".as_ptr())
                    }
                    SplitError::MissingEscape => {
                        PyErr_SetString(PyExc_ValueError, c"No escaped character".as_ptr())
                    }
                    SplitError::Python => {}
                }
                Py_DecRef(list);
            }
            ptr::null_mut()
        }
    }
}

static METHODS: [PyMethodDef; 2] = [
    fastcall(
        c"split",
        split,
        c"Split shell-like words using Rust parsing.",
    ),
    method_table_end(),
];

static MODULE: Module =
    Module::new(c"_shlex_rs", c"Rust implementation used by the shlex module.", &METHODS);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__shlex_rs() -> *mut PyObject {
    MODULE.init()
}
