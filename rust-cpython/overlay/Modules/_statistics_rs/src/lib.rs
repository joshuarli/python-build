//! Exact-int summary helpers for `statistics`.
//!
//! The crate is `no_std` and declares the few C-API entry points it uses
//! itself: linking Rust `std` (and `cpython-sys`, which depends on it) adds
//! roughly 400 KiB of panic, backtrace, and I/O code that is mapped and
//! partly dirtied on every import of the extension.
#![no_std]

use core::ptr;

use cpython_binding::ffi::{
    PyBool_FromLong, PyErr_Clear, PyErr_NoMemory, PyErr_Occurred, PyList_GetItem, PyList_Size,
    PyList_Type, PyLong_AsLongLong, PyLong_FromLongLong, PyLong_FromSsize_t, PyLong_Type,
    PyMem_Free, PyMem_Malloc, PyMethodDef, PyObject, PyTuple_GetItem, PyTuple_New,
    PyTuple_SetItem, PyTuple_Size, PyTuple_Type, PyTypeObject, Py_DecRef, Py_ssize_t,
};
use cpython_binding::{Module, fastcall, method_table_end};

unsafe fn is_exact_type(object: *mut PyObject, expected: *mut PyTypeObject) -> Result<bool, ()> {
    Ok(unsafe { (*object).ob_type } == expected)
}

unsafe fn sequence_info(object: *mut PyObject) -> Result<Option<(bool, usize)>, ()> {
    let list_type = ptr::addr_of_mut!(PyList_Type);
    if unsafe { is_exact_type(object, list_type) }? {
        let length = unsafe { PyList_Size(object) };
        if length < 0 {
            return Err(());
        }
        return Ok(Some((true, length as usize)));
    }

    let tuple_type = ptr::addr_of_mut!(PyTuple_Type);
    if unsafe { is_exact_type(object, tuple_type) }? {
        let length = unsafe { PyTuple_Size(object) };
        if length < 0 {
            return Err(());
        }
        return Ok(Some((false, length as usize)));
    }

    Ok(None)
}

unsafe fn sequence_item(object: *mut PyObject, is_list: bool, index: usize) -> Result<*mut PyObject, ()> {
    let item = if is_list {
        unsafe { PyList_GetItem(object, index as Py_ssize_t) }
    } else {
        unsafe { PyTuple_GetItem(object, index as Py_ssize_t) }
    };
    if item.is_null() {
        Err(())
    } else {
        Ok(item)
    }
}

unsafe fn exact_i64(object: *mut PyObject) -> Result<Option<i64>, ()> {
    let integer_type = ptr::addr_of_mut!(PyLong_Type);
    if !unsafe { is_exact_type(object, integer_type) }? {
        return Ok(None);
    }
    let value = unsafe { PyLong_AsLongLong(object) };
    if value == -1 && !unsafe { PyErr_Occurred() }.is_null() {
        unsafe { PyErr_Clear() };
        return Ok(None);
    }
    Ok(Some(value))
}

fn no_fast_path() -> *mut PyObject {
    unsafe { PyBool_FromLong(0) }
}

unsafe fn return_integer_tuple(values: &[i64]) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(values.len() as Py_ssize_t) };
    if tuple.is_null() {
        return tuple;
    }
    for (index, value) in values.iter().enumerate() {
        let item = unsafe { PyLong_FromLongLong(*value) };
        if item.is_null() {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, item) } != 0 {
            unsafe {
                Py_DecRef(item);
                Py_DecRef(tuple);
            }
            return ptr::null_mut();
        }
    }
    tuple
}

