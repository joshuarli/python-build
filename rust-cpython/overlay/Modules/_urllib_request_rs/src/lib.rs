use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_void};
use std::ptr;

use cpython_sys::METH_FASTCALL;
use cpython_sys::Py_DecRef;
use cpython_sys::Py_IncRef;
use cpython_sys::Py_NewRef;
use cpython_sys::PyErr_Occurred;
use cpython_sys::PyErr_SetString;
use cpython_sys::PyExc_TypeError;
use cpython_sys::PyMethodDef;
use cpython_sys::PyMethodDefFuncPointer;
use cpython_sys::PyModuleDef;
use cpython_sys::PyModuleDef_HEAD_INIT;
use cpython_sys::PyModuleDef_Init;
use cpython_sys::PyObject;
use cpython_sys::Py_ssize_t;

const PY_MOD_MULTIPLE_INTERPRETERS: c_int = 86;

unsafe extern "C" {
    fn PyImport_ImportModule(name: *const c_char) -> *mut PyObject;
    fn PyObject_CallObject(callable: *mut PyObject, args: *mut PyObject) -> *mut PyObject;
    fn PyObject_GetAttr(object: *mut PyObject, name: *mut PyObject) -> *mut PyObject;
    fn PyObject_GetAttrString(object: *mut PyObject, name: *const c_char) -> *mut PyObject;
    fn PyObject_GetIter(object: *mut PyObject) -> *mut PyObject;
    fn PyObject_IsTrue(object: *mut PyObject) -> c_int;
    fn PyObject_SetAttrString(
        object: *mut PyObject,
        name: *const c_char,
        value: *mut PyObject,
    ) -> c_int;
    fn PyIter_Next(iterator: *mut PyObject) -> *mut PyObject;
    fn PyList_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyNumber_Add(left: *mut PyObject, right: *mut PyObject) -> *mut PyObject;
    fn PyTuple_New(size: Py_ssize_t) -> *mut PyObject;
    fn PyTuple_SetItem(tuple: *mut PyObject, index: Py_ssize_t, value: *mut PyObject) -> c_int;
    fn PyUnicode_FromString(value: *const c_char) -> *mut PyObject;
}

