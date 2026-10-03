use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_uint, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_IncRef;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_IndexError;
use cpython_sys::PyExc_RuntimeError;
use cpython_sys::PyExc_TypeError;
use cpython_sys::Py_GetConstant;
use cpython_sys::PyList_Append;
use cpython_sys::PyList_GetItemRef;
use cpython_sys::PyList_SetItem;
use cpython_sys::PyList_SetSlice;
use cpython_sys::PyList_Size;
use cpython_sys::PyList_Type;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::PyObject_Type;
use cpython_sys::PyObject_RichCompareBool;
use cpython_sys::Py_ssize_t;
use cpython_sys::PyType_IsSubtype;

const PY_LT: c_int = 0;

struct Owned(*mut PyObject);

impl Owned {
    fn from_raw(object: *mut PyObject) -> Option<Self> {
        if object.is_null() {
            None
        } else {
            Some(Self(object))
        }
    }

    fn as_ptr(&self) -> *mut PyObject {
        self.0
    }

    fn into_raw(mut self) -> *mut PyObject {
        let object = self.0;
        self.0 = ptr::null_mut();
        object
    }
}

impl Drop for Owned {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { Py_DecRef(self.0) };
        }
    }
}

fn set_index_error() {
    unsafe { PyErr_SetString(PyExc_IndexError, c"index out of range".as_ptr()) };
}

fn set_runtime_error() {
    unsafe {
        PyErr_SetString(
            PyExc_RuntimeError,
            c"list changed size during iteration".as_ptr(),
        )
    };
}

fn none_new_ref() -> *mut PyObject {
    unsafe { Py_GetConstant(0 as c_uint) }
}

fn item(heap: *mut PyObject, index: Py_ssize_t) -> Option<Owned> {
    Owned::from_raw(unsafe { PyList_GetItemRef(heap, index) })
}

fn list_size(heap: *mut PyObject) -> Option<Py_ssize_t> {
    let size = unsafe { PyList_Size(heap) };
    if size < 0 { None } else { Some(size) }
}

fn require_list(heap: *mut PyObject) -> bool {
    let Some(actual_type) = Owned::from_raw(unsafe { PyObject_Type(heap) }) else {
        return false;
    };
    let is_list = unsafe {
        PyType_IsSubtype(
            actual_type.as_ptr().cast(),
            ptr::addr_of_mut!(PyList_Type),
        )
    };
    if is_list == 0 {
        unsafe { PyErr_SetString(PyExc_TypeError, c"heap must be a list".as_ptr()) };
        return false;
    }
    true
}

fn compare_less(left: *mut PyObject, right: *mut PyObject) -> Result<bool, ()> {
    let result = unsafe { PyObject_RichCompareBool(left, right, PY_LT) };
    if result < 0 {
        Err(())
    } else {
        Ok(result != 0)
    }
}

fn unchanged_size(heap: *mut PyObject, expected: Py_ssize_t) -> bool {
    match list_size(heap) {
        Some(actual) if actual == expected => true,
        Some(_) => {
            set_runtime_error();
            false
        }
        None => false,
    }
}

fn swap(heap: *mut PyObject, left: Py_ssize_t, right: Py_ssize_t) -> bool {
    let Some(left_item) = item(heap, left) else {
        return false;
    };
    let Some(right_item) = item(heap, right) else {
        return false;
    };
    if unsafe { PyList_SetItem(heap, left, right_item.into_raw()) } != 0 {
        return false;
    }
    unsafe { PyList_SetItem(heap, right, left_item.into_raw()) == 0 }
}

/// Rich comparisons can mutate the heap, so each swap reads current list items
/// and each comparison checks that the list kept its original size.
fn sift_down(heap: *mut PyObject, start: Py_ssize_t, mut pos: Py_ssize_t, max_heap: bool) -> bool {
    let Some(size) = list_size(heap) else {
        return false;
    };
    if pos >= size {
        set_index_error();
        return false;
    }

    while pos > start {
        let parent = (pos - 1) >> 1;
        let Some(new_item) = item(heap, pos) else {
            return false;
        };
        let Some(parent_item) = item(heap, parent) else {
            return false;
        };
        let out_of_order = if max_heap {
            compare_less(parent_item.as_ptr(), new_item.as_ptr())
        } else {
            compare_less(new_item.as_ptr(), parent_item.as_ptr())
        };
        let out_of_order = match out_of_order {
            Ok(result) => result,
            Err(()) => return false,
        };
        if !unchanged_size(heap, size) {
            return false;
        }
        if !out_of_order {
            break;
        }
        if !swap(heap, pos, parent) {
            return false;
        }
        pos = parent;
    }
    true
}

