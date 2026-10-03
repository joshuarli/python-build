//! Sequence choice and sampling through Python generator callbacks.
//!
//! Direct CPython declarations avoid adding a separate standard runtime
//! to the extension. The builtin route uses the interpreter's existing
//! Rust archive and panic runtime. Python owns all sampling allocations.
#![cfg_attr(not(feature = "static-module"), no_std)]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::ptr;

type Py_ssize_t = isize;

#[repr(C)]
struct PyObject {
    ob_refcnt: Py_ssize_t,
    ob_type: *mut PyTypeObject,
}

#[repr(C)]
struct PyTypeObject {
    _opaque: [u8; 0],
}

#[repr(C)]
union PyMethodDefFuncPointer {
    PyCFunctionFast: unsafe extern "C" fn(
        slf: *mut PyObject,
        args: *mut *mut PyObject,
        nargs: Py_ssize_t,
    ) -> *mut PyObject,
    void: *mut c_void,
}

#[repr(C)]
struct PyMethodDef {
    ml_name: *mut c_char,
    ml_meth: PyMethodDefFuncPointer,
    ml_flags: c_int,
    ml_doc: *mut c_char,
}

unsafe impl Sync for PyMethodDef {}

#[repr(C)]
struct PyModuleDef_Base {
    ob_base: PyObject,
    m_init: Option<unsafe extern "C" fn() -> *mut PyObject>,
    m_index: Py_ssize_t,
    m_copy: *mut PyObject,
}

#[repr(C)]
struct PyModuleDef {
    m_base: PyModuleDef_Base,
    m_name: *const c_char,
    m_doc: *const c_char,
    m_size: Py_ssize_t,
    m_methods: *mut PyMethodDef,
    m_slots: *mut PyModuleDef_Slot,
    m_traverse: Option<unsafe extern "C" fn(*mut PyObject, *mut c_void, *mut c_void) -> c_int>,
    m_clear: Option<extern "C" fn(*mut PyObject) -> c_int>,
    m_free: Option<extern "C" fn(*mut c_void)>,
}

const METH_FASTCALL: c_int = 0x0080;
/// `_Py_IMMORTAL_INITIAL_REFCNT | ((_Py_STATICALLY_ALLOCATED_FLAG |
/// _Py_IMMORTAL_FLAGS) << 48)` for the 64-bit GIL-enabled build.
const STATIC_IMMORTAL_REFCNT: Py_ssize_t = (3_isize << 30) | (5_isize << 48);

#[repr(C)]
struct PyModuleDef_Slot {
    slot: c_int,
    value: *mut c_void,
}

#[cfg_attr(target_vendor = "apple", link(name = "System"))]
unsafe extern "C" {
    static mut PyExc_TypeError: *mut PyObject;
    static mut PyExc_IndexError: *mut PyObject;
    fn PyModuleDef_Init(module: *mut PyModuleDef) -> *mut PyObject;
    fn PyErr_Occurred() -> *mut PyObject;
    fn PyErr_SetString(exception: *mut PyObject, message: *const c_char);
    fn PyLong_FromSsize_t(value: Py_ssize_t) -> *mut PyObject;
    fn PyNumber_Subtract(left: *mut PyObject, right: *mut PyObject) -> *mut PyObject;
    fn PyObject_CallOneArg(callable: *mut PyObject, arg: *mut PyObject) -> *mut PyObject;
    fn PyObject_GetItem(object: *mut PyObject, key: *mut PyObject) -> *mut PyObject;
    fn PyObject_GetIter(object: *mut PyObject) -> *mut PyObject;
    fn PyObject_SetItem(object: *mut PyObject, key: *mut PyObject, value: *mut PyObject) -> c_int;
    fn PyObject_Size(object: *mut PyObject) -> Py_ssize_t;
    fn PySequence_Contains(sequence: *mut PyObject, value: *mut PyObject) -> c_int;
    fn PyIter_Next(iterator: *mut PyObject) -> *mut PyObject;
    fn Py_DecRef(object: *mut PyObject);
    fn Py_IncRef(object: *mut PyObject);
    #[cfg(not(feature = "static-module"))]
    fn abort() -> !;
}

#[cfg(not(feature = "static-module"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

unsafe fn check_arity(actual: Py_ssize_t, expected: Py_ssize_t) -> bool {
    if actual == expected {
        true
    } else {
        unsafe { PyErr_SetString(PyExc_TypeError, c"invalid number of arguments".as_ptr()) };
        false
    }
}

