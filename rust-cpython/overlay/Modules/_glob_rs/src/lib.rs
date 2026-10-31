//! Nonrecursive text pathname expansion for `glob`.
//!
//! The crate is `no_std`, walks directories with `readdir`, and declares the
//! few C-API entry points it uses itself: linking Rust `std` (and
//! `cpython-sys`, which depends on it) adds roughly 400 KiB of panic,
//! backtrace, and I/O code that is mapped and partly dirtied on every import
//! of the extension. Matching follows the `glob` crate's pattern syntax
//! (`?`, `*`, `[...]`, `[!...]`), and patterns it would reject fall back to
//! Python.
#![no_std]

use core::ffi::{CStr, c_char};

use cpython_binding::ffi::{
    PyErr_Clear, PyList_Append, PyList_New, PyObject, PyObject_IsTrue, PyUnicode_AsUTF8AndSize,
    PyUnicode_FromStringAndSize, Py_DecRef, Py_ssize_t,
};
use cpython_binding::{Module, Outcome, Owned, Stop, fastcall, into_return, method_table_end};

/// Capacity of the path buffer; longer paths use the Python fallback.
const PATH_CAPACITY: usize = 4096;

fn has_magic(text: &[u8]) -> bool {
    text.iter().any(|byte| matches!(byte, b'*' | b'?' | b'['))
}

/// Length in bytes of the UTF-8 sequence that starts with `lead`.
fn char_len(lead: u8) -> usize {
    match lead {
        0..=0x7f => 1,
        0xc0..=0xdf => 2,
        0xe0..=0xef => 3,
        _ => 4,
    }
}

fn decode(bytes: &[u8]) -> (char, usize) {
    let text = unsafe { core::str::from_utf8_unchecked(&bytes[..char_len(bytes[0])]) };
    match text.chars().next() {
        Some(character) => (character, text.len()),
        None => ('\0', 1),
    }
}

/// Parse the class starting at `pattern[start] == b'['` with the `glob`
/// crate's rules: returns whether it is negated, its body, and the index
/// after the closing bracket.
fn parse_class(pattern: &[u8], start: usize) -> Option<(bool, &[u8], usize)> {
    let negated = pattern.get(start + 1) == Some(&b'!');
    let body = start + 1 + usize::from(negated);
    let first = char_len(*pattern.get(body)?);
    let search = body + first;
    let close = search + pattern.get(search..)?.iter().position(|&byte| byte == b']')?;
    Some((negated, &pattern[body..close], close + 1))
}

fn in_class(body: &[u8], target: char) -> bool {
    let mut chars = unsafe { core::str::from_utf8_unchecked(body) }.chars();
    while let Some(first) = chars.next() {
        let mut ahead = chars.clone();
        if ahead.next() == Some('-') {
            if let Some(last) = ahead.next() {
                if first <= target && target <= last {
                    return true;
                }
                chars = ahead;
                continue;
            }
        }
        if first == target {
            return true;
        }
    }
    false
}

/// Match one validated pattern component against a file name.
fn matches(pattern: &[u8], name: &[u8]) -> bool {
    let (mut p, mut n) = (0, 0);
    // Pattern and name positions to resume from after the last `*`.
    let mut star: Option<(usize, usize)> = None;
    loop {
        if p < pattern.len() {
            match pattern[p] {
                b'*' => {
                    p += 1;
                    star = Some((p, n));
                    continue;
                }
                b'?' => {
                    if n < name.len() {
                        n += char_len(name[n]);
                        p += 1;
                        continue;
                    }
                }
                b'[' => {
                    if n < name.len() {
                        let Some((negated, body, next)) = parse_class(pattern, p) else {
                            return false;
                        };
                        let (target, width) = decode(&name[n..]);
                        if in_class(body, target) != negated {
                            n += width;
                            p = next;
                            continue;
                        }
                    }
                }
                lead => {
                    let width = char_len(lead);
                    if name.len() - n >= width && name[n..n + width] == pattern[p..p + width] {
                        n += width;
                        p += width;
                        continue;
                    }
                }
            }
        } else if n == name.len() {
            return true;
        }
        match star {
            Some((resume, at)) if at < name.len() => {
                let next = at + char_len(name[at]);
                star = Some((resume, next));
                p = resume;
                n = next;
            }
            _ => return false,
        }
    }
}