unsafe fn integer_moments(data: *mut PyObject) -> Result<Option<(i64, i64, i64)>, ()> {
    let Some((is_list, length)) = (unsafe { sequence_info(data) })? else {
        return Ok(None);
    };
    if length == 0 {
        return Ok(None);
    }

    let mut total = 0_i64;
    let mut squares = 0_i64;
    for index in 0..length {
        let item = unsafe { sequence_item(data, is_list, index) }?;
        let Some(value) = (unsafe { exact_i64(item) })? else {
            return Ok(None);
        };
        let Some(square) = value.checked_mul(value) else {
            return Ok(None);
        };
        let Some(next_total) = total.checked_add(value) else {
            return Ok(None);
        };
        let Some(next_squares) = squares.checked_add(square) else {
            return Ok(None);
        };
        total = next_total;
        squares = next_squares;
    }

    Ok(Some((total, squares, length as i64)))
}

unsafe extern "C" fn integer_moments_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return no_fast_path();
    }
    match unsafe { integer_moments(*args) } {
        Ok(Some((total, squares, count))) => unsafe {
            return_integer_tuple(&[total, squares, count])
        },
        Ok(None) => no_fast_path(),
        Err(()) => ptr::null_mut(),
    }
}

trait Packed: Copy + Ord {
    fn pack(offset: u64) -> Self;
    fn unpack(self) -> u64;
}

impl Packed for u16 {
    fn pack(offset: u64) -> Self {
        offset as u16
    }
    fn unpack(self) -> u64 {
        u64::from(self)
    }
}

impl Packed for u32 {
    fn pack(offset: u64) -> Self {
        offset as u32
    }
    fn unpack(self) -> u64 {
        u64::from(self)
    }
}

impl Packed for u64 {
    fn pack(offset: u64) -> Self {
        offset
    }
    fn unpack(self) -> u64 {
        self
    }
}

unsafe fn value_range(
    data: *mut PyObject,
    is_list: bool,
    length: usize,
) -> Result<Option<(i64, i64)>, ()> {
    let mut low = i64::MAX;
    let mut high = i64::MIN;
    for index in 0..length {
        let item = unsafe { sequence_item(data, is_list, index) }?;
        let Some(value) = (unsafe { exact_i64(item) })? else {
            return Ok(None);
        };
        low = low.min(value);
        high = high.max(value);
    }
    Ok(Some((low, high)))
}

unsafe fn fill_packed<T: Packed>(
    data: *mut PyObject,
    is_list: bool,
    length: usize,
    minimum: i64,
    buffer: *mut T,
) -> Result<bool, ()> {
    for index in 0..length {
        let item = unsafe { sequence_item(data, is_list, index) }?;
        let Some(value) = (unsafe { exact_i64(item) })? else {
            return Ok(false);
        };
        unsafe { buffer.add(index).write(T::pack(value.wrapping_sub(minimum) as u64)) };
    }
    Ok(true)
}

/// Locate the sequence positions of the stable-sort ranks `(length - 1) / 2`
/// and `length / 2` given a scratch copy of the packed values.
unsafe fn find_ranks<T: Packed>(
    data: *mut PyObject,
    is_list: bool,
    length: usize,
    minimum: i64,
    packed: &mut [T],
) -> Result<Option<(usize, usize)>, ()> {
    let rank_low = (length - 1) / 2;
    let rank_high = length / 2;
    let (below, middle, above) = packed.select_nth_unstable(rank_low);
    let value_low = *middle;
    let value_high = match above.iter().min() {
        Some(smallest) if rank_high != rank_low => *smallest,
        _ => value_low,
    };
    let less_than_low = below.iter().filter(|value| **value < value_low).count();
    // Rank `rank_high` is the first occurrence of a strictly larger value, or
    // the next occurrence of the same value.
    let skip_low = rank_low - less_than_low;
    let skip_high = if rank_high == rank_low {
        skip_low
    } else if value_high == value_low {
        skip_low + 1
    } else {
        0
    };

    let target_low = minimum.wrapping_add(value_low.unpack() as i64);
    let target_high = minimum.wrapping_add(value_high.unpack() as i64);
    let mut seen_low = 0;
    let mut seen_high = 0;
    let mut found_low = None;
    let mut found_high = None;
    for index in 0..length {
        let item = unsafe { sequence_item(data, is_list, index) }?;
        let Some(value) = (unsafe { exact_i64(item) })? else {
            return Ok(None);
        };
        if found_low.is_none() && value == target_low {
            if seen_low == skip_low {
                found_low = Some(index);
            }
            seen_low += 1;
        }
        if found_high.is_none() && value == target_high {
            if seen_high == skip_high {
                found_high = Some(index);
            }
            seen_high += 1;
        }
        if found_low.is_some() && found_high.is_some() {
            break;
        }
    }
    match (found_low, found_high) {
        (Some(low), Some(high)) => Ok(Some((low, high))),
        _ => Ok(None),
    }
}

