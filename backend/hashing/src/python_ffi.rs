use crate::{
    BackendError, NativeState, new_hash, new_hmac, normalize_digest_name, pbkdf2_derive,
    pbkdf2_parameters, scrypt_derive, scrypt_parameters,
};
use pyo3_ffi as ffi;
use std::cell::UnsafeCell;
use std::ffi::{c_char, c_int, c_ulong, c_void};
use std::marker::PhantomData;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::ptr;
use std::rc::Rc;
use std::sync::Mutex;

const CAPSULE_NAME: &[u8] = b"_hashlib_graviola.NativeState\0";
const PY_ASNATIVEBYTES_NATIVE_ENDIAN: c_int = 3;
const PY_ASNATIVEBYTES_UNSIGNED_BUFFER: c_int = 4;
const PY_ASNATIVEBYTES_REJECT_NEGATIVE: c_int = 8;
const PY_ASNATIVEBYTES_ALLOW_INDEX: c_int = 16;

unsafe extern "C" {
    fn PyLong_AsNativeBytes(
        value: *mut ffi::PyObject,
        buffer: *mut c_void,
        n_bytes: isize,
        flags: c_int,
    ) -> isize;
}

#[repr(C)]
struct ModuleState {
    unsupported_digestmod_error: *mut ffi::PyObject,
    interpreter_token: *mut Rc<()>,
}

struct CapsuleState {
    interpreter: Rc<()>,
    state: NativeState,
}

struct OwnedPyObject(*mut ffi::PyObject);

impl OwnedPyObject {
    fn new(object: *mut ffi::PyObject) -> Result<Self, ()> {
        if object.is_null() {
            Err(())
        } else {
            Ok(Self(object))
        }
    }

    fn into_ptr(mut self) -> *mut ffi::PyObject {
        let object = self.0;
        self.0 = ptr::null_mut();
        object
    }
}

impl Drop for OwnedPyObject {
    fn drop(&mut self) {
        if !self.0.is_null() {
            // SAFETY: This owner holds exactly one new reference from a CPython API that returns an owned object.
            unsafe { ffi::Py_DecRef(self.0) }
        }
    }
}

struct Buffer {
    view: ffi::Py_buffer,
}

enum BufferCopyError {
    TooLong(&'static str),
    Allocation,
}

struct AllowThreads {
    thread_state: *mut ffi::PyThreadState,
    not_send: PhantomData<Rc<()>>,
}

impl AllowThreads {
    fn new() -> Self {
        Self {
            // SAFETY: Each caller holds the current interpreter GIL, and Drop restores this state on the same thread.
            thread_state: unsafe { ffi::PyEval_SaveThread() },
            not_send: PhantomData,
        }
    }
}

impl Drop for AllowThreads {
    fn drop(&mut self) {
        // SAFETY: SaveThread produced this thread state and the guard cannot move to another thread.
        unsafe { ffi::PyEval_RestoreThread(self.thread_state) }
    }
}

impl Buffer {
    // SAFETY: The caller holds the current interpreter GIL and passes a live object reference.
    unsafe fn from_object(object: *mut ffi::PyObject) -> Result<Self, ()> {
        let mut view = ffi::Py_buffer::new();
        if unsafe { ffi::PyObject_GetBuffer(object, &mut view, ffi::PyBUF_STRIDES) } != 0 {
            return Err(());
        }
        if unsafe { ffi::PyBuffer_IsContiguous(&view, b'C' as c_char) } == 0 {
            unsafe {
                ffi::PyBuffer_Release(&mut view);
                ffi::PyErr_SetString(
                    ffi::PyExc_BufferError,
                    c"memoryview: underlying buffer is not C-contiguous".as_ptr(),
                );
            }
            return Err(());
        }
        Ok(Self { view })
    }

    fn len(&self) -> usize {
        self.view.len as usize
    }