/// Whether a text pattern is one the walker handles; anything else (no
/// wildcard, trailing or doubled separator, `.`/`..`, embedded `**`, or an
/// invalid class) belongs to Python.
fn supported(pattern: &[u8]) -> bool {
    if !has_magic(pattern) || pattern.ends_with(b"/") || pattern.contains(&0) {
        return false;
    }
    let body = pattern.strip_prefix(b"/").unwrap_or(pattern);
    for component in body.split(|&byte| byte == b'/') {
        if component.is_empty() || component == b"." || component == b".." {
            return false;
        }
        if component == b"**" {
            continue;
        }
        if component.windows(2).any(|pair| pair == b"**") {
            return false;
        }
        let mut index = 0;
        while index < component.len() {
            if component[index] == b'[' {
                match parse_class(component, index) {
                    Some((_, _, next)) => index = next,
                    None => return false,
                }
            } else {
                index += 1;
            }
        }
    }
    true
}

struct Dir(*mut libc::DIR);

impl Drop for Dir {
    fn drop(&mut self) {
        unsafe { libc::closedir(self.0) };
    }
}

struct Walk {
    path: [u8; PATH_CAPACITY],
    length: usize,
    /// Where the reported path starts: after the `root_dir` prefix.
    origin: usize,
    include_hidden: bool,
    result: *mut PyObject,
}

impl Walk {
    fn join(&mut self, name: &[u8]) -> Result<(), Stop> {
        let separator = usize::from(self.length != 0 && self.path[self.length - 1] != b'/');
        // Keep one byte for the terminator of the C string.
        if self.length + separator + name.len() + 1 > PATH_CAPACITY {
            return Err(Stop::Unsupported);
        }
        if separator != 0 {
            self.path[self.length] = b'/';
        }
        let start = self.length + separator;
        self.path[start..start + name.len()].copy_from_slice(name);
        self.length = start + name.len();
        Ok(())
    }

    fn c_path(&mut self) -> *const c_char {
        self.path[self.length] = 0;
        self.path.as_ptr().cast::<c_char>()
    }

    fn append(&mut self) -> Result<(), Stop> {
        let item = unsafe {
            PyUnicode_FromStringAndSize(
                self.path.as_ptr().add(self.origin).cast::<c_char>(),
                (self.length - self.origin) as Py_ssize_t,
            )
        };
        if item.is_null() {
            return Err(Stop::Raised);
        }
        let status = unsafe { PyList_Append(self.result, item) };
        unsafe { Py_DecRef(item) };
        if status < 0 { Err(Stop::Raised) } else { Ok(()) }
    }

    fn is_dir(&mut self, name: &[u8], kind: u8) -> Result<bool, Stop> {
        if kind == libc::DT_DIR {
            return Ok(true);
        }
        if kind != libc::DT_LNK && kind != libc::DT_UNKNOWN {
            return Ok(false);
        }
        let saved = self.length;
        self.join(name)?;
        let mut info: libc::stat = unsafe { core::mem::zeroed() };
        let found = unsafe { libc::stat(self.c_path(), &mut info) } == 0;
        self.length = saved;
        Ok(found && info.st_mode & libc::S_IFMT == libc::S_IFDIR)
    }

