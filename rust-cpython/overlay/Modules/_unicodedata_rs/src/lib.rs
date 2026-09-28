use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, PyErr_NoMemory, PyErr_Occurred, PyErr_SetString, PyExc_TypeError,
    PyExc_ValueError, PyLong_AsLong, PyLong_FromLong, PyMethodDef, PyMethodDefFuncPointer,
    PyModuleDef, PyModuleDef_Init, PyModuleDef_Slot, PyModuleDef_HEAD_INIT, PyObject,
    PyUnicode_FromStringAndSize, PyUnicode_GetLength, PyUnicode_ReadChar, Py_ssize_t,
    Py_NewRef, _Py_NoneStruct,
};
use icu_normalizer::{ComposingNormalizerBorrowed, DecomposingNormalizerBorrowed};
use icu_properties::props::{CanonicalCombiningClass, GeneralCategory};
use icu_properties::CodePointMapData;

unsafe fn unicode_string(object: *mut PyObject) -> Result<Option<String>, ()> {
    let length = unsafe { PyUnicode_GetLength(object) };
    if length < 0 {
        return Err(());
    }

    let mut value = String::new();
    if value.try_reserve_exact(length as usize).is_err() {
        unsafe { PyErr_NoMemory() };
        return Err(());
    }
    for index in 0..length {
        let codepoint = unsafe { PyUnicode_ReadChar(object, index) };
        if codepoint == u32::MAX {
            return Err(());
        }
        let Some(character) = char::from_u32(codepoint) else {
            return Ok(None);
        };
        value.push(character);
    }
    Ok(Some(value))
}

fn category_name(category: GeneralCategory) -> &'static str {
    match category {
        GeneralCategory::Unassigned => "Cn",
        GeneralCategory::UppercaseLetter => "Lu",
        GeneralCategory::LowercaseLetter => "Ll",
        GeneralCategory::TitlecaseLetter => "Lt",
        GeneralCategory::ModifierLetter => "Lm",
        GeneralCategory::OtherLetter => "Lo",
        GeneralCategory::NonspacingMark => "Mn",
        GeneralCategory::SpacingMark => "Mc",
        GeneralCategory::EnclosingMark => "Me",
        GeneralCategory::DecimalNumber => "Nd",
        GeneralCategory::LetterNumber => "Nl",
        GeneralCategory::OtherNumber => "No",
        GeneralCategory::SpaceSeparator => "Zs",
        GeneralCategory::LineSeparator => "Zl",
        GeneralCategory::ParagraphSeparator => "Zp",
        GeneralCategory::Control => "Cc",
        GeneralCategory::Format => "Cf",
        GeneralCategory::PrivateUse => "Co",
        GeneralCategory::Surrogate => "Cs",
        GeneralCategory::DashPunctuation => "Pd",
        GeneralCategory::OpenPunctuation => "Ps",
        GeneralCategory::ClosePunctuation => "Pe",
        GeneralCategory::ConnectorPunctuation => "Pc",
        GeneralCategory::InitialPunctuation => "Pi",
        GeneralCategory::FinalPunctuation => "Pf",
        GeneralCategory::OtherPunctuation => "Po",
        GeneralCategory::MathSymbol => "Sm",
        GeneralCategory::CurrencySymbol => "Sc",
        GeneralCategory::ModifierSymbol => "Sk",
        GeneralCategory::OtherSymbol => "So",
    }
}

unsafe fn codepoint_argument(object: *mut PyObject) -> Result<char, ()> {
    let value = unsafe { PyLong_AsLong(object) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        return Err(());
    }
    let Ok(value) = u32::try_from(value) else {
        unsafe {
            PyErr_SetString(PyExc_ValueError, c"invalid Unicode code point".as_ptr());
        }
        return Err(());
    };
    let Some(character) = char::from_u32(value) else {
        unsafe {
            PyErr_SetString(PyExc_ValueError, c"invalid Unicode code point".as_ptr());
        }
        return Err(());
    };
    Ok(character)
}

