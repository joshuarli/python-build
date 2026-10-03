use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_Occurred, PyErr_SetString, PyExc_TypeError,
    PyLong_AsLong, PyLong_FromLong, PyMethodDef, PyMethodDefFuncPointer, PyModuleDef,
    PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyModuleDef_Slot, PyObject, PyTuple_New, PyTuple_SetItem,
    PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize, Py_ssize_t,
};

fn leap(year: i64) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn days_in_month(year: i64, month: i64) -> i64 {
    match month {
        2 => if leap(year) { 29 } else { 28 },
        4 | 6 | 9 | 11 => 30,
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        _ => 0,
    }
}

fn ordinal(year: i64, month: i64, day: i64) -> Option<i64> {
    if !(1..=9999).contains(&year) || !(1..=days_in_month(year, month)).contains(&day) {
        return None;
    }
    let before = year - 1;
    let mut ordinal = before * 365 + before / 4 - before / 100 + before / 400;
    for current in 1..month {
        ordinal += days_in_month(year, current);
    }
    Some(ordinal + day)
}

fn from_ordinal(value: i64) -> Option<[i64; 3]> {
    if !(1..=3_652_059).contains(&value) {
        return None;
    }
    let mut low = 1;
    let mut high = 10000;
    while low + 1 < high {
        let middle = (low + high) / 2;
        if ordinal(middle, 1, 1).is_some_and(|start| start <= value) {
            low = middle;
        } else {
            high = middle;
        }
    }
    let mut remaining = value - ordinal(low, 1, 1)? + 1;
    let mut month = 1;
    while remaining > days_in_month(low, month) {
        remaining -= days_in_month(low, month);
        month += 1;
    }
    Some([low, month, remaining])
}

fn parse_decimal(bytes: &[u8]) -> Option<i64> {
    if bytes.is_empty() || !bytes.iter().all(u8::is_ascii_digit) {
        return None;
    }
    bytes.iter().try_fold(0i64, |value, byte| value.checked_mul(10)?.checked_add(i64::from(*byte - b'0')))
}

fn parse_date_bytes(bytes: &[u8]) -> Option<[i64; 3]> {
    if bytes.len() != 10 || bytes[4] != b'-' || bytes[7] != b'-' {
        return None;
    }
    let parts = [parse_decimal(&bytes[..4])?, parse_decimal(&bytes[5..7])?, parse_decimal(&bytes[8..])?];
    ordinal(parts[0], parts[1], parts[2])?;
    Some(parts)
}

fn parse_time_bytes(bytes: &[u8]) -> Option<[i64; 4]> {
    let bytes = bytes.strip_prefix(b"T").unwrap_or(bytes);
    if bytes.len() != 8 && bytes.len() != 15 {
        return None;
    }
    if bytes[2] != b':' || bytes[5] != b':' || (bytes.len() == 15 && bytes[8] != b'.') {
        return None;
    }
    let hour = parse_decimal(&bytes[..2])?;
    let minute = parse_decimal(&bytes[3..5])?;
    let second = parse_decimal(&bytes[6..8])?;
    let microsecond = if bytes.len() == 15 { parse_decimal(&bytes[9..])? } else { 0 };
    if hour > 23 || minute > 59 || second > 59 {
        return None;
    }
    Some([hour, minute, second, microsecond])
}

unsafe fn read_text(arg: *mut PyObject) -> Option<Vec<u8>> {
    let mut length: Py_ssize_t = 0;
    let bytes = unsafe { PyUnicode_AsUTF8AndSize(arg, &mut length) };
    if bytes.is_null() || length < 0 {
        return None;
    }
    Some(unsafe { slice::from_raw_parts(bytes.cast::<u8>(), length as usize) }.to_vec())
}

unsafe fn read_ints<const N: usize>(args: *mut *mut PyObject, count: Py_ssize_t) -> Option<[i64; N]> {
    if count != N as Py_ssize_t {
        unsafe { PyErr_SetString(PyExc_TypeError, c"wrong number of datetime fields".as_ptr()) };
        return None;
    }
    let mut fields = [0; N];
    for (index, field) in fields.iter_mut().enumerate() {
        let value = unsafe { PyLong_AsLong(*args.add(index)) };
        if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
            return None;
        }
        *field = value as i64;
    }
    Some(fields)
}