/// Median ranks by selection over offsets packed into the narrowest unsigned
/// width that holds the value range, so the scratch buffer is a fraction of a
/// `(value, index)` sort and is released before returning.
unsafe fn median_ranks<T: Packed>(
    data: *mut PyObject,
    is_list: bool,
    length: usize,
    minimum: i64,
) -> Result<Option<(usize, usize)>, ()> {
    let Some(bytes) = length.checked_mul(size_of::<T>()) else {
        unsafe { PyErr_NoMemory() };
        return Err(());
    };
    let buffer = unsafe { PyMem_Malloc(bytes) }.cast::<T>();
    if buffer.is_null() {
        unsafe { PyErr_NoMemory() };
        return Err(());
    }
    let result = match unsafe { fill_packed(data, is_list, length, minimum, buffer) } {
        Ok(true) => {
            let packed = unsafe { core::slice::from_raw_parts_mut(buffer, length) };
            unsafe { find_ranks(data, is_list, length, minimum, packed) }
        }
        Ok(false) => Ok(None),
        Err(()) => Err(()),
    };
    unsafe { PyMem_Free(buffer.cast()) };
    result
}

unsafe fn median_indices(data: *mut PyObject) -> Result<Option<(usize, usize)>, ()> {
    let Some((is_list, length)) = (unsafe { sequence_info(data) })? else {
        return Ok(None);
    };
    if length == 0 {
        return Ok(None);
    }
    let Some((low, high)) = (unsafe { value_range(data, is_list, length) })? else {
        return Ok(None);
    };
    let span = (high as i128 - low as i128) as u128;
    if span <= u128::from(u16::MAX) {
        unsafe { median_ranks::<u16>(data, is_list, length, low) }
    } else if span <= u128::from(u32::MAX) {
        unsafe { median_ranks::<u32>(data, is_list, length, low) }
    } else {
        unsafe { median_ranks::<u64>(data, is_list, length, low) }
    }
}

unsafe extern "C" fn median_indices_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return no_fast_path();
    }
    let (low, high) = match unsafe { median_indices(*args) } {
        Ok(Some(indices)) => indices,
        Ok(None) => return no_fast_path(),
        Err(()) => return ptr::null_mut(),
    };

    let tuple = unsafe { PyTuple_New(2) };
    if tuple.is_null() {
        return tuple;
    }
    for (slot, index) in [low, high].into_iter().enumerate() {
        let item = unsafe { PyLong_FromSsize_t(index as Py_ssize_t) };
        if item.is_null() {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
        if unsafe { PyTuple_SetItem(tuple, slot as Py_ssize_t, item) } != 0 {
            unsafe {
                Py_DecRef(item);
                Py_DecRef(tuple);
            }
            return ptr::null_mut();
        }
    }
    tuple
}

static METHODS: [PyMethodDef; 3] = [
    fastcall(
        c"integer_moments",
        integer_moments_method,
        c"Return sum, sum of squares, and count for exact int sequences.",
    ),
    fastcall(
        c"median_indices",
        median_indices_method,
        c"Return stable median indices for exact int sequences.",
    ),
    method_table_end(),
];

static MODULE: Module = Module::new(
    c"_statistics_rs",
    c"Rust summary operations for exact integer sequences.",
    &METHODS,
);

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__statistics_rs() -> *mut PyObject {
    MODULE.init()
}