unsafe extern "C" fn category(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"category() takes one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let character = match unsafe { codepoint_argument(*args) } {
        Ok(character) => character,
        Err(()) => return ptr::null_mut(),
    };
    let category = CodePointMapData::<GeneralCategory>::new().get(character);
    unsafe { PyUnicode_FromStringAndSize(category_name(category).as_ptr().cast(), 2) }
}

unsafe extern "C" fn combining(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"combining() takes one argument".as_ptr());
        }
        return ptr::null_mut();
    }
    let character = match unsafe { codepoint_argument(*args) } {
        Ok(character) => character,
        Err(()) => return ptr::null_mut(),
    };
    let combining = CodePointMapData::<CanonicalCombiningClass>::new()
        .get(character)
        .to_icu4c_value();
    unsafe { PyLong_FromLong(combining as std::ffi::c_long) }
}

fn normalize(form: &str, input: &str) -> Option<String> {
    let normalized = match form {
        "NFC" => ComposingNormalizerBorrowed::new_nfc().normalize(input),
        "NFKC" => ComposingNormalizerBorrowed::new_nfkc().normalize(input),
        "NFD" => DecomposingNormalizerBorrowed::new_nfd().normalize(input),
        "NFKD" => DecomposingNormalizerBorrowed::new_nfkd().normalize(input),
        _ => return None,
    };
    Some(normalized.into_owned())
}

unsafe fn unicode_result(value: &str) -> *mut PyObject {
    let Ok(length) = Py_ssize_t::try_from(value.len()) else {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    };
    unsafe { PyUnicode_FromStringAndSize(value.as_ptr().cast::<c_char>(), length) }
}

unsafe extern "C" fn normalize_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        unsafe {
            PyErr_SetString(PyExc_TypeError, c"normalize() takes two arguments".as_ptr());
        }
        return ptr::null_mut();
    }
    let form = match unsafe { unicode_string(*args) } {
        Ok(Some(form)) => form,
        Ok(None) => {
            unsafe {
                PyErr_SetString(PyExc_ValueError, c"invalid normalization form".as_ptr());
            }
            return ptr::null_mut();
        }
        Err(()) => return ptr::null_mut(),
    };
    let input = match unsafe { unicode_string(*args.add(1)) } {
        Ok(Some(input)) => input,
        Ok(None) => return unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) },
        Err(()) => return ptr::null_mut(),
    };
    let Some(normalized) = normalize(&form, &input) else {
        unsafe {
            PyErr_SetString(PyExc_ValueError, c"invalid normalization form".as_ptr());
        }
        return ptr::null_mut();
    };
    unsafe { unicode_result(&normalized) }
}

pub extern "C" fn _unicodedata_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _unicodedata_rs_free(_object: *mut c_void) {}

struct ModuleDef(UnsafeCell<PyModuleDef>);

impl ModuleDef {
    fn init(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.0.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

struct ModuleSlots(UnsafeCell<[PyModuleDef_Slot; 2]>);

impl ModuleSlots {
    const fn as_mut_ptr(&self) -> *mut PyModuleDef_Slot {
        self.0.get().cast::<PyModuleDef_Slot>()
    }
}

unsafe impl Sync for ModuleSlots {}

static METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"category".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: category,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return the general category of a Unicode scalar value.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"combining".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: combining,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Return the canonical combining class of a Unicode scalar value.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"normalize".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: normalize_method,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Normalize text using a Unicode normalization form.".as_ptr()
            as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE_SLOTS: ModuleSlots = ModuleSlots(UnsafeCell::new([
    PyModuleDef_Slot {
        slot: 86,
        value: 2usize as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]));

static MODULE: ModuleDef = ModuleDef(UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_unicodedata_rs".as_ptr() as *mut c_char,
    m_doc: c"Unicode property and normalization helpers.".as_ptr() as *mut c_char,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut PyMethodDef,
    m_slots: MODULE_SLOTS.as_mut_ptr(),
    m_traverse: None,
    m_clear: Some(_unicodedata_rs_clear),
    m_free: Some(_unicodedata_rs_free),
}));

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__unicodedata_rs() -> *mut PyObject {
    MODULE.init()
}
