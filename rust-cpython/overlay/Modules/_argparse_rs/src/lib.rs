use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use clap_lex::RawArgs;
use cpython_sys::METH_FASTCALL;
use cpython_sys::PyList_Append;
use cpython_sys::PyList_New;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_Slot;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_IsTrue;
use cpython_sys::PyTuple_GetItem;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyTuple_Size;
use cpython_sys::PyUnicode_AsUTF8AndSize;
use cpython_sys::PyUnicode_FromStringAndSize;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_NewRef;
use cpython_sys::Py_ssize_t;
use cpython_sys::_Py_NoneStruct;

const PY_MOD_MULTIPLE_INTERPRETERS_SLOT: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: *mut c_void = 2usize as *mut c_void;

struct OptionCandidate {
    option: String,
    separator: Option<String>,
    explicit_argument: Option<String>,
}

fn add_candidate(
    candidates: &mut Vec<OptionCandidate>,
    option: &str,
    separator: Option<&str>,
    explicit_argument: Option<&str>,
) {
    candidates.push(OptionCandidate {
        option: option.to_owned(),
        separator: separator.map(str::to_owned),
        explicit_argument: explicit_argument.map(str::to_owned),
    });
}

fn scan_option(
    argument: &str,
    options: &[String],
    allow_abbrev: bool,
) -> Result<Vec<OptionCandidate>, ()> {
    let mut candidates = Vec::new();
    candidates.try_reserve(options.len()).map_err(|_| ())?;
    if !argument.starts_with('-') {
        return Ok(candidates);
    }

    if let Some(option) = options.iter().find(|option| option.as_str() == argument) {
        add_candidate(&mut candidates, option, None, None);
        return Ok(candidates);
    }

    if let Some((option_prefix, explicit_argument)) = argument.split_once('=')
        && let Some(option) = options
            .iter()
            .find(|option| option.as_str() == option_prefix)
    {
        add_candidate(&mut candidates, option, Some("="), Some(explicit_argument));
        return Ok(candidates);
    }

    if argument == "--" {
        if allow_abbrev {
            for option in options.iter().filter(|option| option.starts_with("--")) {
                add_candidate(&mut candidates, option, None, None);
            }
        }
        return Ok(candidates);
    }

    let raw = RawArgs::new([argument]);
    let mut cursor = raw.cursor();
    let Some(parsed) = raw.next(&mut cursor) else {
        return Ok(candidates);
    };

    if let Some((flag, explicit_argument)) = parsed.to_long() {
        let Ok(flag) = flag else {
            return Ok(candidates);
        };
        let option_prefix = format!("--{flag}");
        let (separator, explicit_argument) = match explicit_argument {
            Some(value) => {
                let Some(value) = value.to_str() else {
                    return Ok(candidates);
                };
                (Some("="), Some(value))
            }
            None => (None, None),
        };
        if allow_abbrev {
            for option in options
                .iter()
                .filter(|option| option.starts_with(&option_prefix))
            {
                add_candidate(&mut candidates, option, separator, explicit_argument);
            }
        }
        return Ok(candidates);
    }

    if let Some(mut short_flags) = parsed.to_short() {
        let Some(Ok(flag)) = short_flags.next_flag() else {
            return Ok(candidates);
        };
        let short_option = format!("-{flag}");
        let short_explicit_argument = short_flags
            .next_value_os()
            .and_then(|value| value.to_str())
            .unwrap_or("");
        let (option_prefix, separator, explicit_argument) = match argument.split_once('=') {
            Some((prefix, value)) => (prefix, Some("="), Some(value)),
            None => (argument, None, None),
        };
        for option in options {
            if option == &short_option {
                add_candidate(
                    &mut candidates,
                    option,
                    Some(""),
                    Some(short_explicit_argument),
                );
            } else if allow_abbrev && option.starts_with(option_prefix) {
                add_candidate(&mut candidates, option, separator, explicit_argument);
            }
        }
    }

    Ok(candidates)
}

