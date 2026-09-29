use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::mem::MaybeUninit;
use std::ptr;
use std::slice;

use cpython_sys::METH_FASTCALL;
use cpython_sys::METH_O;
use cpython_sys::PyBytes_AsString;
use cpython_sys::PyBytes_FromStringAndSize;
use cpython_sys::PyBytes_Size;
use cpython_sys::PyErr_Clear;
use cpython_sys::PyErr_NoMemory;
use cpython_sys::PyMem_Free;
use cpython_sys::PyMem_Malloc;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyTuple_New;
use cpython_sys::PyTuple_SetItem;
use cpython_sys::PyUnicode_AsUCS4;
use cpython_sys::PyUnicode_FromKindAndData;
use cpython_sys::PyUnicode_GetLength;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_ssize_t;

unsafe extern "C" {
    fn PyOS_FSPath(object: *mut PyObject) -> *mut PyObject;
}

/// Path units that fit in the on-stack scratch buffer; longer paths borrow
/// a buffer from Python's allocator for that one call. Every operation works
/// in a single scratch buffer, so the common path never allocates. Nothing
/// here can panic or unwind, which keeps Rust's panic runtime out of the
/// extension image.
const STACK_UNITS: usize = 512;
const PY_UNICODE_4BYTE_KIND: c_int = 4;

/// A path code unit: a UCS4 character for `str`, a byte for `bytes`.
trait Unit: Copy + PartialEq {
    const SEPARATOR: Self;
    const DOT: Self;

    unsafe fn length(value: *mut PyObject) -> Py_ssize_t;
    unsafe fn read(value: *mut PyObject, target: *mut Self, length: usize) -> bool;
    unsafe fn make(units: *const Self, length: usize) -> *mut PyObject;
}

impl Unit for u32 {
    const SEPARATOR: Self = b'/' as u32;
    const DOT: Self = b'.' as u32;

    unsafe fn length(value: *mut PyObject) -> Py_ssize_t {
        unsafe { PyUnicode_GetLength(value) }
    }

    unsafe fn read(value: *mut PyObject, target: *mut Self, length: usize) -> bool {
        !unsafe { PyUnicode_AsUCS4(value, target, length as Py_ssize_t, 0) }.is_null()
    }

    unsafe fn make(units: *const Self, length: usize) -> *mut PyObject {
        unsafe {
            PyUnicode_FromKindAndData(PY_UNICODE_4BYTE_KIND, units.cast(), length as Py_ssize_t)
        }
    }
}

impl Unit for u8 {
    const SEPARATOR: Self = b'/';
    const DOT: Self = b'.';

    unsafe fn length(value: *mut PyObject) -> Py_ssize_t {
        unsafe { PyBytes_Size(value) }
    }

    unsafe fn read(value: *mut PyObject, target: *mut Self, length: usize) -> bool {
        let data = unsafe { PyBytes_AsString(value) };
        if data.is_null() {
            return false;
        }
        unsafe { ptr::copy_nonoverlapping(data.cast::<u8>(), target, length) };
        true
    }

    unsafe fn make(units: *const Self, length: usize) -> *mut PyObject {
        unsafe { PyBytes_FromStringAndSize(units.cast(), length as Py_ssize_t) }
    }
}

/// Run `body` with a scratch buffer of `capacity` units: on the stack when it
/// fits, otherwise from Python's allocator for that one call.
unsafe fn with_scratch<T: Unit>(
    capacity: usize,
    body: impl FnOnce(*mut T) -> *mut PyObject,
) -> *mut PyObject {
    if capacity <= STACK_UNITS {
        let mut stack = [const { MaybeUninit::<T>::uninit() }; STACK_UNITS];
        return body(stack.as_mut_ptr().cast());
    }
    let Some(bytes) = capacity.checked_mul(size_of::<T>()) else {
        return unsafe { PyErr_NoMemory() };
    };
    let heap = unsafe { PyMem_Malloc(bytes) }.cast::<T>();
    if heap.is_null() {
        return unsafe { PyErr_NoMemory() };
    }
    let result = body(heap);
    unsafe { PyMem_Free(heap.cast()) };
    result
}