unsafe fn tuple(values: &[i64]) -> *mut PyObject {
    let result = unsafe { PyTuple_New(values.len() as Py_ssize_t) };
    if result.is_null() {
        return result;
    }
    for (index, value) in values.iter().enumerate() {
        let item = unsafe { PyLong_FromLong(*value as _) };
        if item.is_null() {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(result, index as Py_ssize_t, item) } != 0 {
            unsafe { Py_DecRef(result) };
            return ptr::null_mut();
        }
    }
    result
}

unsafe fn unicode(value: &str) -> *mut PyObject {
    unsafe { PyUnicode_FromStringAndSize(value.as_ptr().cast(), value.len() as Py_ssize_t) }
}

unsafe extern "C" fn parse_date(_module: *mut PyObject, args: *mut *mut PyObject, count: Py_ssize_t) -> *mut PyObject {
    if count != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"parse_date() requires one string".as_ptr()) };
        return ptr::null_mut();
    }
    let Some(bytes) = (unsafe { read_text(*args) }) else { return ptr::null_mut() };
    match parse_date_bytes(&bytes) {
        Some(fields) => unsafe { tuple(&fields) },
        None => unsafe { tuple(&[]) },
    }
}

unsafe extern "C" fn parse_time(_module: *mut PyObject, args: *mut *mut PyObject, count: Py_ssize_t) -> *mut PyObject {
    if count != 1 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"parse_time() requires one string".as_ptr()) };
        return ptr::null_mut();
    }
    let Some(bytes) = (unsafe { read_text(*args) }) else { return ptr::null_mut() };
    match parse_time_bytes(&bytes) {
        Some(fields) => unsafe { tuple(&fields) },
        None => unsafe { tuple(&[]) },
    }
}

unsafe extern "C" fn format_date(_module: *mut PyObject, args: *mut *mut PyObject, count: Py_ssize_t) -> *mut PyObject {
    let Some([year, month, day]) = (unsafe { read_ints::<3>(args, count) }) else { return ptr::null_mut() };
    unsafe { unicode(&format!("{year:04}-{month:02}-{day:02}")) }
}

unsafe extern "C" fn format_time(_module: *mut PyObject, args: *mut *mut PyObject, count: Py_ssize_t) -> *mut PyObject {
    let Some([hour, minute, second, microsecond, spec]) = (unsafe { read_ints::<5>(args, count) }) else { return ptr::null_mut() };
    let result = match spec {
        0 => format!("{hour:02}"),
        1 => format!("{hour:02}:{minute:02}"),
        2 => format!("{hour:02}:{minute:02}:{second:02}"),
        3 => format!("{hour:02}:{minute:02}:{second:02}.{:03}", microsecond / 1000),
        4 => format!("{hour:02}:{minute:02}:{second:02}.{microsecond:06}"),
        _ => return unsafe { tuple(&[]) },
    };
    unsafe { unicode(&result) }
}

unsafe extern "C" fn format_datetime(_module: *mut PyObject, args: *mut *mut PyObject, count: Py_ssize_t) -> *mut PyObject {
    let Some([year, month, day, hour, minute, second, microsecond, separator, spec]) =
        (unsafe { read_ints::<9>(args, count) }) else { return ptr::null_mut() };
    let Some(separator) = char::from_u32(separator as u32) else {
        return unsafe { tuple(&[]) };
    };
    let time = match spec {
        0 => format!("{hour:02}"),
        1 => format!("{hour:02}:{minute:02}"),
        2 => format!("{hour:02}:{minute:02}:{second:02}"),
        3 => format!("{hour:02}:{minute:02}:{second:02}.{:03}", microsecond / 1000),
        4 => format!("{hour:02}:{minute:02}:{second:02}.{microsecond:06}"),
        _ => return unsafe { tuple(&[]) },
    };
    unsafe { unicode(&format!("{year:04}-{month:02}-{day:02}{separator}{time}")) }
}

