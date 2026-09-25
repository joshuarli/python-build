use std::cell::UnsafeCell;
use std::collections::{HashMap, VecDeque};
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::sync::{Arc, Mutex, OnceLock};

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyBool_FromLong;
use cpython_sys::PyBytes_AsStringAndSize;
use cpython_sys::Py_DecRef;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyUnicode_GetLength;
use cpython_sys::PyUnicode_New;
use cpython_sys::PyUnicode_ReadChar;
use cpython_sys::PyUnicode_WriteChar;
use cpython_sys::Py_ssize_t;

const CACHE_LIMIT: usize = 32_768;

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
enum PatternKey {
    Text(Vec<u32>),
    Bytes(Vec<u8>),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum PatternKind {
    Text,
    Bytes,
}

#[derive(Clone, Debug)]
enum Token {
    Literal(u32),
    Any,
    Star,
    Class(CharacterClass),
}

#[derive(Clone, Debug)]
struct CharacterClass {
    inverted: bool,
    ranges: Vec<(u32, u32)>,
}

#[derive(Clone, Debug)]
struct Pattern {
    kind: PatternKind,
    tokens: Vec<Token>,
}

struct PatternCache {
    entries: HashMap<PatternKey, Arc<Pattern>>,
    insertion_order: VecDeque<PatternKey>,
}

impl PatternCache {
    fn new() -> Self {
        Self {
            entries: HashMap::new(),
            insertion_order: VecDeque::new(),
        }
    }

    fn get_or_insert(&mut self, key: PatternKey) -> Arc<Pattern> {
        if let Some(pattern) = self.entries.get(&key) {
            return Arc::clone(pattern);
        }
        let pattern = Arc::new(compile_pattern(&key));
        self.insertion_order.push_back(key.clone());
        self.entries.insert(key, Arc::clone(&pattern));
        if self.entries.len() > CACHE_LIMIT {
            if let Some(oldest) = self.insertion_order.pop_front() {
                self.entries.remove(&oldest);
            }
        }
        pattern
    }
}

static PATTERN_CACHE: OnceLock<Mutex<PatternCache>> = OnceLock::new();

fn pattern_cache() -> &'static Mutex<PatternCache> {
    PATTERN_CACHE.get_or_init(|| Mutex::new(PatternCache::new()))
}

fn compile_pattern(key: &PatternKey) -> Pattern {
    let (kind, pattern): (PatternKind, Vec<u32>) = match key {
        PatternKey::Text(pattern) => (PatternKind::Text, pattern.clone()),
        PatternKey::Bytes(pattern) => (
            PatternKind::Bytes,
            pattern.iter().map(|byte| u32::from(*byte)).collect(),
        ),
    };
    let mut tokens = Vec::new();
    let mut index = 0;
    while index < pattern.len() {
        match pattern[index] {
            42 => {
                if !matches!(tokens.last(), Some(Token::Star)) {
                    tokens.push(Token::Star);
                }
                index += 1;
            }
            63 => {
                tokens.push(Token::Any);
                index += 1;
            }
            91 => {
                if let Some((end, class)) = parse_class(&pattern, index) {
                    tokens.push(Token::Class(class));
                    index = end;
                } else {
                    tokens.push(Token::Literal(pattern[index]));
                    index += 1;
                }
            }
            literal => {
                tokens.push(Token::Literal(literal));
                index += 1;
            }
        }
    }
    Pattern { kind, tokens }
}

fn parse_class(pattern: &[u32], open: usize) -> Option<(usize, CharacterClass)> {
    let mut end = open + 1;
    if end < pattern.len() && pattern[end] == b'!' as u32 {
        end += 1;
    }
    if end < pattern.len() && pattern[end] == b']' as u32 {
        end += 1;
    }
    while end < pattern.len() && pattern[end] != b']' as u32 {
        end += 1;
    }
    if end == pattern.len() {
        return None;
    }

    let contents = &pattern[open + 1..end];
    let (normalized, inverted) = normalize_class(contents);
    Some((end + 1, class_from_normalized(&normalized, inverted)))
}

