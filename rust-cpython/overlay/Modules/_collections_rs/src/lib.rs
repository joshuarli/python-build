use std::ffi::{c_char, c_int, c_long, c_void};
use std::ptr;

use cpython_sys::{
    METH_FASTCALL, Py_DecRef, PyErr_Occurred, PyErr_SetString, PyExc_TypeError, PyMethodDef,
    PyMethodDefFuncPointer, PyABIInfo, PySlot, PySlot__bindgen_ty_1, PySlot__bindgen_ty_2,
    Py_mod_abi, Py_mod_name, Py_mod_doc, Py_mod_methods, PySlot_INTPTR, PySlot_STATIC,
    PyObject, Py_NewRef, Py_ssize_t, _Py_NoneStruct,
};

unsafe extern "C" {
    fn PyObject_GetIter(object: *mut PyObject) -> *mut PyObject;
    fn PyIter_Next(iterator: *mut PyObject) -> *mut PyObject;
    fn PyObject_CallFunctionObjArgs(callable: *mut PyObject, ...) -> *mut PyObject;
    fn PyNumber_Subtract(left: *mut PyObject, right: *mut PyObject) -> *mut PyObject;
    fn PyObject_SetItem(
        object: *mut PyObject,
        key: *mut PyObject,
        value: *mut PyObject,
    ) -> std::ffi::c_int;
    fn PyLong_FromLong(value: c_long) -> *mut PyObject;
}

struct Owned(*mut PyObject);

impl Drop for Owned {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe { Py_DecRef(self.0) };
        }
    }
}

unsafe fn subtract_iterable(
    mapping: *mut PyObject,
    iterable: *mut PyObject,
    mapping_get: *mut PyObject,
) -> *mut PyObject {
    let iterator = Owned(unsafe { PyObject_GetIter(iterable) });
    if iterator.0.is_null() {
        return ptr::null_mut();
    }
    let zero = Owned(unsafe { PyLong_FromLong(0) });
    if zero.0.is_null() {
        return ptr::null_mut();
    }
    let one = Owned(unsafe { PyLong_FromLong(1) });
    if one.0.is_null() {
        return ptr::null_mut();
    }

    loop {
        let key = Owned(unsafe { PyIter_Next(iterator.0) });
        if key.0.is_null() {
            if unsafe { PyErr_Occurred() }.is_null() {
                break;
            }
            return ptr::null_mut();
        }

        let current = Owned(unsafe {
            PyObject_CallFunctionObjArgs(
                mapping_get,
                key.0,
                zero.0,
                ptr::null_mut::<PyObject>(),
            )
        });
        if current.0.is_null() {
            return ptr::null_mut();
        }
        let next = Owned(unsafe { PyNumber_Subtract(current.0, one.0) });
        if next.0.is_null() {
            return ptr::null_mut();
        }
        if unsafe { PyObject_SetItem(mapping, key.0, next.0) } < 0 {
            return ptr::null_mut();
        }
    }

    unsafe { Py_NewRef(ptr::addr_of_mut!(_Py_NoneStruct)) }
}

unsafe extern "C" fn subtract_iterable_method(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 3 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"subtract_iterable requires a mapping, iterable, and bound get method".as_ptr(),
            )
        };
        return ptr::null_mut();
    }

    let (mapping, iterable, mapping_get) = unsafe { (*args, *args.add(1), *args.add(2)) };
    unsafe { subtract_iterable(mapping, iterable, mapping_get) }
}

// The loader reads these process-lifetime tables without modifying them.
// Python references and module state belong to each interpreter.
struct ModuleSlots([PySlot; 7]);
unsafe impl Sync for ModuleSlots {}

unsafe extern "C" fn module_exec(_module: *mut PyObject) -> c_int {
    0
}

// Non-stable descriptors validate the major/minor version and GIL ABI.
// The source lock fixes the complete interpreter revision.
static ABI_INFO: PyABIInfo = PyABIInfo {
    abiinfo_major_version: 1, abiinfo_minor_version: 0, flags: 2,
    build_version: 0x031000a0, abi_version: 0x031000a0,
};

#[cfg(not(target_pointer_width = "64"))]
compile_error!("collections slot export requires the supported 64-bit CPython ABI");

const _: () = {
    assert!(std::mem::size_of::<PySlot>() == 16);
    assert!(std::mem::align_of::<PySlot>() == 8);
    assert!(std::mem::offset_of!(PySlot, sl_id) == 0);
    assert!(std::mem::offset_of!(PySlot, sl_flags) == 2);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_1) == 4);
    assert!(std::mem::offset_of!(PySlot, __bindgen_anon_2) == 8);
    assert!(std::mem::size_of::<PyABIInfo>() == 12);
    assert!(std::mem::align_of::<PyABIInfo>() == 4);
};

const fn data_slot(id: u32, value: *mut c_void) -> PySlot {
    PySlot { sl_id: id as u16, sl_flags: PySlot_INTPTR as u16,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: value } }
}

// Method objects retain pointers into this immutable process-lifetime array.
const fn static_data_slot(id: u32, value: *mut c_void) -> PySlot {
    let mut slot = data_slot(id, value);
    slot.sl_flags |= PySlot_STATIC as u16;
    slot
}

const fn function_slot(id: u32, value: unsafe extern "C" fn()) -> PySlot {
    PySlot { sl_id: id as u16, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_func: Some(value) } }
}

// The full non-limited headers select these IDs from compatibility macros;
// the binding generator does not expose those function-like macros.
const MODULE_EXEC_SLOT: u32 = 85;
const MODULE_MULTIPLE_INTERPRETERS_SLOT: u16 = 86;

static METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"subtract_iterable".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: subtract_iterable_method,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Subtract one from the mapped count for each iterable element."
            .as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];


static MODULE_SLOTS: ModuleSlots = ModuleSlots([
    data_slot(Py_mod_abi, &ABI_INFO as *const PyABIInfo as *mut c_void),
    data_slot(Py_mod_name, c"_collections_rs".as_ptr() as *mut c_void),
    data_slot(Py_mod_doc, c"Rust counting operations for collections.".as_ptr() as *mut c_void),
    static_data_slot(Py_mod_methods, METHODS.as_ptr() as *mut c_void),
    function_slot(MODULE_EXEC_SLOT, unsafe { std::mem::transmute::<
        unsafe extern "C" fn(*mut PyObject) -> c_int, unsafe extern "C" fn()>(module_exec) }),
    PySlot { sl_id: MODULE_MULTIPLE_INTERPRETERS_SLOT, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_uint64: 2 } },
    PySlot { sl_id: 0, sl_flags: 0,
        __bindgen_anon_1: PySlot__bindgen_ty_1 { sl_reserved: 0 },
        __bindgen_anon_2: PySlot__bindgen_ty_2 { sl_ptr: ptr::null_mut() } },
]);

#[unsafe(no_mangle)]
pub extern "C" fn PyModExport__collections_rs() -> *mut PySlot {
    MODULE_SLOTS.0.as_ptr() as *mut PySlot
}