unsafe fn read_unicode(object: *mut PyObject) -> Option<String> {
    let mut length: Py_ssize_t = 0;
    let data = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if data.is_null() || length < 0 {
        return None;
    }
    let bytes = unsafe { std::slice::from_raw_parts(data.cast::<u8>(), length as usize) };
    let text = unsafe { std::str::from_utf8_unchecked(bytes) };
    Some(text.to_owned())
}

unsafe fn new_unicode(text: &str) -> *mut PyObject {
    let Ok(length) = Py_ssize_t::try_from(text.len()) else {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    };
    unsafe { PyUnicode_FromStringAndSize(text.as_ptr().cast::<c_char>(), length) }
}

unsafe fn new_candidate(candidate: &OptionCandidate) -> *mut PyObject {
    let result = unsafe { PyTuple_New(3) };
    if result.is_null() {
        return ptr::null_mut();
    }

    let option = unsafe { new_unicode(&candidate.option) };
    if option.is_null() {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(result, 0, option) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }

    let separator = match &candidate.separator {
        Some(separator) => unsafe { new_unicode(separator) },
        None => unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
    };
    if separator.is_null() {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(result, 1, separator) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }

    let explicit_argument = match &candidate.explicit_argument {
        Some(argument) => unsafe { new_unicode(argument) },
        None => unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
    };
    if explicit_argument.is_null() {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }
    if unsafe { PyTuple_SetItem(result, 2, explicit_argument) } != 0 {
        unsafe { Py_DecRef(result) };
        return ptr::null_mut();
    }

    result
}

unsafe extern "C" fn option_candidates(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"option_candidates() takes exactly three arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }

    let Some(argument) = (unsafe { read_unicode(*args) }) else {
        return ptr::null_mut();
    };

    let options_object = unsafe { *args.add(1) };
    let option_count = unsafe { PyTuple_Size(options_object) };
    if option_count < 0 {
        return ptr::null_mut();
    }
    let mut options = Vec::new();
    if options.try_reserve(option_count as usize).is_err() {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    for index in 0..option_count {
        let option_object = unsafe { PyTuple_GetItem(options_object, index) };
        if option_object.is_null() {
            return ptr::null_mut();
        }
        let Some(option) = (unsafe { read_unicode(option_object) }) else {
            return ptr::null_mut();
        };
        options.push(option);
    }

    let allow_abbrev = unsafe { PyObject_IsTrue(*args.add(2)) };
    if allow_abbrev < 0 {
        return ptr::null_mut();
    }

    let candidates = match scan_option(&argument, &options, allow_abbrev != 0) {
        Ok(candidates) => candidates,
        Err(()) => {
            unsafe { PyErr_NoMemory() };
            return ptr::null_mut();
        }
    };

    let result = unsafe { PyList_New(0) };
    if result.is_null() {
        return ptr::null_mut();
    }
    for candidate in &candidates {
        let item = unsafe { new_candidate(candidate) };
        if item.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyList_Append(result, item) } < 0 {
            unsafe {
                Py_DecRef(item);
                Py_DecRef(result);
            }
            return ptr::null_mut();
        }
        unsafe { Py_DecRef(item) };
    }
    result
}

extern "C" fn module_clear(_module: *mut PyObject) -> c_int {
    0
}

extern "C" fn module_free(_module: *mut c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
    slots: [PyModuleDef_Slot; 2],
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe {
            (*self.ffi.get()).m_slots = self.slots.as_ptr() as *mut PyModuleDef_Slot;
            PyModuleDef_Init(self.ffi.get())
        }
    }
}

unsafe impl Sync for ModuleDef {}

static MODULE_METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"option_candidates".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: option_candidates,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Find configured option tokens using Rust command-line lexing".as_ptr()
            as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_argparse_rs".as_ptr() as *mut _,
        m_doc: c"Rust option-token lexer used by argparse".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(module_clear),
        m_free: Some(module_free),
    }),
    slots: [
        PyModuleDef_Slot {
            slot: PY_MOD_MULTIPLE_INTERPRETERS_SLOT,
            value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED,
        },
        PyModuleDef_Slot {
            slot: 0,
            value: ptr::null_mut(),
        },
    ],
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__argparse_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