unsafe fn tuple_from_borrowed(values: &[*mut PyObject]) -> *mut PyObject {
    let tuple = unsafe { PyTuple_New(values.len() as Py_ssize_t) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    for (index, value) in values.iter().enumerate() {
        unsafe { Py_IncRef(*value) };
        if unsafe { PyTuple_SetItem(tuple, index as Py_ssize_t, *value) } != 0 {
            unsafe { Py_DecRef(tuple) };
            return ptr::null_mut();
        }
    }
    tuple
}

unsafe fn call(callable: *mut PyObject, args: &[*mut PyObject]) -> *mut PyObject {
    let tuple = unsafe { tuple_from_borrowed(args) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    let result = unsafe { PyObject_CallObject(callable, tuple) };
    unsafe { Py_DecRef(tuple) };
    result
}

unsafe fn call_method(
    receiver: *mut PyObject,
    name: &'static std::ffi::CStr,
    args: &[*mut PyObject],
) -> *mut PyObject {
    let method = unsafe { PyObject_GetAttrString(receiver, name.as_ptr()) };
    if method.is_null() {
        return ptr::null_mut();
    }
    let result = unsafe { call(method, args) };
    unsafe { Py_DecRef(method) };
    result
}

unsafe fn call_processor_chain(
    director: *mut PyObject,
    collection_name: &'static std::ffi::CStr,
    protocol: *mut PyObject,
    suffix: &'static std::ffi::CStr,
    request: *mut PyObject,
    mut response: *mut PyObject,
) -> *mut PyObject {
    let has_response = !response.is_null();
    let method_name = unsafe { PyUnicode_FromString(suffix.as_ptr()) };
    if method_name.is_null() {
        if !response.is_null() {
            unsafe { Py_DecRef(response) };
        }
        return ptr::null_mut();
    }
    let full_method_name = unsafe { PyNumber_Add(protocol, method_name) };
    unsafe { Py_DecRef(method_name) };
    if full_method_name.is_null() {
        if !response.is_null() {
            unsafe { Py_DecRef(response) };
        }
        return ptr::null_mut();
    }

    let collection = unsafe { PyObject_GetAttrString(director, collection_name.as_ptr()) };
    if collection.is_null() {
        unsafe { Py_DecRef(full_method_name) };
        if !response.is_null() {
            unsafe { Py_DecRef(response) };
        }
        return ptr::null_mut();
    }
    let empty = unsafe { PyList_New(0) };
    if empty.is_null() {
        unsafe {
            Py_DecRef(collection);
            Py_DecRef(full_method_name);
        }
        if !response.is_null() {
            unsafe { Py_DecRef(response) };
        }
        return ptr::null_mut();
    }
    let processors = unsafe { call_method(collection, c"get", &[protocol, empty]) };
    unsafe {
        Py_DecRef(empty);
        Py_DecRef(collection);
    }
    if processors.is_null() {
        unsafe { Py_DecRef(full_method_name) };
        if !response.is_null() {
            unsafe { Py_DecRef(response) };
        }
        return ptr::null_mut();
    }
    let iterator = unsafe { PyObject_GetIter(processors) };
    unsafe { Py_DecRef(processors) };
    if iterator.is_null() {
        unsafe { Py_DecRef(full_method_name) };
        if !response.is_null() {
            unsafe { Py_DecRef(response) };
        }
        return ptr::null_mut();
    }

    let mut request = unsafe { Py_NewRef(request) };
    loop {
        let processor = unsafe { PyIter_Next(iterator) };
        if processor.is_null() {
            break;
        }
        let method = unsafe { PyObject_GetAttr(processor, full_method_name) };
        unsafe { Py_DecRef(processor) };
        if method.is_null() {
            unsafe {
                Py_DecRef(request);
                Py_DecRef(iterator);
                Py_DecRef(full_method_name);
                if !response.is_null() {
                    Py_DecRef(response);
                }
            }
            return ptr::null_mut();
        }
        let result = if has_response {
            unsafe { call(method, &[request, response]) }
        } else {
            unsafe { call(method, &[request]) }
        };
        unsafe { Py_DecRef(method) };
        if result.is_null() {
            unsafe {
                Py_DecRef(request);
                Py_DecRef(iterator);
                Py_DecRef(full_method_name);
                if !response.is_null() {
                    Py_DecRef(response);
                }
            }
            return ptr::null_mut();
        }
        if has_response {
            unsafe { Py_DecRef(response) };
            response = result;
        } else {
            unsafe { Py_DecRef(request) };
            request = result;
        }
    }
    let iteration_failed = unsafe { !PyErr_Occurred().is_null() };
    unsafe {
        Py_DecRef(iterator);
        Py_DecRef(full_method_name);
    }
    if iteration_failed {
        unsafe {
            Py_DecRef(request);
            if !response.is_null() {
                Py_DecRef(response);
            }
        }
        return ptr::null_mut();
    }
    if has_response {
        unsafe { Py_DecRef(request) };
        response
    } else {
        request
    }
}

unsafe extern "C" fn open(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    if nargs != 6 {
        unsafe {
            PyErr_SetString(
                PyExc_TypeError,
                c"internal urllib request opener requires six arguments".as_ptr(),
            );
        }
        return ptr::null_mut();
    }
    let director = unsafe { *args };
    let fullurl = unsafe { *args.add(1) };
    let data = unsafe { *args.add(2) };
    let timeout = unsafe { *args.add(3) };
    let request_type = unsafe { *args.add(4) };
    let is_string = unsafe { PyObject_IsTrue(*args.add(5)) };
    if is_string < 0 {
        return ptr::null_mut();
    }

    let request = if is_string != 0 {
        unsafe { call(request_type, &[fullurl, data]) }
    } else {
        let request = unsafe { Py_NewRef(fullurl) };
        let none = ptr::addr_of_mut!(cpython_sys::_Py_NoneStruct).cast::<PyObject>();
        if data != none && unsafe { PyObject_SetAttrString(request, c"data".as_ptr(), data) } != 0 {
            unsafe { Py_DecRef(request) };
            return ptr::null_mut();
        }
        request
    };
    if request.is_null() {
        return ptr::null_mut();
    }
    if unsafe { PyObject_SetAttrString(request, c"timeout".as_ptr(), timeout) } != 0 {
        unsafe { Py_DecRef(request) };
        return ptr::null_mut();
    }

    let protocol = unsafe { PyObject_GetAttrString(request, c"type".as_ptr()) };
    if protocol.is_null() {
        unsafe { Py_DecRef(request) };
        return ptr::null_mut();
    }
    let processed_request = unsafe {
        call_processor_chain(
            director,
            c"process_request",
            protocol,
            c"_request",
            request,
            ptr::null_mut(),
        )
    };
    unsafe { Py_DecRef(request) };
    if processed_request.is_null() {
        unsafe { Py_DecRef(protocol) };
        return ptr::null_mut();
    }

    let full_url = unsafe { PyObject_GetAttrString(processed_request, c"full_url".as_ptr()) };
    let request_data = unsafe { PyObject_GetAttrString(processed_request, c"data".as_ptr()) };
    let headers = unsafe { PyObject_GetAttrString(processed_request, c"headers".as_ptr()) };
    let get_method = unsafe { PyObject_GetAttrString(processed_request, c"get_method".as_ptr()) };
    if full_url.is_null() || request_data.is_null() || headers.is_null() || get_method.is_null() {
        for value in [full_url, request_data, headers, get_method, processed_request, protocol] {
            if !value.is_null() {
                unsafe { Py_DecRef(value) };
            }
        }
        return ptr::null_mut();
    }
    let method = unsafe { call(get_method, &[]) };
    unsafe { Py_DecRef(get_method) };
    if method.is_null() {
        for value in [full_url, request_data, headers, processed_request, protocol] {
            unsafe { Py_DecRef(value) };
        }
        return ptr::null_mut();
    }

    let sys_module = unsafe { PyImport_ImportModule(c"sys".as_ptr()) };
    if sys_module.is_null() {
        for value in [full_url, request_data, headers, method, processed_request, protocol] {
            unsafe { Py_DecRef(value) };
        }
        return ptr::null_mut();
    }
    let audit = unsafe { PyObject_GetAttrString(sys_module, c"audit".as_ptr()) };
    unsafe { Py_DecRef(sys_module) };
    if audit.is_null() {
        for value in [full_url, request_data, headers, method, processed_request, protocol] {
            unsafe { Py_DecRef(value) };
        }
        return ptr::null_mut();
    }
    let event = unsafe { PyUnicode_FromString(c"urllib.Request".as_ptr()) };
    let audited = if event.is_null() {
        ptr::null_mut()
    } else {
        unsafe { call(audit, &[event, full_url, request_data, headers, method]) }
    };
    unsafe {
        if !event.is_null() {
            Py_DecRef(event);
        }
        Py_DecRef(audit);
        Py_DecRef(full_url);
        Py_DecRef(request_data);
        Py_DecRef(headers);
        Py_DecRef(method);
    }
    if audited.is_null() {
        unsafe {
            Py_DecRef(processed_request);
            Py_DecRef(protocol);
        }
        return ptr::null_mut();
    }
    unsafe { Py_DecRef(audited) };

    let response = unsafe { call_method(director, c"_open", &[processed_request, data]) };
    if response.is_null() {
        unsafe {
            Py_DecRef(processed_request);
            Py_DecRef(protocol);
        }
        return ptr::null_mut();
    }
    let result = unsafe {
        call_processor_chain(
            director,
            c"process_response",
            protocol,
            c"_response",
            processed_request,
            response,
        )
    };
    unsafe {
        Py_DecRef(processed_request);
        Py_DecRef(protocol);
    }
    result
}

extern "C" fn clear(_module: *mut PyObject) -> c_int {
    0
}

extern "C" fn free(_module: *mut c_void) {}

struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

#[repr(C)]
struct ModuleSlot {
    slot: c_int,
    value: *mut c_void,
}

unsafe impl Sync for ModuleSlot {}

static METHODS: [PyMethodDef; 2] = [
    PyMethodDef {
        ml_name: c"open".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer { PyCFunctionFast: open },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Open a request and process its response through an opener.".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

static SLOTS: [ModuleSlot; 2] = [
    ModuleSlot {
        slot: PY_MOD_MULTIPLE_INTERPRETERS,
        value: 2usize as *mut c_void,
    },
    ModuleSlot {
        slot: 0,
        value: ptr::null_mut(),
    },
];

static MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_urllib_request_rs".as_ptr() as *mut _,
        m_doc: c"Rust request dispatch for urllib.request.".as_ptr() as *mut _,
        m_size: 0,
        m_methods: METHODS.as_ptr() as *mut _,
        m_slots: SLOTS.as_ptr() as *mut _,
        m_traverse: None,
        m_clear: Some(clear),
        m_free: Some(free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__urllib_request_rs() -> *mut PyObject {
    MODULE.init_multi_phase()
}
