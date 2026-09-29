use std::cell::UnsafeCell;
use std::ffi::{CStr, c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyList_Append;
use cpython_sys::PyList_New;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_NewRef;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;

/// A path component of the pattern.
enum Component<'a> {
    Literal(&'a str),
    Magic(glob::Pattern, bool),
}

/// Why a walk stopped early.
enum Stop {
    /// The pattern or a directory entry needs the Python implementation.
    Fallback,
    /// A Python exception is set.
    Error,
}

struct Walk<'a> {
    components: Vec<Component<'a>>,
    options: glob::MatchOptions,
    include_hidden: bool,
    /// The path being built; always valid UTF-8.
    path: Vec<u8>,
    result: *mut PyObject,
}

struct Dir(*mut libc::DIR);

impl Drop for Dir {
    fn drop(&mut self) {
        unsafe { libc::closedir(self.0) };
    }
}

impl Walk<'_> {
    fn join(&mut self, name: &[u8]) {
        if !self.path.is_empty() && self.path.last() != Some(&b'/') {
            self.path.push(b'/');
        }
        self.path.extend_from_slice(name);
    }

    fn append_path(&mut self) -> Result<(), Stop> {
        let item = unsafe {
            PyUnicode_FromStringAndSize(
                self.path.as_ptr().cast::<c_char>(),
                self.path.len() as Py_ssize_t,
            )
        };
        if item.is_null() {
            return Err(Stop::Error);
        }
        let status = unsafe { PyList_Append(self.result, item) };
        unsafe { Py_DecRef(item) };
        if status < 0 { Err(Stop::Error) } else { Ok(()) }
    }

    /// Runs `check` on the path built so far as a C string.
    fn with_c_path<T>(&mut self, check: impl FnOnce(*const c_char) -> T) -> T {
        self.path.push(0);
        let value = check(self.path.as_ptr().cast::<c_char>());
        self.path.pop();
        value
    }

    fn is_dir(&mut self, name: &[u8], d_type: u8) -> bool {
        if d_type == libc::DT_DIR {
            return true;
        }
        if d_type != libc::DT_LNK && d_type != libc::DT_UNKNOWN {
            return false;
        }
        let length = self.path.len();
        self.join(name);
        let answer = self.with_c_path(|path| {
            let mut info: libc::stat = unsafe { std::mem::zeroed() };
            unsafe { libc::stat(path, &mut info) == 0 && info.st_mode & libc::S_IFMT == libc::S_IFDIR }
        });
        self.path.truncate(length);
        answer
    }

    fn walk(&mut self, index: usize) -> Result<(), Stop> {
        let last = index + 1 == self.components.len();
        let length = self.path.len();
        // Components borrow the pattern, not `self`, so copy the small
        // handle out before mutating the path buffer.
        let (literal, pattern, starts_with_dot) = match &self.components[index] {
            Component::Literal(text) => (Some(*text), None, false),
            Component::Magic(pattern, dot) => (None, Some(pattern as *const glob::Pattern), *dot),
        };
        if let Some(text) = literal {
            self.join(text.as_bytes());
            let result = if last {
                let exists = self.with_c_path(|path| {
                    let mut info: libc::stat = unsafe { std::mem::zeroed() };
                    unsafe { libc::lstat(path, &mut info) == 0 }
                });
                if exists { self.append_path() } else { Ok(()) }
            } else {
                self.walk(index + 1)
            };
            self.path.truncate(length);
            return result;
        }
        let pattern = unsafe { &*pattern.unwrap() };
        let directory = if self.path.is_empty() {
            unsafe { libc::opendir(c".".as_ptr()) }
        } else {
            self.with_c_path(|path| unsafe { libc::opendir(path) })
        };
        if directory.is_null() {
            return Ok(());
        }
        let directory = Dir(directory);
        loop {
            let entry = unsafe { libc::readdir(directory.0) };
            if entry.is_null() {
                return Ok(());
            }
            let (name, d_type) = unsafe {
                (
                    CStr::from_ptr((*entry).d_name.as_ptr()).to_bytes(),
                    (*entry).d_type,
                )
            };
            if name == b"." || name == b".." {
                continue;
            }
            let Ok(text) = std::str::from_utf8(name) else {
                return Err(Stop::Fallback);
            };
            if !self.include_hidden && !starts_with_dot && name[0] == b'.' {
                continue;
            }
            if !pattern.matches_with(text, self.options) {
                continue;
            }
            if last {
                self.join(name);
                let result = self.append_path();
                self.path.truncate(length);
                result?;
            } else if self.is_dir(name, d_type) {
                self.join(name);
                let result = self.walk(index + 1);
                self.path.truncate(length);
                result?;
            }
        }
    }
}

fn has_magic(text: &str) -> bool {
    text.bytes().any(|byte| matches!(byte, b'*' | b'?' | b'['))
}

/// Build the walker for the pattern, or None when Python must handle it.
fn prepare(pattern: &str, include_hidden: bool) -> Option<Walk<'_>> {
    if !has_magic(pattern) || pattern.ends_with('/') || pattern.contains('\0') {
        return None;
    }
    let mut components = Vec::new();
    let mut root = false;
    for (index, part) in pattern.split('/').enumerate() {
        if part.is_empty() {
            if index != 0 {
                return None;
            }
            root = true;
            continue;
        }
        if part == "." || part == ".." {
            return None;
        }
        // Without recursive=True, CPython treats a lone `**` as an ordinary star.
        let part = if part == "**" {
            "*"
        } else if part.contains("**") {
            return None;
        } else {
            part
        };
        if has_magic(part) {
            let compiled = glob::Pattern::new(part).ok()?;
            components.push(Component::Magic(compiled, part.starts_with('.')));
        } else {
            components.push(Component::Literal(part));
        }
    }
    Some(Walk {
        components,
        options: glob::MatchOptions {
            case_sensitive: true,
            require_literal_separator: true,
            // The hidden-name rule is applied per component above.
            require_literal_leading_dot: false,
        },
        include_hidden,
        path: if root { b"/".to_vec() } else { Vec::new() },
        result: ptr::null_mut(),
    })
}

unsafe extern "C" fn expand(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    let none = || unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) };
    if nargs != 2 {
        return none();
    }
    let hidden = unsafe { PyObject_IsTrue(*args.add(1)) };
    if hidden < 0 {
        return ptr::null_mut();
    }
    let mut size: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(*args, &mut size) };
    if data.is_null() {
        // Lone surrogates cannot be encoded; Python handles them.
        unsafe { PyErr_Clear() };
        return none();
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), size as usize) };
    let pattern = unsafe { std::str::from_utf8_unchecked(bytes) };
    let Some(mut walk) = prepare(pattern, hidden != 0) else {
        return none();
    };
    walk.result = unsafe { PyList_New(0) };
    if walk.result.is_null() {
        return ptr::null_mut();
    }
    match walk.walk(0) {
        Ok(()) => walk.result,
        Err(Stop::Fallback) => {
            unsafe { Py_DecRef(walk.result) };
            none()
        }
        Err(Stop::Error) => {
            unsafe { Py_DecRef(walk.result) };
            ptr::null_mut()
        }
    }
}

pub extern "C" fn _glob_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _glob_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _GLOB_RS_MODULE_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"expand".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: expand,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Expand a supported text pathname pattern, or return None.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _GLOB_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_glob_rs".as_ptr() as *mut _,
        m_doc: c"Rust pathname expansion using the glob crate.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_GLOB_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_glob_rs_clear),
        m_free: Some(_glob_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__glob_rs() -> *mut PyObject {
    _GLOB_RS_MODULE.init_multi_phase()
}