fn sift_up(heap: *mut PyObject, mut pos: Py_ssize_t, max_heap: bool) -> bool {
    let Some(end) = list_size(heap) else {
        return false;
    };
    if pos >= end {
        set_index_error();
        return false;
    }
    let start = pos;
    let limit = end >> 1;

    while pos < limit {
        let left = 2 * pos + 1;
        let right = left + 1;
        let mut child = left;
        if right < end {
            let Some(left_item) = item(heap, left) else {
                return false;
            };
            let Some(right_item) = item(heap, right) else {
                return false;
            };
            let choose_right = if max_heap {
                match compare_less(right_item.as_ptr(), left_item.as_ptr()) {
                    Ok(result) => !result,
                    Err(()) => return false,
                }
            } else {
                match compare_less(left_item.as_ptr(), right_item.as_ptr()) {
                    Ok(result) => !result,
                    Err(()) => return false,
                }
            };
            if !unchanged_size(heap, end) {
                return false;
            }
            if choose_right {
                child = right;
            }
        }
        if !swap(heap, pos, child) {
            return false;
        }
        pos = child;
    }
    sift_down(heap, start, pos, max_heap)
}

unsafe fn arity(nargs: Py_ssize_t, expected: Py_ssize_t, name: &'static std::ffi::CStr) -> bool {
    if nargs == expected {
        true
    } else {
        unsafe { PyErr_SetString(PyExc_TypeError, name.as_ptr()) };
        false
    }
}

unsafe fn heap_one_arg(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    name: &'static std::ffi::CStr,
    max_heap: bool,
    operation: c_int,
) -> *mut PyObject {
    if !unsafe { arity(nargs, 1, name) } {
        return ptr::null_mut();
    }
    let heap = unsafe { *args };
    if !require_list(heap) {
        return ptr::null_mut();
    }
    let Some(size) = list_size(heap) else {
        return ptr::null_mut();
    };

    if operation == 1 {
        if size == 0 {
            set_index_error();
            return ptr::null_mut();
        }
        let Some(last) = item(heap, size - 1) else {
            return ptr::null_mut();
        };
        if unsafe { PyList_SetSlice(heap, size - 1, size, ptr::null_mut()) } != 0 {
            return ptr::null_mut();
        }
        if size == 1 {
            return last.into_raw();
        }
        let Some(returned) = item(heap, 0) else {
            return ptr::null_mut();
        };
        if unsafe { PyList_SetItem(heap, 0, last.into_raw()) } != 0 {
            return ptr::null_mut();
        }
        if !sift_up(heap, 0, max_heap) {
            return ptr::null_mut();
        }
        return returned.into_raw();
    }

    for index in (0..(size / 2)).rev() {
        if !sift_up(heap, index, max_heap) {
            return ptr::null_mut();
        }
    }
    none_new_ref()
}