/// Call `text` for a `str` value and `bytes` for a `bytes` value, passing the
/// length. `value` must come from `PyOS_FSPath`.
unsafe fn with_kind(
    value: *mut PyObject,
    text: impl FnOnce(usize) -> *mut PyObject,
    bytes: impl FnOnce(usize) -> *mut PyObject,
) -> *mut PyObject {
    let length = unsafe { <u32 as Unit>::length(value) };
    if length >= 0 {
        return text(length as usize);
    }
    unsafe { PyErr_Clear() };
    let length = unsafe { <u8 as Unit>::length(value) };
    if length < 0 {
        return ptr::null_mut();
    }
    bytes(length as usize)
}

unsafe fn tuple_of<const N: usize>(items: [*mut PyObject; N]) -> *mut PyObject {
    if items.iter().any(|item| item.is_null()) {
        for item in items.iter() {
            if !item.is_null() {
                unsafe { Py_DecRef(*item) };
            }
        }
        return ptr::null_mut();
    }
    let result = unsafe { PyTuple_New(N as Py_ssize_t) };
    if result.is_null() {
        for item in items.iter() {
            unsafe { Py_DecRef(*item) };
        }
        return ptr::null_mut();
    }
    for (index, item) in items.iter().enumerate() {
        // PyTuple_SetItem steals the reference even when it fails.
        unsafe { PyTuple_SetItem(result, index as Py_ssize_t, *item) };
    }
    result
}

fn root_length<T: Unit>(path: &[T]) -> usize {
    if path.first() != Some(&T::SEPARATOR) {
        return 0;
    }
    // Preserve a root of exactly two slashes; collapse longer runs to one.
    if path.get(1) == Some(&T::SEPARATOR) && (path.len() == 2 || path.get(2) != Some(&T::SEPARATOR))
    {
        2
    } else {
        1
    }
}

/// Normalize the path in `buffer` in place. The output never overtakes the
/// unread input, so no second buffer is needed. Returns the normalized
/// length, at least 1 (the buffer needs one spare unit for an empty path).
unsafe fn normpath_in_place<T: Unit>(buffer: *mut T, length: usize) -> usize {
    if length == 0 {
        unsafe { *buffer = T::DOT };
        return 1;
    }
    let root = root_length(unsafe { slice::from_raw_parts(buffer, length) });
    let mut written = root;
    let mut start = root;
    let mut index = root;
    loop {
        if index != length && unsafe { *buffer.add(index) } != T::SEPARATOR {
            index += 1;
            continue;
        }
        let component = index - start;
        let first = start;
        start = index + 1;
        let is_dot = component == 1 && unsafe { *buffer.add(first) } == T::DOT;
        let is_parent = component == 2
            && unsafe { *buffer.add(first) } == T::DOT
            && unsafe { *buffer.add(first + 1) } == T::DOT;
        if component != 0 && !is_dot {
            if is_parent {
                let last_start = unsafe { slice::from_raw_parts(buffer.add(root), written - root) }
                    .iter()
                    .rposition(|unit| *unit == T::SEPARATOR)
                    .map(|position| root + position + 1);
                let relative_leading_parent = root == 0 && written == 0;
                let repeated_parent = written > root && {
                    let from = last_start.unwrap_or(root);
                    written - from == 2
                        && unsafe { *buffer.add(from) } == T::DOT
                        && unsafe { *buffer.add(from + 1) } == T::DOT
                };
                if relative_leading_parent || repeated_parent {
                    if written > root {
                        unsafe { *buffer.add(written) = T::SEPARATOR };
                        written += 1;
                    }
                    unsafe {
                        *buffer.add(written) = T::DOT;
                        *buffer.add(written + 1) = T::DOT;
                    }
                    written += 2;
                } else if let Some(from) = last_start {
                    written = from - 1;
                } else {
                    written = root;
                }
            } else {
                if written > root {
                    unsafe { *buffer.add(written) = T::SEPARATOR };
                    written += 1;
                }
                unsafe { ptr::copy(buffer.add(first), buffer.add(written), component) };
                written += component;
            }
        }
        if index == length {
            break;
        }
        index += 1;
    }
    if written == 0 {
        unsafe { *buffer = T::DOT };
        1
    } else {
        written
    }
}