unsafe fn call_randbelow(randbelow: *mut PyObject, upper: *mut PyObject) -> *mut PyObject {
    unsafe { PyObject_CallOneArg(randbelow, upper) }
}

unsafe fn set_item(
    container: *mut PyObject,
    index: *mut PyObject,
    item: *mut PyObject,
) -> bool {
    let status = unsafe { PyObject_SetItem(container, index, item) };
    unsafe { Py_DecRef(item) };
    status == 0
}

unsafe fn next_index(iterator: *mut PyObject) -> Result<Option<*mut PyObject>, ()> {
    let index = unsafe { PyIter_Next(iterator) };
    if !index.is_null() {
        return Ok(Some(index));
    }
    if unsafe { PyErr_Occurred() }.is_null() {
        Ok(None)
    } else {
        Err(())
    }
}

unsafe fn sample_pool(
    pool: *mut PyObject,
    result: *mut PyObject,
    indices: *mut PyObject,
    population_size: *mut PyObject,
    randbelow: *mut PyObject,
) -> bool {
    let iterator = unsafe { PyObject_GetIter(indices) };
    if iterator.is_null() {
        return false;
    }
    let one = unsafe { PyLong_FromSsize_t(1) };
    if one.is_null() {
        unsafe { Py_DecRef(iterator) };
        return false;
    }
    loop {
        let index = match unsafe { next_index(iterator) } {
            Ok(Some(index)) => index,
            Ok(None) => break,
            Err(()) => {
                unsafe {
                    Py_DecRef(one);
                    Py_DecRef(iterator);
                }
                return false;
            }
        };
        let upper = unsafe { PyNumber_Subtract(population_size, index) };
        if upper.is_null() {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let selected_index = unsafe { call_randbelow(randbelow, upper) };
        unsafe { Py_DecRef(upper) };
        if selected_index.is_null() {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let selected = unsafe { PyObject_GetItem(pool, selected_index) };
        if selected.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        if !unsafe { set_item(result, index, selected) } {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let end = unsafe { PyNumber_Subtract(population_size, index) };
        if end.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let last_index = unsafe { PyNumber_Subtract(end, one) };
        unsafe { Py_DecRef(end) };
        if last_index.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let replacement = unsafe { PyObject_GetItem(pool, last_index) };
        unsafe { Py_DecRef(last_index) };
        if replacement.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
        let updated = unsafe { PyObject_SetItem(pool, selected_index, replacement) };
        unsafe {
            Py_DecRef(replacement);
            Py_DecRef(selected_index);
            Py_DecRef(index);
        }
        if updated != 0 {
            unsafe {
                Py_DecRef(one);
                Py_DecRef(iterator);
            }
            return false;
        }
    }
    unsafe {
        Py_DecRef(one);
        Py_DecRef(iterator);
    }
    true
}

unsafe fn sample_selected(
    population: *mut PyObject,
    selected: *mut PyObject,
    selected_add: *mut PyObject,
    result: *mut PyObject,
    indices: *mut PyObject,
    population_size: *mut PyObject,
    randbelow: *mut PyObject,
) -> bool {
    let iterator = unsafe { PyObject_GetIter(indices) };
    if iterator.is_null() {
        return false;
    }
    loop {
        let index = match unsafe { next_index(iterator) } {
            Ok(Some(index)) => index,
            Ok(None) => break,
            Err(()) => {
                unsafe { Py_DecRef(iterator) };
                return false;
            }
        };
        let mut selected_index = unsafe { call_randbelow(randbelow, population_size) };
        if selected_index.is_null() {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(iterator);
            }
            return false;
        }
        loop {
            let contains = unsafe { PySequence_Contains(selected, selected_index) };
            if contains < 0 {
                unsafe {
                    Py_DecRef(selected_index);
                    Py_DecRef(index);
                    Py_DecRef(iterator);
                }
                return false;
            }
            if contains == 0 {
                break;
            }
            unsafe { Py_DecRef(selected_index) };
            selected_index = unsafe { call_randbelow(randbelow, population_size) };
            if selected_index.is_null() {
                unsafe {
                    Py_DecRef(index);
                    Py_DecRef(iterator);
                }
                return false;
            }
        }
        let added = unsafe { PyObject_CallOneArg(selected_add, selected_index) };
        if added.is_null() {
            unsafe {
                Py_DecRef(selected_index);
                Py_DecRef(index);
                Py_DecRef(iterator);
            }
            return false;
        }
        unsafe { Py_DecRef(added) };
        let item = unsafe { PyObject_GetItem(population, selected_index) };
        unsafe { Py_DecRef(selected_index) };
        if item.is_null() {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(iterator);
            }
            return false;
        }
        if !unsafe { set_item(result, index, item) } {
            unsafe {
                Py_DecRef(index);
                Py_DecRef(iterator);
            }
            return false;
        }
        unsafe { Py_DecRef(index) };
    }
    unsafe { Py_DecRef(iterator) };
    true
}

unsafe extern "C" fn choice(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 2) } {
        return ptr::null_mut();
    }
    let sequence = unsafe { *args };
    let length = unsafe { PyObject_Size(sequence) };
    if length < 0 {
        return ptr::null_mut();
    }
    if length == 0 {
        unsafe { PyErr_SetString(PyExc_IndexError, c"Cannot choose from an empty sequence".as_ptr()) };
        return ptr::null_mut();
    }
    let upper = unsafe { PyLong_FromSsize_t(length) };
    if upper.is_null() {
        return ptr::null_mut();
    }
    let index = unsafe { call_randbelow(*args.add(1), upper) };
    unsafe { Py_DecRef(upper) };
    if index.is_null() {
        return ptr::null_mut();
    }
    let item = unsafe { PyObject_GetItem(sequence, index) };
    unsafe { Py_DecRef(index) };
    item
}