    fn walk(&mut self, rest: &[u8]) -> Result<(), Stop> {
        let (component, tail) = match rest.iter().position(|&byte| byte == b'/') {
            Some(slash) => (&rest[..slash], Some(&rest[slash + 1..])),
            None => (rest, None),
        };
        // Without recursive=True, CPython treats a lone `**` as an ordinary star.
        let component: &[u8] = if component == b"**" { b"*" } else { component };
        let saved = self.length;

        if !has_magic(component) {
            self.join(component)?;
            let result = match tail {
                Some(tail) => self.walk(tail),
                None => {
                    let mut info: libc::stat = unsafe { core::mem::zeroed() };
                    if unsafe { libc::lstat(self.c_path(), &mut info) } == 0 {
                        self.append()
                    } else {
                        Ok(())
                    }
                }
            };
            self.length = saved;
            return result;
        }

        let directory = if self.length == 0 {
            unsafe { libc::opendir(c".".as_ptr()) }
        } else {
            unsafe { libc::opendir(self.c_path()) }
        };
        if directory.is_null() {
            return Ok(());
        }
        let directory = Dir(directory);
        let explicit_dot = component[0] == b'.';
        loop {
            let entry = unsafe { libc::readdir(directory.0) };
            if entry.is_null() {
                return Ok(());
            }
            let (name, kind) = unsafe {
                (
                    CStr::from_ptr((*entry).d_name.as_ptr()).to_bytes(),
                    (*entry).d_type,
                )
            };
            if name == b"." || name == b".." {
                continue;
            }
            if core::str::from_utf8(name).is_err() {
                return Err(Stop::Unsupported);
            }
            // CPython excludes hidden names unless the pattern component
            // starts with '.'.
            if !self.include_hidden && !explicit_dot && name[0] == b'.' {
                continue;
            }
            if !matches(component, name) {
                continue;
            }
            match tail {
                None => {
                    self.join(name)?;
                    let result = self.append();
                    self.length = saved;
                    result?;
                }
                Some(tail) => {
                    if self.is_dir(name, kind)? {
                        self.join(name)?;
                        let result = self.walk(tail);
                        self.length = saved;
                        result?;
                    }
                }
            }
        }
    }
}

unsafe extern "C" fn expand(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    into_return(unsafe { expand_arguments(args, nargs) })
}

unsafe fn expand_arguments(args: *mut *mut PyObject, nargs: Py_ssize_t) -> Outcome<Owned> {
    if nargs != 3 {
        return Err(Stop::Unsupported);
    }
    let include_hidden = unsafe { PyObject_IsTrue(*args.add(1)) };
    if include_hidden < 0 {
        return Err(Stop::Raised);
    }
    let mut size: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(*args, &mut size) };
    if data.is_null() {
        unsafe { PyErr_Clear() };
        return Err(Stop::Unsupported);
    }
    let pattern = unsafe { core::slice::from_raw_parts(data.cast::<u8>(), size as usize) };
    if !supported(pattern) {
        return Err(Stop::Unsupported);
    }
    let mut root_size: Py_ssize_t = 0;
    let root_data = unsafe { PyUnicode_AsUTF8AndSize(*args.add(2), &mut root_size) };
    if root_data.is_null() {
        unsafe { PyErr_Clear() };
        return Err(Stop::Unsupported);
    }
    let root = unsafe { core::slice::from_raw_parts(root_data.cast::<u8>(), root_size as usize) };
    if root.contains(&0) {
        return Err(Stop::Unsupported);
    }
    let result = unsafe { Owned::from_new_reference(PyList_New(0))? };
    let mut walk = Walk {
        path: [0; PATH_CAPACITY],
        length: 0,
        origin: 0,
        include_hidden: include_hidden != 0,
        result: result.as_ptr(),
    };
    let rest = match pattern.strip_prefix(b"/") {
        Some(rest) => {
            walk.path[0] = b'/';
            walk.length = 1;
            rest
        }
        None => {
            if !root.is_empty() {
                let separator = usize::from(root[root.len() - 1] != b'/');
                if root.len() + separator + 1 > PATH_CAPACITY {
                    return Err(Stop::Unsupported);
                }
                walk.path[..root.len()].copy_from_slice(root);
                if separator != 0 {
                    walk.path[root.len()] = b'/';
                }
                walk.length = root.len() + separator;
                walk.origin = walk.length;
            }
            pattern
        }
    };
    walk.walk(rest)?;
    Ok(result)
}

static METHODS: [cpython_binding::ffi::PyMethodDef; 2] = [
    fastcall(
        c"expand",
        expand,
        c"Expand a supported text pathname pattern under a root, or return None.",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(c"_glob_rs", c"Rust pathname expansion.", &METHODS);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__glob_rs() -> *mut PyObject {
    MODULE.init()
}