unsafe fn normpath_impl<T: Unit>(value: *mut PyObject, length: usize) -> *mut PyObject {
    unsafe {
        with_scratch::<T>(length + 1, |buffer| {
            if !T::read(value, buffer, length) {
                return ptr::null_mut();
            }
            let written = normpath_in_place(buffer, length);
            T::make(buffer, written)
        })
    }
}

unsafe fn split_impl<T: Unit>(value: *mut PyObject, length: usize) -> *mut PyObject {
    unsafe {
        with_scratch::<T>(length, |buffer| {
            if !T::read(value, buffer, length) {
                return ptr::null_mut();
            }
            let path = slice::from_raw_parts(buffer, length);
            let split_at = path
                .iter()
                .rposition(|unit| *unit == T::SEPARATOR)
                .map_or(0, |index| index + 1);
            let mut head = split_at;
            if head != 0
                && !slice::from_raw_parts(buffer, head)
                    .iter()
                    .all(|unit| *unit == T::SEPARATOR)
            {
                while head != 0 && *buffer.add(head - 1) == T::SEPARATOR {
                    head -= 1;
                }
            }
            tuple_of([
                T::make(buffer, head),
                T::make(buffer.add(split_at), length - split_at),
            ])
        })
    }
}

unsafe fn splitroot_impl<T: Unit>(value: *mut PyObject, length: usize) -> *mut PyObject {
    unsafe {
        with_scratch::<T>(length, |buffer| {
            if !T::read(value, buffer, length) {
                return ptr::null_mut();
            }
            let root = root_length(slice::from_raw_parts(buffer, length));
            tuple_of([
                T::make(buffer, 0),
                T::make(buffer, root),
                T::make(buffer.add(root), length - root),
            ])
        })
    }
}

unsafe fn splitext_impl<T: Unit>(value: *mut PyObject, length: usize) -> *mut PyObject {
    unsafe {
        with_scratch::<T>(length, |buffer| {
            if !T::read(value, buffer, length) {
                return ptr::null_mut();
            }
            let path = slice::from_raw_parts(buffer, length);
            let separator_index = path.iter().rposition(|unit| *unit == T::SEPARATOR);
            let mut split_at = length;
            if let Some(dot_index) = path.iter().rposition(|unit| *unit == T::DOT)
                && separator_index.is_none_or(|index| dot_index > index)
            {
                let filename_start = separator_index.map_or(0, |index| index + 1);
                if slice::from_raw_parts(buffer.add(filename_start), dot_index - filename_start)
                    .iter()
                    .any(|unit| *unit != T::DOT)
                {
                    split_at = dot_index;
                }
            }
            tuple_of([
                T::make(buffer, split_at),
                T::make(buffer.add(split_at), length - split_at),
            ])
        })
    }
}

/// Join `right` onto `left` in one buffer: left at the front, right after a
/// one-unit gap that is either filled with a separator or closed.
unsafe fn join_impl<T: Unit>(
    left: *mut PyObject,
    left_length: usize,
    right: *mut PyObject,
) -> *mut PyObject {
    let right_length = unsafe { T::length(right) };
    if right_length < 0 {
        unsafe { PyErr_Clear() };
        return type_error(c"path components must have the same type");
    }
    let right_length = right_length as usize;
    let gap = left_length + 1;
    unsafe {
        with_scratch::<T>(gap + right_length, |buffer| {
            if !T::read(left, buffer, left_length) || !T::read(right, buffer.add(gap), right_length)
            {
                return ptr::null_mut();
            }
            if left_length == 0 || (right_length != 0 && *buffer.add(gap) == T::SEPARATOR) {
                return T::make(buffer.add(gap), right_length);
            }
            if *buffer.add(left_length - 1) == T::SEPARATOR {
                ptr::copy(buffer.add(gap), buffer.add(left_length), right_length);
                T::make(buffer, left_length + right_length)
            } else {
                *buffer.add(left_length) = T::SEPARATOR;
                T::make(buffer, gap + right_length)
            }
        })
    }
}