unsafe fn heap_two_args(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    name: &'static std::ffi::CStr,
    max_heap: bool,
    operation: c_int,
) -> *mut PyObject {
    if !unsafe { arity(nargs, 2, name) } {
        return ptr::null_mut();
    }
    let heap = unsafe { *args };
    let value = unsafe { *args.add(1) };
    if !require_list(heap) {
        return ptr::null_mut();
    }
    let Some(size) = list_size(heap) else {
        return ptr::null_mut();
    };

    match operation {
        0 => {
            if unsafe { PyList_Append(heap, value) } != 0 {
                return ptr::null_mut();
            }
            let Some(new_size) = list_size(heap) else {
                return ptr::null_mut();
            };
            if !sift_down(heap, 0, new_size - 1, max_heap) {
                return ptr::null_mut();
            }
            none_new_ref()
        }
        1 => {
            if size == 0 {
                set_index_error();
                return ptr::null_mut();
            }
            let Some(returned) = item(heap, 0) else {
                return ptr::null_mut();
            };
            unsafe { Py_IncRef(value) };
            if unsafe { PyList_SetItem(heap, 0, value) } != 0 {
                unsafe { Py_DecRef(value) };
                return ptr::null_mut();
            }
            if !sift_up(heap, 0, max_heap) {
                return ptr::null_mut();
            }
            returned.into_raw()
        }
        _ => {
            if size == 0 {
                unsafe { Py_IncRef(value) };
                return value;
            }
            let Some(root) = item(heap, 0) else {
                return ptr::null_mut();
            };
            let replace = if max_heap {
                match compare_less(value, root.as_ptr()) {
                    Ok(result) => result,
                    Err(()) => return ptr::null_mut(),
                }
            } else {
                match compare_less(root.as_ptr(), value) {
                    Ok(result) => result,
                    Err(()) => return ptr::null_mut(),
                }
            };
            if !replace {
                unsafe { Py_IncRef(value) };
                return value;
            }
            let Some(current_size) = list_size(heap) else {
                return ptr::null_mut();
            };
            if current_size == 0 {
                set_index_error();
                return ptr::null_mut();
            }
            let Some(returned) = item(heap, 0) else {
                return ptr::null_mut();
            };
            unsafe { Py_IncRef(value) };
            if unsafe { PyList_SetItem(heap, 0, value) } != 0 {
                unsafe { Py_DecRef(value) };
                return ptr::null_mut();
            }
            if !sift_up(heap, 0, max_heap) {
                return ptr::null_mut();
            }
            returned.into_raw()
        }
    }
}

unsafe extern "C" fn heappush(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_two_args(args, nargs, c"heappush() takes exactly two arguments", false, 0) }
}

unsafe extern "C" fn heappop(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_one_arg(args, nargs, c"heappop() takes exactly one argument", false, 1) }
}

unsafe extern "C" fn heapify(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_one_arg(args, nargs, c"heapify() takes exactly one argument", false, 0) }
}

unsafe extern "C" fn heapreplace(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_two_args(args, nargs, c"heapreplace() takes exactly two arguments", false, 1) }
}

unsafe extern "C" fn heappushpop(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_two_args(args, nargs, c"heappushpop() takes exactly two arguments", false, 2) }
}

unsafe extern "C" fn heappush_max(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_two_args(args, nargs, c"heappush_max() takes exactly two arguments", true, 0) }
}

unsafe extern "C" fn heappop_max(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_one_arg(args, nargs, c"heappop_max() takes exactly one argument", true, 1) }
}

unsafe extern "C" fn heapify_max(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_one_arg(args, nargs, c"heapify_max() takes exactly one argument", true, 0) }
}

unsafe extern "C" fn heapreplace_max(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_two_args(args, nargs, c"heapreplace_max() takes exactly two arguments", true, 1) }
}

unsafe extern "C" fn heappushpop_max(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { heap_two_args(args, nargs, c"heappushpop_max() takes exactly two arguments", true, 2) }
}

pub extern "C" fn _heapq_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _heapq_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _HEAPQ_RS_MODULE_METHODS: [PyMethodDef; 11] = [
    PyMethodDef {
        ml_name: c"heappush".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heappush,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Push an item onto a min-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heappop".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heappop,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Pop the smallest item from a min-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heapify".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heapify,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Transform a list into a min-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heapreplace".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heapreplace,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Pop and replace the smallest item in a min-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heappushpop".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heappushpop,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Push and pop in one operation on a min-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heappush_max".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heappush_max,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Push an item onto a max-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heappop_max".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heappop_max,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Pop the largest item from a max-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heapify_max".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heapify_max,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Transform a list into a max-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heapreplace_max".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heapreplace_max,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Pop and replace the largest item in a max-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"heappushpop_max".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: heappushpop_max,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Push and pop in one operation on a max-heap.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _HEAPQ_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_heapq_rs".as_ptr() as *mut _,
        m_doc: c"Rust heap operation helpers.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_HEAPQ_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_heapq_rs_clear),
        m_free: Some(_heapq_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__heapq_rs() -> *mut PyObject {
    _HEAPQ_RS_MODULE.init_multi_phase()
}