fn normalize_class(contents: &[u32]) -> (Vec<u32>, bool) {
    let inverted = contents.first() == Some(&(b'!' as u32));
    let has_range_marker = contents.contains(&(b'-' as u32));
    let mut normalized = Vec::new();
    if !has_range_marker {
        for character in contents {
            if *character == b'\\' as u32 {
                normalized.push(b'\\' as u32);
            }
            normalized.push(*character);
        }
    } else {
        let mut chunks: Vec<Vec<u32>> = Vec::new();
        let mut start = 0;
        let mut search = if inverted { 2 } else { 1 };
        while let Some(hyphen) = find_codepoint(contents, b'-' as u32, search) {
            chunks.push(contents[start..hyphen].to_vec());
            start = hyphen + 1;
            search = hyphen + 3;
        }
        let final_chunk = contents[start..].to_vec();
        if final_chunk.is_empty() {
            if let Some(previous) = chunks.last_mut() {
                previous.push(b'-' as u32);
            } else {
                chunks.push(vec![b'-' as u32]);
            }
        } else {
            chunks.push(final_chunk);
        }

        let mut index = chunks.len();
        while index > 1 {
            index -= 1;
            let left_end = chunks[index - 1].last().copied();
            let right_start = chunks[index].first().copied();
            if matches!((left_end, right_start), (Some(left), Some(right)) if left > right) {
                let right = chunks.remove(index);
                chunks[index - 1].pop();
                chunks[index - 1].extend_from_slice(&right[1..]);
            }
        }

        for chunk_index in 0..chunks.len() {
            if chunk_index > 0 {
                normalized.push(b'-' as u32);
            }
            for character in &chunks[chunk_index] {
                if *character == b'\\' as u32 || *character == b'-' as u32 {
                    normalized.push(b'\\' as u32);
                }
                normalized.push(*character);
            }
        }
    }

    let mut escaped = Vec::with_capacity(normalized.len());
    for character in normalized {
        if matches!(character, 38 | 126 | 124) {
            escaped.push(b'\\' as u32);
        }
        escaped.push(character);
    }
    let mut normalized = escaped;
    if normalized.first() == Some(&(b'!' as u32)) {
        normalized[0] = b'^' as u32;
    } else if matches!(normalized.first(), Some(value) if *value == b'^' as u32 || *value == b'[' as u32)
    {
        normalized.insert(0, b'\\' as u32);
    }
    (normalized, inverted)
}

fn find_codepoint(pattern: &[u32], needle: u32, start: usize) -> Option<usize> {
    pattern
        .iter()
        .enumerate()
        .skip(start)
        .find_map(|(index, value)| (*value == needle).then_some(index))
}

fn class_from_normalized(normalized: &[u32], inverted: bool) -> CharacterClass {
    let mut body = normalized;
    if inverted && body.first() == Some(&(b'^' as u32)) {
        body = &body[1..];
    }
    if !inverted
        && body.first() == Some(&(b'\\' as u32))
        && matches!(body.get(1), Some(value) if *value == b'^' as u32 || *value == b'[' as u32)
    {
        body = &body[1..];
    }

    let mut members = Vec::new();
    let mut index = 0;
    if body.first() == Some(&(b']' as u32)) {
        members.push((b']' as u32, false));
        index += 1;
    }
    while index < body.len() {
        if body[index] == b'\\' as u32 && index + 1 < body.len() {
            members.push((body[index + 1], false));
            index += 2;
        } else {
            members.push((body[index], body[index] == b'-' as u32));
            index += 1;
        }
    }

    let mut ranges = Vec::new();
    index = 0;
    while index < members.len() {
        if index + 2 < members.len()
            && members[index + 1].1
            && !members[index].1
            && !members[index + 2].1
            && members[index].0 <= members[index + 2].0
        {
            ranges.push((members[index].0, members[index + 2].0));
            index += 3;
        } else {
            ranges.push((members[index].0, members[index].0));
            index += 1;
        }
    }
    CharacterClass { inverted, ranges }
}

fn matches(pattern: &Pattern, input: &[u32]) -> bool {
    let mut pattern_index = 0;
    let mut input_index = 0;
    let mut last_star = None;

    while input_index < input.len() {
        let matched = match pattern.tokens.get(pattern_index) {
            Some(Token::Literal(expected)) => *expected == input[input_index],
            Some(Token::Any) => true,
            Some(Token::Class(class)) => class.matches(input[input_index]),
            Some(Token::Star) => {
                last_star = Some((pattern_index + 1, input_index));
                pattern_index += 1;
                continue;
            }
            None => false,
        };
        if matched {
            input_index += 1;
            pattern_index += 1;
        } else if let Some((next_pattern_index, next_input_index)) = last_star {
            let next_input_index = next_input_index + 1;
            last_star = Some((next_pattern_index, next_input_index));
            pattern_index = next_pattern_index;
            input_index = next_input_index;
        } else {
            return false;
        }
    }

    pattern.tokens[pattern_index..]
        .iter()
        .all(|token| matches!(token, Token::Star))
}