unsafe fn argument(args: *mut *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { *args.add(index) }
}

fn type_error(message: &'static std::ffi::CStr) -> *mut PyObject {
    unsafe { cpython_sys::PyErr_SetString(cpython_sys::PyExc_TypeError, message.as_ptr()) };
    ptr::null_mut()
}

/// Apply a one-path operation to `object` after `os.fspath`.
unsafe fn unary(
    object: *mut PyObject,
    text: unsafe fn(*mut PyObject, usize) -> *mut PyObject,
    bytes: unsafe fn(*mut PyObject, usize) -> *mut PyObject,
) -> *mut PyObject {
    let value = unsafe { PyOS_FSPath(object) };
    if value.is_null() {
        return ptr::null_mut();
    }
    let result = unsafe {
        with_kind(
            value,
            |length| text(value, length),
            |length| bytes(value, length),
        )
    };
    unsafe { Py_DecRef(value) };
    result
}

unsafe extern "C" fn normpath(_module: *mut PyObject, object: *mut PyObject) -> *mut PyObject {
    unsafe { unary(object, normpath_impl::<u32>, normpath_impl::<u8>) }
}

unsafe extern "C" fn join_pair_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 2 {
        return type_error(c"join_pair() takes exactly two arguments");
    }
    let left = unsafe { PyOS_FSPath(argument(args, 0)) };
    if left.is_null() {
        return ptr::null_mut();
    }
    let right = unsafe { PyOS_FSPath(argument(args, 1)) };
    if right.is_null() {
        unsafe { Py_DecRef(left) };
        return ptr::null_mut();
    }
    let result = unsafe {
        with_kind(
            left,
            |length| join_impl::<u32>(left, length, right),
            |length| join_impl::<u8>(left, length, right),
        )
    };
    unsafe {
        Py_DecRef(left);
        Py_DecRef(right);
    }
    result
}

unsafe extern "C" fn split(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"split() takes exactly one argument");
    }
    unsafe { unary(argument(args, 0), split_impl::<u32>, split_impl::<u8>) }
}

unsafe extern "C" fn splitroot(_module: *mut PyObject, object: *mut PyObject) -> *mut PyObject {
    unsafe { unary(object, splitroot_impl::<u32>, splitroot_impl::<u8>) }
}

unsafe extern "C" fn splitext(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 1 {
        return type_error(c"splitext() takes exactly one argument");
    }
    unsafe { unary(argument(args, 0), splitext_impl::<u32>, splitext_impl::<u8>) }
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

static MODULE_METHODS: [PyMethodDef; 6] = [
    PyMethodDef {
        ml_name: c"_path_normpath".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: normpath },
        ml_flags: METH_O,
        ml_doc: c"_path_normpath($module, /, path)\n--\n\nNormalize path, eliminating double slashes, etc.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"join_pair".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: join_pair_method },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Join one POSIX path component.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"split".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: split },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Split a POSIX path into head and tail.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"_path_splitroot_ex".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunction: splitroot },
        ml_flags: METH_O,
        ml_doc: c"_path_splitroot_ex($module, /, p)\n--\n\nSplit a pathname into drive, root and tail.\n\nThe tail contains anything after the root.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"splitext".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: splitext },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Split a POSIX path extension.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_posixpath_rs".as_ptr() as *mut _,
        m_doc: c"Rust POSIX path lexical operations.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(module_clear),
        m_free: Some(module_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__posixpath_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