unsafe extern "C" fn sample_pool_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 5) } {
        return ptr::null_mut();
    }
    let pool = unsafe { *args };
    let result = unsafe { *args.add(1) };
    let indices = unsafe { *args.add(2) };
    let population_size = unsafe { *args.add(3) };
    let randbelow = unsafe { *args.add(4) };
    if !unsafe { sample_pool(pool, result, indices, population_size, randbelow) } {
        return ptr::null_mut();
    }
    unsafe { Py_IncRef(result) };
    result
}

unsafe extern "C" fn sample_selected_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if !unsafe { check_arity(nargs, 7) } {
        return ptr::null_mut();
    }
    let population = unsafe { *args };
    let selected = unsafe { *args.add(1) };
    let selected_add = unsafe { *args.add(2) };
    let result = unsafe { *args.add(3) };
    let indices = unsafe { *args.add(4) };
    let population_size = unsafe { *args.add(5) };
    let randbelow = unsafe { *args.add(6) };
    if !unsafe {
        sample_selected(
            population,
            selected,
            selected_add,
            result,
            indices,
            population_size,
            randbelow,
        )
    } {
        return ptr::null_mut();
    }
    unsafe { Py_IncRef(result) };
    result
}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

const PY_MOD_MULTIPLE_INTERPRETERS_SLOT: c_int = 86;
const PY_MOD_PER_INTERPRETER_GIL_SUPPORTED: usize = 2;

struct ModuleSlots(UnsafeCell<[PyModuleDef_Slot; 2]>);

unsafe impl Sync for ModuleSlots {}

static MODULE_SLOTS: ModuleSlots = ModuleSlots(UnsafeCell::new([
    PyModuleDef_Slot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS_SLOT,
        value: PY_MOD_PER_INTERPRETER_GIL_SUPPORTED as *mut c_void,
    },
    PyModuleDef_Slot {
        slot: 0,
        value: ptr::null_mut(),
    },
]));

static MODULE_METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"choice".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: choice },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Choose an element using a Python generator callback".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"sample_pool".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: sample_pool_method },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Sample a sequence using a Python generator callback".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"sample_selected".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: sample_selected_method },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Sample a sequence using a Python generator callback".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: ptr::null_mut(),
        ml_meth: PyMethodDefFuncPointer { void: ptr::null_mut() },
        ml_flags: 0,
        ml_doc: ptr::null_mut(),
    },
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_Base {
            ob_base: PyObject {
                ob_refcnt: STATIC_IMMORTAL_REFCNT,
                ob_type: ptr::null_mut(),
            },
            m_init: None,
            m_index: 0,
            m_copy: ptr::null_mut(),
        },
        m_name: c"_random_rs".as_ptr() as *mut c_char,
        m_doc: c"Rust sequence sampling primitives for random.Random".as_ptr() as *mut c_char,
        m_size: 0,
        m_methods: MODULE_METHODS.as_ptr() as *mut PyMethodDef,
        m_slots: MODULE_SLOTS.0.get().cast(),
        m_traverse: None,
        m_clear: None,
        m_free: None,
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__random_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