impl CharacterClass {
    fn matches(&self, character: u32) -> bool {
        let found = self
            .ranges
            .iter()
            .any(|(start, end)| *start <= character && character <= *end);
        found != self.inverted
    }
}

fn py_unicode_to_units(object: *mut PyObject) -> Result<Vec<u32>, ()> {
    let length = unsafe { PyUnicode_GetLength(object) };
    if length < 0 {
        return Err(());
    }
    let mut value = Vec::with_capacity(length as usize);
    for index in 0..length {
        let character = unsafe { PyUnicode_ReadChar(object, index) };
        if character > 0x10ffff {
            return Err(());
        }
        value.push(character);
    }
    Ok(value)
}

fn py_bytes_to_units(object: *mut PyObject) -> Result<Vec<u8>, ()> {
    let mut bytes = ptr::null_mut::<c_char>();
    let mut length: Py_ssize_t = 0;
    if unsafe { PyBytes_AsStringAndSize(object, &mut bytes, &mut length) } != 0 {
        return Err(());
    }
    if length < 0 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"pattern or filename must be bytes or str".as_ptr(),
            );
        }
        return Err(());
    }
    let value = unsafe { std::slice::from_raw_parts(bytes.cast::<u8>(), length as usize) };
    Ok(value.to_vec())
}

fn pattern_key(object: *mut PyObject) -> Result<PatternKey, ()> {
    match py_unicode_to_units(object) {
        Ok(value) => Ok(PatternKey::Text(value)),
        Err(()) => {
            unsafe { PyErr_Clear() };
            py_bytes_to_units(object).map(PatternKey::Bytes)
        }
    }
}

fn filename_units(object: *mut PyObject) -> Result<PatternKey, ()> {
    match py_unicode_to_units(object) {
        Ok(value) => Ok(PatternKey::Text(value)),
        Err(()) => {
            unsafe { PyErr_Clear() };
            py_bytes_to_units(object).map(PatternKey::Bytes)
        }
    }
}

fn raise_type_error(message: &'static std::ffi::CStr) {
    unsafe { PyErr_SetString(PyExc_TypeError, message.as_ptr()) };
}

unsafe extern "C" fn prepare(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        raise_type_error(c"prepare() takes exactly one argument");
        return ptr::null_mut();
    }
    let key = match pattern_key(unsafe { *args }) {
        Ok(key) => key,
        Err(()) => return ptr::null_mut(),
    };
    pattern_cache().lock().unwrap().get_or_insert(key);
    unsafe { PyBool_FromLong(1) }
}

unsafe extern "C" fn matcher(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        raise_type_error(c"match() takes exactly two arguments");
        return ptr::null_mut();
    }
    let name = unsafe { *args };
    let pattern = unsafe { *args.add(1) };
    let key = match pattern_key(pattern) {
        Ok(key) => key,
        Err(()) => return ptr::null_mut(),
    };
    let compiled = pattern_cache().lock().unwrap().get_or_insert(key);
    let name = match filename_units(name) {
        Ok(name) => name,
        Err(()) => return ptr::null_mut(),
    };
    let (name_kind, name_units) = match name {
        PatternKey::Text(value) => (PatternKind::Text, value),
        PatternKey::Bytes(value) => (
            PatternKind::Bytes,
            value.into_iter().map(u32::from).collect(),
        ),
    };
    if name_kind != compiled.kind {
        raise_type_error(c"cannot mix bytes and non-bytes patterns and filenames");
        return ptr::null_mut();
    }
    unsafe { PyBool_FromLong(matches(&compiled, &name_units) as _) }
}

fn push_text(output: &mut Vec<u32>, text: &str) {
    output.extend(text.chars().map(u32::from));
}