    fn as_slice(&self) -> &[u8] {
        if self.view.len == 0 {
            &[]
        } else {
            // SAFETY: The acquired buffer keeps this pointer valid until Drop releases the view.
            unsafe { std::slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
        }
    }

    fn copy(&self, too_long: &'static str) -> Result<Vec<u8>, BufferCopyError> {
        if self.len() > i32::MAX as usize {
            return Err(BufferCopyError::TooLong(too_long));
        }
        let mut owned = Vec::new();
        owned
            .try_reserve_exact(self.len())
            .map_err(|_| BufferCopyError::Allocation)?;
        owned.extend_from_slice(self.as_slice());
        Ok(owned)
    }
}

impl Drop for Buffer {
    fn drop(&mut self) {
        // SAFETY: This view was successfully acquired and has not been released elsewhere.
        unsafe { ffi::PyBuffer_Release(&mut self.view) }
    }
}

// SAFETY: Callers use only a live exception object from the active interpreter while holding its GIL.
fn set_error(exception: *mut ffi::PyObject, message: &str) {
    unsafe {
        let value = ffi::PyUnicode_FromStringAndSize(message.as_ptr().cast(), message.len() as isize);
        if value.is_null() {
            return;
        }
        ffi::PyErr_SetObject(exception, value);
        ffi::Py_DecRef(value);
    }
}

// SAFETY: The module pointer is `self` from a live bound module function or module lifecycle callback.
unsafe fn module_state(module: *mut ffi::PyObject) -> Result<*mut ModuleState, ()> {
    let state = unsafe { ffi::PyModule_GetState(module) }.cast::<ModuleState>();
    if state.is_null() {
        unsafe {
            ffi::PyErr_SetString(ffi::PyExc_RuntimeError, c"hash backend has no module state".as_ptr());
        }
        return Err(());
    }
    Ok(state)
}

// SAFETY: These argument helpers run only inside callbacks with the active interpreter GIL held.
unsafe fn tuple_arg(args: *mut ffi::PyObject, index: isize) -> Result<*mut ffi::PyObject, ()> {
    let size = unsafe { ffi::PyTuple_Size(args) };
    if size < 0 {
        return Err(());
    }
    if index >= size {
        unsafe { ffi::PyErr_SetString(ffi::PyExc_TypeError, c"missing required positional argument".as_ptr()) };
        return Err(());
    }
    let result = unsafe { ffi::PyTuple_GetItem(args, index) };
    if result.is_null() {
        Err(())
    } else {
        Ok(result)
    }
}

unsafe fn require_arity(args: *mut ffi::PyObject, expected: isize) -> Result<(), ()> {
    let actual = unsafe { ffi::PyTuple_Size(args) };
    if actual < 0 {
        return Err(());
    }
    if actual != expected {
        let message = format!("expected {expected} positional arguments, got {actual}");
        set_error(unsafe { ffi::PyExc_TypeError }, &message);
        return Err(());
    }
    Ok(())
}

unsafe fn read_name(object: *mut ffi::PyObject) -> Result<String, ()> {
    if unsafe { ffi::PyUnicode_Check(object) } == 0 {
        unsafe { ffi::PyErr_SetString(ffi::PyExc_TypeError, c"hash name must be a string".as_ptr()) };
        return Err(());
    }
    let mut length = 0;
    let text = unsafe { ffi::PyUnicode_AsUTF8AndSize(object, &mut length) };
    if text.is_null() {
        return Err(());
    }
    // SAFETY: CPython returns a UTF-8 pointer valid for this live Unicode object and the reported byte length.
    let bytes = unsafe { std::slice::from_raw_parts(text.cast::<u8>(), length as usize) };
    match std::str::from_utf8(bytes) {
        Ok(name) => Ok(normalize_digest_name(name)),
        Err(_) => {
            unsafe { ffi::PyErr_SetString(ffi::PyExc_UnicodeError, c"hash name is not UTF-8".as_ptr()) };
            Err(())
        }
    }
}

unsafe fn read_long(object: *mut ffi::PyObject) -> Result<i64, ()> {
    let value = unsafe { ffi::PyLong_AsLongLong(object) };
    if !unsafe { ffi::PyErr_Occurred() }.is_null() {
        Err(())
    } else {
        Ok(value)
    }
}

unsafe fn read_unsigned_long(object: *mut ffi::PyObject) -> Result<u64, ()> {
    let mut value: c_ulong = 0;
    // SAFETY: The borrowed object remains live in the argument tuple while the GIL is held. `value` is aligned writable storage of the requested size.
    let size = unsafe {
        PyLong_AsNativeBytes(
            object,
            (&mut value as *mut c_ulong).cast(),
            std::mem::size_of::<c_ulong>() as isize,
            PY_ASNATIVEBYTES_NATIVE_ENDIAN
                | PY_ASNATIVEBYTES_UNSIGNED_BUFFER
                | PY_ASNATIVEBYTES_REJECT_NEGATIVE
                | PY_ASNATIVEBYTES_ALLOW_INDEX,
        )
    };
    if size < 0 {
        return Err(());
    }
    if size as usize > std::mem::size_of::<c_ulong>() {
        unsafe {
            ffi::PyErr_SetString(
                ffi::PyExc_OverflowError,
                c"Python int too large for C unsigned long".as_ptr(),
            );
        }
        return Err(());
    }
    Ok(value as u64)
}

fn backend_error(module: *mut ffi::PyObject, error: BackendError) {
    match error {
        BackendError::UnsupportedDigest(name) => unsafe {
            match module_state(module) {
                Ok(state) if !(*state).unsupported_digestmod_error.is_null() => {
                    set_error(
                        (*state).unsupported_digestmod_error,
                        &format!("[digital envelope routines] unsupported hash algorithm {name}"),
                    );
                }
                _ => {
                    ffi::PyErr_SetString(ffi::PyExc_RuntimeError, c"missing digest exception".as_ptr());
                }
            }
        },
        BackendError::Value(message) => set_error(unsafe { ffi::PyExc_ValueError }, &message),
        BackendError::Overflow(message) => set_error(unsafe { ffi::PyExc_OverflowError }, message),
    }
}

unsafe fn capsule_state(
    module: *mut ffi::PyObject,
    capsule: *mut ffi::PyObject,
) -> Result<*mut CapsuleState, ()> {
    if unsafe { ffi::PyCapsule_IsValid(capsule, CAPSULE_NAME.as_ptr().cast()) } == 0 {
        unsafe { ffi::PyErr_SetString(ffi::PyExc_TypeError, c"invalid hash state".as_ptr()) };
        return Err(());
    }
    let pointer = unsafe { ffi::PyCapsule_GetPointer(capsule, CAPSULE_NAME.as_ptr().cast()) }
        .cast::<CapsuleState>();
    if pointer.is_null() {
        return Err(());
    }
    let module_state = unsafe { module_state(module)? };
    if unsafe { (*module_state).interpreter_token.is_null() } {
        unsafe { ffi::PyErr_SetString(ffi::PyExc_RuntimeError, c"hash backend is not initialized".as_ptr()) };
        return Err(());
    }
    // SAFETY: The live capsule validates this pointer; its destructor owns the Box until capsule deallocation.
    let capsule_state = unsafe { &*pointer };
    let token = unsafe { &*(*module_state).interpreter_token };
    if !Rc::ptr_eq(&capsule_state.interpreter, token) {
        unsafe { ffi::PyErr_SetString(ffi::PyExc_RuntimeError, c"hash state belongs to another interpreter".as_ptr()) };
        return Err(());
    }
    Ok(pointer)
}

unsafe fn new_capsule(
    module: *mut ffi::PyObject,
    state: NativeState,
) -> Result<*mut ffi::PyObject, ()> {
    let module_state = unsafe { module_state(module)? };
    if unsafe { (*module_state).interpreter_token.is_null() } {
        unsafe { ffi::PyErr_SetString(ffi::PyExc_RuntimeError, c"hash backend is not initialized".as_ptr()) };
        return Err(());
    }
    let capsule_state = Box::new(CapsuleState {
        // SAFETY: The module state owns this token until clear; this clone extends only its Rust allocation.
        interpreter: unsafe { (&*(*module_state).interpreter_token).clone() },
        state,
    });
    let pointer = Box::into_raw(capsule_state);
    let capsule = unsafe {
        ffi::PyCapsule_New(
            pointer.cast(),
            CAPSULE_NAME.as_ptr().cast(),
            Some(capsule_drop),
        )
    };
    if capsule.is_null() {
        unsafe { drop(Box::from_raw(pointer)) };
        return Err(());
    }
    Ok(capsule)
}

unsafe extern "C" fn capsule_drop(capsule: *mut ffi::PyObject) {
    if unsafe { ffi::PyCapsule_IsValid(capsule, CAPSULE_NAME.as_ptr().cast()) } != 0 {
        let pointer = unsafe { ffi::PyCapsule_GetPointer(capsule, CAPSULE_NAME.as_ptr().cast()) }
            .cast::<CapsuleState>();
        if !pointer.is_null() {
            // SAFETY: The capsule was created with Box::into_raw and its matching destructor owns it once.
            unsafe { drop(Box::from_raw(pointer)) };
        }
    }
}

fn object_tuple(items: [OwnedPyObject; 3]) -> Result<OwnedPyObject, ()> {
    unsafe {
        let tuple = OwnedPyObject::new(ffi::PyTuple_New(items.len() as isize))?;
        for (index, item) in items.into_iter().enumerate() {
            if ffi::PyTuple_SetItem(tuple.0, index as isize, item.into_ptr()) != 0 {
                return Err(());
            }
        }
        Ok(tuple)
    }
}

fn size_object(value: usize) -> Result<*mut ffi::PyObject, ()> {
    let object = unsafe { ffi::PyLong_FromSize_t(value) };
    if object.is_null() { Err(()) } else { Ok(object) }
}

fn bytes_object(value: &[u8]) -> Result<*mut ffi::PyObject, ()> {
    let object = unsafe {
        ffi::PyBytes_FromStringAndSize(value.as_ptr().cast(), value.len() as isize)
    };
    if object.is_null() { Err(()) } else { Ok(object) }
}

fn report_buffer_copy_error(error: BufferCopyError) {
    match error {
        BufferCopyError::TooLong(message) => {
            set_error(unsafe { ffi::PyExc_OverflowError }, message)
        }
        BufferCopyError::Allocation => unsafe {
            ffi::PyErr_NoMemory();
        },
    }
}

unsafe extern "C" fn hash_state_new(module: *mut ffi::PyObject, args: *mut ffi::PyObject) -> *mut ffi::PyObject {
    ffi_call(|| unsafe {
        require_arity(args, 2)?;
        let name = read_name(tuple_arg(args, 0)?)?;
        let mut hash = match new_hash(&name) {
            Ok(hash) => hash,
            Err(error) => {
                backend_error(module, error);
                return Err(());
            }
        };
        let buffer = Buffer::from_object(tuple_arg(args, 1)?)?;
        hash.update(buffer.as_slice());
        let metadata = (hash.digest_size, hash.block_size);
        let capsule = OwnedPyObject::new(new_capsule(module, NativeState::Hash(hash))?)?;
        let digest_size = OwnedPyObject::new(size_object(metadata.0)?)?;
        let block_size = OwnedPyObject::new(size_object(metadata.1)?)?;
        Ok(object_tuple([capsule, digest_size, block_size])?.into_ptr())
    })
}

unsafe extern "C" fn hmac_state_new(module: *mut ffi::PyObject, args: *mut ffi::PyObject) -> *mut ffi::PyObject {
    ffi_call(|| unsafe {
        require_arity(args, 2)?;
        let name = read_name(tuple_arg(args, 1)?)?;
        let key = Buffer::from_object(tuple_arg(args, 0)?)?;
        if key.len() > i32::MAX as usize {
            drop(key);
            set_error(ffi::PyExc_OverflowError, "key is too long.");
            return Err(());
        }
        let hmac = new_hmac(&name, key.as_slice());
        drop(key);
        let hmac = match hmac {
            Ok(hmac) => hmac,
            Err(error) => {
                backend_error(module, error);
                return Err(());
            }
        };
        let digest_size = hmac.digest_size;
        let block_size = hmac.block_size;
        let capsule = OwnedPyObject::new(new_capsule(module, NativeState::Hmac(hmac))?)?;
        let digest_size = OwnedPyObject::new(size_object(digest_size)?)?;
        let block_size = OwnedPyObject::new(size_object(block_size)?)?;
        Ok(object_tuple([capsule, digest_size, block_size])?.into_ptr())
    })
}

unsafe extern "C" fn state_update(module: *mut ffi::PyObject, args: *mut ffi::PyObject) -> *mut ffi::PyObject {
    ffi_call(|| unsafe {
        require_arity(args, 2)?;
        let capsule = tuple_arg(args, 0)?;
        let buffer = Buffer::from_object(tuple_arg(args, 1)?)?;
        let state_pointer = capsule_state(module, capsule)?;
        {
            let state = &mut (*state_pointer).state;
            match state {
                NativeState::Hash(hash) => hash.update(buffer.as_slice()),
                NativeState::Hmac(hmac) => hmac.update(buffer.as_slice()),
            }
        }
        drop(buffer);
        Ok(ffi::Py_NewRef(ffi::Py_None()))
    })
}

unsafe extern "C" fn state_copy(module: *mut ffi::PyObject, args: *mut ffi::PyObject) -> *mut ffi::PyObject {
    ffi_call(|| unsafe {
        require_arity(args, 1)?;
        let capsule = tuple_arg(args, 0)?;
        let state = (*capsule_state(module, capsule)?).state.clone();
        new_capsule(module, state)
    })
}

unsafe extern "C" fn state_digest(module: *mut ffi::PyObject, args: *mut ffi::PyObject) -> *mut ffi::PyObject {
    ffi_call(|| unsafe {
        require_arity(args, 1)?;
        let capsule = tuple_arg(args, 0)?;
        let digest = (*capsule_state(module, capsule)?).state.digest();
        bytes_object(&digest)
    })
}

unsafe extern "C" fn hmac_digest(module: *mut ffi::PyObject, args: *mut ffi::PyObject) -> *mut ffi::PyObject {
    ffi_call(|| unsafe {
        require_arity(args, 3)?;
        let name = read_name(tuple_arg(args, 2)?)?;
        let key_buffer = Buffer::from_object(tuple_arg(args, 0)?)?;
        let key = match key_buffer.copy("key is too long.") {
            Ok(key) => key,
            Err(error) => {
                drop(key_buffer);
                report_buffer_copy_error(error);
                return Err(());
            }
        };
        drop(key_buffer);
        let message_buffer = Buffer::from_object(tuple_arg(args, 1)?)?;
        let message = match message_buffer.copy("msg is too long.") {
            Ok(message) => message,
            Err(error) => {
                drop(message_buffer);
                report_buffer_copy_error(error);
                return Err(());
            }
        };
        drop(message_buffer);
        let mut hmac = match new_hmac(&name, &key) {
            Ok(hmac) => hmac,
            Err(error) => {
                backend_error(module, error);
                return Err(());
            }
        };
        let digest = {
            let _allow_threads = AllowThreads::new();
            hmac.update(&message);
            hmac.digest()
        };
        bytes_object(&digest)
    })
}

unsafe extern "C" fn pbkdf2_hmac_call(module: *mut ffi::PyObject, args: *mut ffi::PyObject) -> *mut ffi::PyObject {
    ffi_call(|| unsafe {
        require_arity(args, 5)?;
        let name = read_name(tuple_arg(args, 0)?)?;
        let iterations = read_long(tuple_arg(args, 3)?)?;
        let dklen_object = tuple_arg(args, 4)?;
        let dklen = if dklen_object == ffi::Py_None() {
            None
        } else {
            Some(read_long(dklen_object)?)
        };
        let password_buffer = Buffer::from_object(tuple_arg(args, 1)?)?;
        let salt_buffer = match Buffer::from_object(tuple_arg(args, 2)?) {
            Ok(buffer) => buffer,
            Err(()) => {
                drop(password_buffer);
                return Err(());
            }
        };
        let parameters = match pbkdf2_parameters(
            &name,
            password_buffer.len(),
            salt_buffer.len(),
            iterations,
            dklen,
        ) {
            Ok(parameters) => parameters,
            Err(error) => {
                drop(salt_buffer);
                drop(password_buffer);
                backend_error(module, error);
                return Err(());
            }
        };
        let password = match password_buffer.copy("password is too long.") {
            Ok(password) => password,
            Err(error) => {
                drop(salt_buffer);
                drop(password_buffer);
                report_buffer_copy_error(error);
                return Err(());
            }
        };
        let salt = match salt_buffer.copy("salt is too long.") {
            Ok(salt) => salt,
            Err(error) => {
                drop(salt_buffer);
                drop(password_buffer);
                report_buffer_copy_error(error);
                return Err(());
            }
        };
        drop(salt_buffer);
        drop(password_buffer);
        let result = {
            let _allow_threads = AllowThreads::new();
            pbkdf2_derive(parameters, &password, &salt)
        };
        match result {
            Ok(result) => bytes_object(&result),
            Err(error) => {
                backend_error(module, error);
                Err(())
            }
        }
    })
}

unsafe extern "C" fn scrypt_call(module: *mut ffi::PyObject, args: *mut ffi::PyObject) -> *mut ffi::PyObject {
    ffi_call(|| unsafe {
        require_arity(args, 7)?;
        let n = read_unsigned_long(tuple_arg(args, 2)?)?;
        let r = read_unsigned_long(tuple_arg(args, 3)?)?;
        let p = read_unsigned_long(tuple_arg(args, 4)?)?;
        let maxmem = read_long(tuple_arg(args, 5)?)?;
        let dklen = read_long(tuple_arg(args, 6)?)?;
        let password_buffer = Buffer::from_object(tuple_arg(args, 0)?)?;
        let salt_buffer = match Buffer::from_object(tuple_arg(args, 1)?) {
            Ok(buffer) => buffer,
            Err(()) => {
                drop(password_buffer);
                return Err(());
            }
        };
        let parameters = match scrypt_parameters(
            password_buffer.len(),
            salt_buffer.len(),
            n,
            r,
            p,
            maxmem,
            dklen,
        ) {
            Ok(parameters) => parameters,
            Err(error) => {
                drop(salt_buffer);
                drop(password_buffer);
                backend_error(module, error);
                return Err(());
            }
        };
        let password = match password_buffer.copy("password is too long") {
            Ok(password) => password,
            Err(error) => {
                drop(salt_buffer);
                drop(password_buffer);
                report_buffer_copy_error(error);
                return Err(());
            }
        };
        let salt = match salt_buffer.copy("salt is too long") {
            Ok(salt) => salt,
            Err(error) => {
                drop(salt_buffer);
                drop(password_buffer);
                report_buffer_copy_error(error);
                return Err(());
            }
        };
        drop(salt_buffer);
        drop(password_buffer);
        let result = {
            let _allow_threads = AllowThreads::new();
            scrypt_derive(parameters, &password, &salt)
        };
        match result {
            Ok(result) => bytes_object(&result),
            Err(error) => {
                backend_error(module, error);
                Err(())
            }
        }
    })
}

fn ffi_call(call: impl FnOnce() -> Result<*mut ffi::PyObject, ()>) -> *mut ffi::PyObject {
    match catch_unwind(AssertUnwindSafe(call)) {
        Ok(Ok(value)) if !value.is_null() => value,
        Ok(Ok(_)) => ptr::null_mut(),
        Ok(Err(())) => ptr::null_mut(),
        Err(_) => {
            unsafe {
                ffi::PyErr_SetString(ffi::PyExc_RuntimeError, c"Rust hash backend panicked".as_ptr());
            }
            ptr::null_mut()
        }
    }
}

unsafe extern "C" fn module_exec(module: *mut ffi::PyObject) -> c_int {
    match catch_unwind(AssertUnwindSafe(|| unsafe { module_exec_inner(module) })) {
        Ok(value) => value,
        Err(_) => {
            unsafe { ffi::PyErr_SetString(ffi::PyExc_RuntimeError, c"hash module initialization panicked".as_ptr()) };
            -1
        }
    }
}

unsafe fn module_exec_inner(module: *mut ffi::PyObject) -> c_int {
    let state = match unsafe { module_state(module) } {
        Ok(state) => state,
        Err(()) => return -1,
    };
    let token = unsafe { (*state).interpreter_token };
    let error = unsafe { (*state).unsupported_digestmod_error };
    if !token.is_null() && !error.is_null() {
        return 0;
    }
    if !token.is_null() || !error.is_null() {
        unsafe { ffi::PyErr_SetString(ffi::PyExc_RuntimeError, c"hash module initialized twice".as_ptr()) };
        return -1;
    }
    let token = Box::into_raw(Box::new(Rc::new(())));
    unsafe { ptr::addr_of_mut!((*state).interpreter_token).write(token) };
    let error_name = c"_hashlib_graviola.UnsupportedDigestmodError";
    let exception = unsafe {
        ffi::PyErr_NewException(
            error_name.as_ptr(),
            ffi::PyExc_ValueError,
            ptr::null_mut(),
        )
    };
    if exception.is_null() {
        return -1;
    }
    unsafe { ptr::addr_of_mut!((*state).unsupported_digestmod_error).write(exception) };
    if unsafe {
        ffi::PyModule_AddObjectRef(
            module,
            c"UnsupportedDigestmodError".as_ptr(),
            exception,
        )
    } != 0
    {
        return -1;
    }
    0
}

unsafe extern "C" fn module_traverse(
    module: *mut ffi::PyObject,
    visit: ffi::visitproc,
    arg: *mut c_void,
) -> c_int {
    let state = match unsafe { module_state(module) } {
        Ok(state) => state,
        Err(()) => return 0,
    };
    let error = unsafe { (*state).unsupported_digestmod_error };
    if error.is_null() {
        0
    } else {
        unsafe { visit(error, arg) }
    }
}

unsafe fn state_clear(state: *mut ModuleState) {
    if state.is_null() {
        return;
    }
    // SAFETY: CPython calls clear/free with this module's allocated state.
    let (error, token) = unsafe {
        let state = &mut *state;
        (
            std::mem::replace(&mut state.unsupported_digestmod_error, ptr::null_mut()),
            std::mem::replace(&mut state.interpreter_token, ptr::null_mut()),
        )
    };
    if !error.is_null() {
        unsafe { ffi::Py_DecRef(error) };
    }
    if !token.is_null() {
        unsafe { drop(Box::from_raw(token)) };
    }
}

unsafe extern "C" fn module_clear(module: *mut ffi::PyObject) -> c_int {
    let state = unsafe { ffi::PyModule_GetState(module) }.cast::<ModuleState>();
    unsafe { state_clear(state) };
    0
}

unsafe extern "C" fn module_free(state: *mut c_void) {
    // SAFETY: CPython 3.15 passes the module object to m_free, matching the module lifecycle callback API.
    let module_state = unsafe { ffi::PyModule_GetState(state.cast::<ffi::PyObject>()) }
        .cast::<ModuleState>();
    unsafe { state_clear(module_state) };
}

#[repr(transparent)]
struct StaticMethods([ffi::PyMethodDef; 9]);

// SAFETY: CPython reads these immutable definitions and the function pointers never reference Python objects.
unsafe impl Sync for StaticMethods {}

static METHODS: StaticMethods = StaticMethods([
    ffi::PyMethodDef {
        ml_name: c"hash_state_new".as_ptr(),
        ml_meth: ffi::PyMethodDefPointer { PyCFunction: hash_state_new },
        ml_flags: ffi::METH_VARARGS,
        ml_doc: ptr::null(),
    },
    ffi::PyMethodDef {
        ml_name: c"hmac_state_new".as_ptr(),
        ml_meth: ffi::PyMethodDefPointer { PyCFunction: hmac_state_new },
        ml_flags: ffi::METH_VARARGS,
        ml_doc: ptr::null(),
    },
    ffi::PyMethodDef {
        ml_name: c"state_update".as_ptr(),
        ml_meth: ffi::PyMethodDefPointer { PyCFunction: state_update },
        ml_flags: ffi::METH_VARARGS,
        ml_doc: ptr::null(),
    },
    ffi::PyMethodDef {
        ml_name: c"state_copy".as_ptr(),
        ml_meth: ffi::PyMethodDefPointer { PyCFunction: state_copy },
        ml_flags: ffi::METH_VARARGS,
        ml_doc: ptr::null(),
    },
    ffi::PyMethodDef {
        ml_name: c"state_digest".as_ptr(),
        ml_meth: ffi::PyMethodDefPointer { PyCFunction: state_digest },
        ml_flags: ffi::METH_VARARGS,
        ml_doc: ptr::null(),
    },
    ffi::PyMethodDef {
        ml_name: c"hmac_digest".as_ptr(),
        ml_meth: ffi::PyMethodDefPointer { PyCFunction: hmac_digest },
        ml_flags: ffi::METH_VARARGS,
        ml_doc: ptr::null(),
    },
    ffi::PyMethodDef {
        ml_name: c"pbkdf2_hmac".as_ptr(),
        ml_meth: ffi::PyMethodDefPointer { PyCFunction: pbkdf2_hmac_call },
        ml_flags: ffi::METH_VARARGS,
        ml_doc: ptr::null(),
    },
    ffi::PyMethodDef {
        ml_name: c"scrypt".as_ptr(),
        ml_meth: ffi::PyMethodDefPointer { PyCFunction: scrypt_call },
        ml_flags: ffi::METH_VARARGS,
        ml_doc: ptr::null(),
    },
    ffi::PyMethodDef::zeroed(),
]);

#[repr(transparent)]
struct StaticSlots([ffi::PyModuleDef_Slot; 4]);

// SAFETY: CPython reads these immutable slot definitions during import.
unsafe impl Sync for StaticSlots {}

static SLOTS: StaticSlots = StaticSlots([
    ffi::PyModuleDef_Slot { slot: ffi::Py_mod_exec, value: module_exec as *mut c_void },
    ffi::PyModuleDef_Slot {
        slot: ffi::Py_mod_multiple_interpreters,
        value: ffi::Py_MOD_PER_INTERPRETER_GIL_SUPPORTED,
    },
    ffi::PyModuleDef_Slot { slot: ffi::Py_mod_gil, value: ffi::Py_MOD_GIL_USED },
    ffi::PyModuleDef_Slot { slot: 0, value: ptr::null_mut() },
]);

struct StaticModuleDef(UnsafeCell<ffi::PyModuleDef>);

// SAFETY: PyModuleDef_Init access is serialized by MODULE_DEF_INIT, and CPython owns later access.
unsafe impl Sync for StaticModuleDef {}

static MODULE_DEF_INIT: Mutex<()> = Mutex::new(());

static MODULE_DEF: StaticModuleDef = StaticModuleDef(UnsafeCell::new(ffi::PyModuleDef {
    m_base: ffi::PyModuleDef_HEAD_INIT,
    m_name: c"_hashlib_graviola".as_ptr(),
    m_doc: ptr::null(),
    m_size: std::mem::size_of::<ModuleState>() as isize,
    m_methods: ptr::addr_of!(METHODS.0).cast::<ffi::PyMethodDef>().cast_mut(),
    m_slots: ptr::addr_of!(SLOTS.0).cast::<ffi::PyModuleDef_Slot>().cast_mut(),
    m_traverse: Some(module_traverse),
    m_clear: Some(module_clear),
    m_free: Some(module_free),
}));

#[unsafe(no_mangle)]
pub unsafe extern "C" fn PyInit__hashlib_graviola() -> *mut ffi::PyObject {
    let _guard = MODULE_DEF_INIT.lock().unwrap_or_else(|error| error.into_inner());
    let module_def = MODULE_DEF.0.get();
    unsafe { ffi::PyModuleDef_Init(module_def) }
}