unsafe extern "C" fn add_date(_module: *mut PyObject, args: *mut *mut PyObject, count: Py_ssize_t) -> *mut PyObject {
    let Some([year, month, day, days]) = (unsafe { read_ints::<4>(args, count) }) else { return ptr::null_mut() };
    let result = ordinal(year, month, day).and_then(|value| from_ordinal(value + days));
    match result {
        Some(fields) => unsafe { tuple(&fields) },
        None => unsafe { tuple(&[]) },
    }
}

unsafe extern "C" fn add_datetime(_module: *mut PyObject, args: *mut *mut PyObject, count: Py_ssize_t) -> *mut PyObject {
    let Some([year, month, day, hour, minute, second, microsecond, days, seconds, micros, factor]) =
        (unsafe { read_ints::<11>(args, count) }) else { return ptr::null_mut() };
    let Some(ordinal) = ordinal(year, month, day) else { return unsafe { tuple(&[]) } };
    let day_us = 86_400_000_000i128;
    let base = (ordinal as i128 - 1) * day_us
        + (hour as i128 * 3600 + minute as i128 * 60 + second as i128) * 1_000_000
        + microsecond as i128;
    let delta = days as i128 * day_us + seconds as i128 * 1_000_000 + micros as i128;
    let total = base + factor as i128 * delta;
    let new_ordinal = total.div_euclid(day_us) + 1;
    if !(1..=3_652_059).contains(&new_ordinal) {
        return unsafe { tuple(&[]) };
    }
    let Some([year, month, day]) = from_ordinal(new_ordinal as i64) else { return unsafe { tuple(&[]) } };
    let remainder = total.rem_euclid(day_us) as i64;
    unsafe { tuple(&[year, month, day, remainder / 3_600_000_000,
        remainder / 60_000_000 % 60, remainder / 1_000_000 % 60, remainder % 1_000_000]) }
}

pub extern "C" fn _datetime_rs_clear(_obj: *mut PyObject) -> c_int { 0 }
pub extern "C" fn _datetime_rs_free(_obj: *mut c_void) {}

pub struct ModuleDef { ffi: UnsafeCell<PyModuleDef> }
unsafe impl Sync for ModuleDef {}

struct ModuleSlots([PyModuleDef_Slot; 3]);
unsafe impl Sync for ModuleSlots {}

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int { 0 }

static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    PyModuleDef_Slot {
        slot: 85,
        value: module_exec as *const () as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 86,
        value: 2 as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]);

pub static METHODS: [PyMethodDef; 8] = [
    method(c"parse_date", parse_date),
    method(c"parse_time", parse_time),
    method(c"format_date", format_date),
    method(c"format_time", format_time),
    method(c"format_datetime", format_datetime),
    method(c"add_date", add_date),
    method(c"add_datetime", add_datetime),
    PyMethodDef::zeroed(),
];

const fn method(name: &'static std::ffi::CStr, function: unsafe extern "C" fn(*mut PyObject, *mut *mut PyObject, Py_ssize_t) -> *mut PyObject) -> PyMethodDef {
    PyMethodDef { ml_name: name.as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: function },
        ml_flags: METH_FASTCALL, ml_doc: ptr::null_mut() }
}

pub static MODULE: ModuleDef = ModuleDef { ffi: UnsafeCell::new(PyModuleDef {
    m_base: PyModuleDef_HEAD_INIT,
    m_name: c"_datetime_rs".as_ptr() as *mut _,
    m_doc: c"Rust datetime field operations.".as_ptr() as *mut _,
    m_size: 0,
    m_methods: METHODS.as_ptr() as *mut _,
    m_slots: MODULE_SLOTS.0.as_ptr() as *mut PyModuleDef_Slot,
    m_traverse: None,
    m_clear: Some(_datetime_rs_clear),
    m_free: Some(_datetime_rs_free),
}) };

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__datetime_rs() -> *mut PyObject {
    unsafe { PyModuleDef_Init(MODULE.ffi.get()) }
}