fn escaped_regex_character(character: u32, output: &mut Vec<u32>) {
    if matches!(
        character,
        9 | 10 | 11 | 12 | 13 | 32 | 35 | 38 | 40 | 41 | 42 | 43 | 45 | 46 | 63 | 91 | 92
            | 93 | 94 | 123 | 124 | 125 | 126 | 36
    ) {
        output.push(b'\\' as u32);
    }
    output.push(character);
}

fn translate_parts(pattern: &[u32], star: u32, question: u32) -> (Vec<Vec<u32>>, Vec<usize>) {
    let mut parts = Vec::new();
    let mut star_indices = Vec::new();
    let mut index = 0;
    while index < pattern.len() {
        let character = pattern[index];
        index += 1;
        if character == b'*' as u32 {
            star_indices.push(parts.len());
            parts.push(vec![star]);
            while index < pattern.len() && pattern[index] == b'*' as u32 {
                index += 1;
            }
        } else if character == b'?' as u32 {
            parts.push(vec![question]);
        } else if character == b'[' as u32 {
            let mut end = index;
            if end < pattern.len() && pattern[end] == b'!' as u32 {
                end += 1;
            }
            if end < pattern.len() && pattern[end] == b']' as u32 {
                end += 1;
            }
            while end < pattern.len() && pattern[end] != b']' as u32 {
                end += 1;
            }
            if end == pattern.len() {
                parts.push(vec![b'\\' as u32, b'[' as u32]);
            } else {
                let contents = &pattern[index..end];
                let (mut stuff, _) = normalize_class(contents);
                if stuff.is_empty() {
                    parts.push("(?!)".chars().map(u32::from).collect());
                } else if stuff == [b'^' as u32]
                    && contents.first() == Some(&(b'!' as u32))
                {
                    parts.push(vec![b'.' as u32]);
                } else {
                    let mut class = vec![b'[' as u32];
                    class.append(&mut stuff);
                    class.push(b']' as u32);
                    parts.push(class);
                }
                index = end + 1;
            }
        } else {
            let mut escaped = Vec::new();
            escaped_regex_character(character, &mut escaped);
            parts.push(escaped);
        }
    }
    (parts, star_indices)
}

fn join_translated_parts(parts: &[Vec<u32>], star_indices: &[usize]) -> Vec<u32> {
    let mut body = Vec::new();
    if star_indices.is_empty() {
        for part in parts {
            body.extend_from_slice(part);
        }
    } else {
        let mut star_iterator = star_indices.iter();
        let first_star = *star_iterator.next().unwrap();
        for part in &parts[..first_star] {
            body.extend_from_slice(part);
        }
        let mut index = first_star + 1;
        for star in star_iterator {
            push_text(&mut body, "(?>.*?");
            for part in &parts[index..*star] {
                body.extend_from_slice(part);
            }
            body.push(b')' as u32);
            index = *star + 1;
        }
        push_text(&mut body, ".*");
        for part in &parts[index..] {
            body.extend_from_slice(part);
        }
    }
    let mut output = Vec::with_capacity(body.len() + 8);
    push_text(&mut output, "(?s:");
    output.extend(body);
    push_text(&mut output, ")\\z");
    output
}

unsafe extern "C" fn translate(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        raise_type_error(c"translate() takes exactly one argument");
        return ptr::null_mut();
    }
    let pattern = match py_unicode_to_units(unsafe { *args }) {
        Ok(pattern) => pattern,
        Err(()) => return ptr::null_mut(),
    };
    let (parts, star_indices) = translate_parts(&pattern, b'*' as u32, b'.' as u32);
    let translated = join_translated_parts(&parts, &star_indices);
    let max_character = translated.iter().copied().max().unwrap_or(0);
    let result = unsafe { PyUnicode_New(translated.len() as Py_ssize_t, max_character) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for (index, character) in translated.iter().copied().enumerate() {
        if unsafe { PyUnicode_WriteChar(result, index as Py_ssize_t, character) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

extern "C" fn module_clear(_module: *mut PyObject) -> c_int {
    0
}

extern "C" fn module_free(_module: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

static MODULE_METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"prepare".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: prepare,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Prepare a filename pattern for matching".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"match".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: matcher,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Match a filename against a shell-style pattern".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"translate".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: translate,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Translate a shell-style pattern to a regular expression".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_fnmatch_rs".as_ptr() as *mut _,
        m_doc: c"Rust filename pattern matching primitives".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(module_clear),
        m_free: Some(module_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__fnmatch_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
