#![no_std]

use core::cell::UnsafeCell;
use core::ffi::{c_char, c_int, c_void};
use core::mem::{MaybeUninit, size_of};
use core::ptr::{self, NonNull};
use core::slice;

use byteorder::{BigEndian, ByteOrder, LittleEndian};
mod ffi;

use ffi::{
    METH_FASTCALL, PyBool_FromLong, PyBool_Type, PyByteArray_Type, PyBytes_AsString, PyBytes_FromStringAndSize,
    PyBytes_Type, PyErr_Clear, PyErr_NoMemory, PyFloat_AsDouble, PyFloat_FromDouble,
    PyFloat_Type, PyLong_AsLongLong, PyLong_AsSsize_t, PyLong_AsUnsignedLongLong,
    PyLong_FromLongLong, PyLong_FromUnsignedLongLong, PyLong_Type, PyMethodDef,
    PyMethodDefFuncPointer, PyModuleDef, PyModuleDef_HEAD_INIT, PyModuleDef_Init, PyObject,
    PyObject_GetBuffer, PyObject_Type, PyTuple_GetItem, PyTuple_New, PyTuple_SetItem,
    PyTuple_Size, PyTypeObject, PyUnicode_AsUTF8AndSize, PyUnicode_Type, Py_DecRef,
    Py_ssize_t, Py_buffer, PyBuffer_Release, PyMem_Free, PyMem_Malloc, Py_NewRef,
};

// A standalone helper owns its abort handler; the static carrier owns one
// shared handler when this helper is linked into the interpreter.
#[cfg(not(feature = "static-module"))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { ffi::Py_FatalError(c"Rust struct helper panicked".as_ptr()) }
}

const PYBUF_SIMPLE: c_int = 0;
const MAX_FORMAT_SIZE: usize = 1 << 26;

#[derive(Clone, Copy)]
enum Endian {
    Big,
    Little,
}

#[derive(Clone, Copy)]
struct Operation {
    code: u8,
    count: usize,
    offset: usize,
    size: usize,
}

struct FormatPlan {
    endian: Endian,
    operations: OperationStorage,
    size: usize,
    value_count: usize,
}

struct OwnedObject {
    object: *mut PyObject,
}

impl OwnedObject {
    fn from_new(object: *mut PyObject) -> Option<Self> {
        if object.is_null() { None } else { Some(Self { object }) }
    }

    fn into_raw(mut self) -> *mut PyObject {
        let object = self.object;
        self.object = ptr::null_mut();
        object
    }
}

impl Drop for OwnedObject {
    fn drop(&mut self) {
        if !self.object.is_null() {
            unsafe { Py_DecRef(self.object) };
        }
    }
}

// The extra reference keeps the immutable UTF-8 storage alive even if a
// later Python allocation reenters this module.
struct FormatText {
    _owner: OwnedObject,
    text: *const u8,
    length: usize,
}

impl FormatText {
    fn as_slice(&self) -> &[u8] {
        unsafe { slice::from_raw_parts(self.text, self.length) }
    }
}

// Only the initialized prefix is exposed. Operations contain no owning
// fields, and PyMem supplies alignment for this integer-only record.
struct OperationStorage {
    data: NonNull<Operation>,
    length: usize,
    capacity: usize,
}

impl OperationStorage {
    fn new(capacity: usize) -> Result<Self, ()> {
        if capacity == 0 {
            return Ok(Self { data: NonNull::dangling(), length: 0, capacity: 0 });
        }
        let bytes = capacity.checked_mul(size_of::<Operation>())
            .filter(|bytes| *bytes <= isize::MAX as usize);
        let Some(bytes) = bytes else {
            unsafe { PyErr_NoMemory() };
            return Err(());
        };
        let data = unsafe { PyMem_Malloc(bytes) }.cast::<Operation>();
        let Some(data) = NonNull::new(data) else {
            unsafe { PyErr_NoMemory() };
            return Err(());
        };
        Ok(Self { data, length: 0, capacity })
    }

    fn push(&mut self, operation: Operation) -> bool {
        if self.length == self.capacity { return false; }
        unsafe { self.data.as_ptr().add(self.length).write(operation) };
        self.length += 1;
        true
    }

    fn as_slice(&self) -> &[Operation] {
        unsafe { slice::from_raw_parts(self.data.as_ptr(), self.length) }
    }
}

impl Drop for OperationStorage {
    fn drop(&mut self) {
        if self.capacity != 0 {
            unsafe { PyMem_Free(self.data.as_ptr().cast::<c_void>()) };
        }
    }
}

struct BorrowedBuffer {
    view: Py_buffer,
}

impl BorrowedBuffer {
    fn from_object(object: *mut PyObject) -> Option<Self> {
        let mut view = MaybeUninit::<Py_buffer>::uninit();
        unsafe {
            if PyObject_GetBuffer(object, view.as_mut_ptr(), PYBUF_SIMPLE) != 0 {
                PyErr_Clear();
                return None;
            }
            Some(Self {
                view: view.assume_init(),
            })
        }
    }

    fn as_slice(&self) -> &[u8] {
        unsafe { slice::from_raw_parts(self.view.buf.cast::<u8>(), self.view.len as usize) }
    }
}

impl Drop for BorrowedBuffer {
    fn drop(&mut self) {
        unsafe { PyBuffer_Release(&mut self.view) }
    }
}

unsafe fn is_exact_type(object: *mut PyObject, type_object: *mut PyTypeObject) -> bool {
    let actual_type = unsafe { PyObject_Type(object) };
    if actual_type.is_null() {
        unsafe { PyErr_Clear() };
        return false;
    }
    let matches = actual_type == type_object.cast::<PyObject>();
    unsafe { Py_DecRef(actual_type) };
    matches
}

unsafe fn exact_format(object: *mut PyObject) -> Option<FormatText> {
    let unicode_type = unsafe { ptr::addr_of_mut!(PyUnicode_Type) };
    if !unsafe { is_exact_type(object, unicode_type) } {
        return None;
    }
    let mut length = 0;
    let utf8 = unsafe { PyUnicode_AsUTF8AndSize(object, &mut length) };
    if utf8.is_null() || length < 0 {
        unsafe { PyErr_Clear() };
        return None;
    }
    let text = unsafe { slice::from_raw_parts(utf8.cast::<u8>(), length as usize) };
    if !text.is_ascii() {
        return None;
    }
    Some(FormatText {
        _owner: OwnedObject { object: unsafe { Py_NewRef(object) } },
        text: utf8.cast::<u8>(),
        length: length as usize,
    })
}

fn field_size(code: u8) -> Option<usize> {
    Some(match code {
        b'x' | b'c' | b'b' | b'B' | b'?' => 1,
        b'h' | b'H' => 2,
        b'i' | b'I' | b'l' | b'L' | b'f' => 4,
        b'q' | b'Q' | b'd' => 8,
        b's' => 1,
        _ => return None,
    })
}

fn scan_format(format: &[u8], mut emit: impl FnMut(Operation) -> bool)
    -> Option<(Endian, usize, usize, usize)>
{
    let (endian, mut index) = match format.first().copied() {
        Some(b'<') => (Endian::Little, 1),
        Some(b'>') | Some(b'!') => (Endian::Big, 1),
        Some(b'=') => {
            if cfg!(target_endian = "little") {
                (Endian::Little, 1)
            } else {
                (Endian::Big, 1)
            }
        }
        // The implicit and explicit native modes also define alignment and
        // pointer-sized fields, which remain owned by CPython.
        _ => return None,
    };

    let mut operation_count = 0usize;
    let mut size = 0usize;
    let mut value_count = 0usize;
    while index < format.len() {
        let mut count = 0usize;
        let mut has_count = false;
        while index < format.len() && format[index].is_ascii_digit() {
            has_count = true;
            count = count
                .checked_mul(10)?
                .checked_add((format[index] - b'0') as usize)?;
            if count > MAX_FORMAT_SIZE {
                return None;
            }
            index += 1;
        }
        if !has_count {
            count = 1;
        }
        let code = *format.get(index)?;
        let width = field_size(code)?;
        index += 1;

        let operation_size = count.checked_mul(width)?;
        let next_size = size.checked_add(operation_size)?;
        if next_size > MAX_FORMAT_SIZE {
            return None;
        }
        let consumes = match code {
            b'x' => 0,
            b's' => 1,
            _ => count,
        };
        value_count = value_count.checked_add(consumes)?;
        if value_count > MAX_FORMAT_SIZE {
            return None;
        }
        operation_count = operation_count.checked_add(1)?;
        if !emit(Operation {
            code,
            count,
            offset: size,
            size: operation_size,
        }) { return None; }
        size = next_size;
    }
    Some((endian, size, value_count, operation_count))
}

fn parse_format(format: &[u8]) -> Result<Option<FormatPlan>, ()> {
    // Validate the entire format before allocating: unsupported syntax and
    // size overflow must still reach the native struct error oracle.
    let Some((endian, size, value_count, operation_count)) = scan_format(format, |_| true) else {
        return Ok(None);
    };
    let mut operations = OperationStorage::new(operation_count)?;
    // The format owner keeps this immutable text unchanged between scans.
    if scan_format(format, |operation| operations.push(operation)).is_none() {
        return Ok(None);
    }
    Ok(Some(FormatPlan {
        endian,
        operations,
        size,
        value_count,
    }))
}

unsafe fn tuple_item(tuple: *mut PyObject, index: usize) -> *mut PyObject {
    unsafe { PyTuple_GetItem(tuple, index as Py_ssize_t) }
}

unsafe fn exact_integer(object: *mut PyObject) -> bool {
    let integer = unsafe { ptr::addr_of_mut!(PyLong_Type) };
    let boolean = unsafe { ptr::addr_of_mut!(PyBool_Type) };
    unsafe { is_exact_type(object, integer) || is_exact_type(object, boolean) }
}

unsafe fn signed_value(object: *mut PyObject) -> Option<i64> {
    if !unsafe { exact_integer(object) } {
        return None;
    }
    let value = unsafe { PyLong_AsLongLong(object) };
    if value == -1 && !unsafe { ffi::PyErr_Occurred() }.is_null() {
        unsafe { PyErr_Clear() };
        return None;
    }
    Some(value)
}

unsafe fn unsigned_value(object: *mut PyObject) -> Option<u64> {
    if !unsafe { exact_integer(object) } {
        return None;
    }
    let value = unsafe { PyLong_AsUnsignedLongLong(object) };
    if value == u64::MAX && !unsafe { ffi::PyErr_Occurred() }.is_null() {
        unsafe { PyErr_Clear() };
        return None;
    }
    Some(value)
}

unsafe fn exact_buffer(object: *mut PyObject) -> bool {
    let bytes = unsafe { ptr::addr_of_mut!(PyBytes_Type) };
    let bytearray = unsafe { ptr::addr_of_mut!(PyByteArray_Type) };
    unsafe { is_exact_type(object, bytes) || is_exact_type(object, bytearray) }
}

unsafe fn encode_integer(
    code: u8,
    endian: Endian,
    object: *mut PyObject,
    output: &mut [u8],
) -> bool {
    match code {
        b'b' => {
            let Some(value) = (unsafe { signed_value(object) }) else {
                return false;
            };
            if !(i8::MIN as i64..=i8::MAX as i64).contains(&value) {
                return false;
            }
            output[0] = value as i8 as u8;
        }
        b'B' => {
            let Some(value) = (unsafe { unsigned_value(object) }) else {
                return false;
            };
            if value > u8::MAX as u64 {
                return false;
            }
            output[0] = value as u8;
        }
        b'h' => {
            let Some(value) = (unsafe { signed_value(object) }) else {
                return false;
            };
            if !(i16::MIN as i64..=i16::MAX as i64).contains(&value) {
                return false;
            }
            match endian {
                Endian::Big => BigEndian::write_i16(output, value as i16),
                Endian::Little => LittleEndian::write_i16(output, value as i16),
            }
        }
        b'H' => {
            let Some(value) = (unsafe { unsigned_value(object) }) else {
                return false;
            };
            if value > u16::MAX as u64 {
                return false;
            }
            match endian {
                Endian::Big => BigEndian::write_u16(output, value as u16),
                Endian::Little => LittleEndian::write_u16(output, value as u16),
            }
        }
        b'i' | b'l' => {
            let Some(value) = (unsafe { signed_value(object) }) else {
                return false;
            };
            if !(i32::MIN as i64..=i32::MAX as i64).contains(&value) {
                return false;
            }
            match endian {
                Endian::Big => BigEndian::write_i32(output, value as i32),
                Endian::Little => LittleEndian::write_i32(output, value as i32),
            }
        }
        b'I' | b'L' => {
            let Some(value) = (unsafe { unsigned_value(object) }) else {
                return false;
            };
            if value > u32::MAX as u64 {
                return false;
            }
            match endian {
                Endian::Big => BigEndian::write_u32(output, value as u32),
                Endian::Little => LittleEndian::write_u32(output, value as u32),
            }
        }
        b'q' => {
            let Some(value) = (unsafe { signed_value(object) }) else {
                return false;
            };
            match endian {
                Endian::Big => BigEndian::write_i64(output, value),
                Endian::Little => LittleEndian::write_i64(output, value),
            }
        }
        b'Q' => {
            let Some(value) = (unsafe { unsigned_value(object) }) else {
                return false;
            };
            match endian {
                Endian::Big => BigEndian::write_u64(output, value),
                Endian::Little => LittleEndian::write_u64(output, value),
            }
        }
        b'?' => {
            if !(unsafe { exact_integer(object) }) {
                return false;
            }
            let truth = unsafe { ffi::PyObject_IsTrue(object) };
            if truth < 0 {
                unsafe { PyErr_Clear() };
                return false;
            }
            output[0] = u8::from(truth != 0);
        }
        b'f' | b'd' => {
            let float_type = unsafe { ptr::addr_of_mut!(PyFloat_Type) };
            if !unsafe { is_exact_type(object, float_type) } {
                return false;
            }
            let value = unsafe { PyFloat_AsDouble(object) };
            if code == b'f' {
                if value.is_finite() && value.abs() > f32::MAX as f64 {
                    return false;
                }
                let narrowed = value as f32;
                match endian {
                    Endian::Big => BigEndian::write_f32(output, narrowed),
                    Endian::Little => LittleEndian::write_f32(output, narrowed),
                }
            } else {
                match endian {
                    Endian::Big => BigEndian::write_f64(output, value),
                    Endian::Little => LittleEndian::write_f64(output, value),
                }
            }
        }
        _ => return false,
    }
    true
}

unsafe fn pack_values(
    plan: &FormatPlan,
    values: *mut PyObject,
    value_count: Py_ssize_t,
) -> Result<Option<OwnedObject>, ()> {
    if value_count < 0 || value_count as usize != plan.value_count {
        return Ok(None);
    }
    let Some(bytes) = OwnedObject::from_new(unsafe {
        PyBytes_FromStringAndSize(ptr::null(), plan.size as Py_ssize_t)
    }) else { return Err(()); };
    // The nonempty bytes object is private until every field succeeds. No
    // callback or source buffer can hold a reference to its mutable storage.
    let output = if plan.size == 0 {
        &mut []
    } else {
        let data = unsafe { PyBytes_AsString(bytes.object) };
        if data.is_null() { return Err(()); }
        unsafe {
            ptr::write_bytes(data.cast::<u8>(), 0, plan.size);
            slice::from_raw_parts_mut(data.cast::<u8>(), plan.size)
        }
    };
    let mut value_index = 0usize;
    for operation in plan.operations.as_slice() {
        match operation.code {
            b'x' => {}
            b's' => {
                let object = unsafe { tuple_item(values, value_index) };
                value_index += 1;
                if !unsafe { exact_buffer(object) } {
                    return Ok(None);
                }
                let Some(buffer) = BorrowedBuffer::from_object(object) else { return Ok(None); };
                let source = buffer.as_slice();
                let copied = source.len().min(operation.size);
                output[operation.offset..operation.offset + copied]
                    .copy_from_slice(&source[..copied]);
            }
            b'c' => {
                for repeat in 0..operation.count {
                    let object = unsafe { tuple_item(values, value_index) };
                    value_index += 1;
                    if !unsafe { exact_buffer(object) } {
                        return Ok(None);
                    }
                    let Some(buffer) = BorrowedBuffer::from_object(object) else { return Ok(None); };
                    let source = buffer.as_slice();
                    if source.len() != 1 {
                        return Ok(None);
                    }
                    output[operation.offset + repeat] = source[0];
                }
            }
            code => {
                let Some(width) = field_size(code) else { return Ok(None); };
                for repeat in 0..operation.count {
                    let object = unsafe { tuple_item(values, value_index) };
                    value_index += 1;
                    let start = operation.offset + repeat * width;
                    let target = &mut output[start..start + width];
                    if !unsafe { encode_integer(code, plan.endian, object, target) } {
                        return Ok(None);
                    }
                }
            }
        }
    }
    Ok(Some(bytes))
}

fn return_bytes(bytes: &[u8]) -> *mut PyObject {
    if bytes.len() > Py_ssize_t::MAX as usize {
        unsafe { PyErr_NoMemory() };
        return ptr::null_mut();
    }
    unsafe {
        PyBytes_FromStringAndSize(bytes.as_ptr().cast::<c_char>(), bytes.len() as Py_ssize_t)
    }
}

unsafe fn pack_call(args: *mut *mut PyObject, nargs: Py_ssize_t) -> *mut PyObject {
    if nargs != 2 {
        return not_handled();
    }
    let format = unsafe { exact_format(*args) };
    let Some(format) = format else {
        return not_handled();
    };
    let plan = match parse_format(format.as_slice()) {
        Ok(Some(plan)) => plan,
        Ok(None) => return not_handled(),
        Err(()) => return ptr::null_mut(),
    };
    let values = unsafe { *args.add(1) };
    let tuple_type = unsafe { ptr::addr_of_mut!(ffi::PyTuple_Type) };
    if !unsafe { is_exact_type(values, tuple_type) } {
        return not_handled();
    }
    let count = unsafe { PyTuple_Size(values) };
    match unsafe { pack_values(&plan, values, count) } {
        Ok(Some(bytes)) => bytes.into_raw(),
        Ok(None) => not_handled(),
        Err(()) => ptr::null_mut(),
    }
}

fn not_handled() -> *mut PyObject {
    unsafe { PyBool_FromLong(0) }
}

unsafe fn decoded_value(code: u8, endian: Endian, input: &[u8]) -> *mut PyObject {
    match code {
        b'b' => unsafe { PyLong_FromLongLong((input[0] as i8) as i64) },
        b'B' => unsafe { PyLong_FromUnsignedLongLong(input[0] as u64) },
        b'h' => {
            let value = match endian {
                Endian::Big => BigEndian::read_i16(input),
                Endian::Little => LittleEndian::read_i16(input),
            };
            unsafe { PyLong_FromLongLong(value as i64) }
        }
        b'H' => {
            let value = match endian {
                Endian::Big => BigEndian::read_u16(input),
                Endian::Little => LittleEndian::read_u16(input),
            };
            unsafe { PyLong_FromUnsignedLongLong(value as u64) }
        }
        b'i' | b'l' => {
            let value = match endian {
                Endian::Big => BigEndian::read_i32(input),
                Endian::Little => LittleEndian::read_i32(input),
            };
            unsafe { PyLong_FromLongLong(value as i64) }
        }
        b'I' | b'L' => {
            let value = match endian {
                Endian::Big => BigEndian::read_u32(input),
                Endian::Little => LittleEndian::read_u32(input),
            };
            unsafe { PyLong_FromUnsignedLongLong(value as u64) }
        }
        b'q' => {
            let value = match endian {
                Endian::Big => BigEndian::read_i64(input),
                Endian::Little => LittleEndian::read_i64(input),
            };
            unsafe { PyLong_FromLongLong(value) }
        }
        b'Q' => {
            let value = match endian {
                Endian::Big => BigEndian::read_u64(input),
                Endian::Little => LittleEndian::read_u64(input),
            };
            unsafe { PyLong_FromUnsignedLongLong(value) }
        }
        b'?' => unsafe { PyBool_FromLong(if input[0] != 0 { 1 } else { 0 }) },
        b'f' => {
            let value = match endian {
                Endian::Big => BigEndian::read_f32(input),
                Endian::Little => LittleEndian::read_f32(input),
            };
            unsafe { PyFloat_FromDouble(value as f64) }
        }
        b'd' => {
            let value = match endian {
                Endian::Big => BigEndian::read_f64(input),
                Endian::Little => LittleEndian::read_f64(input),
            };
            unsafe { PyFloat_FromDouble(value) }
        }
        b'c' => return_bytes(input),
        _ => ptr::null_mut(),
    }
}

unsafe fn unpack_values(plan: &FormatPlan, input: &[u8]) -> *mut PyObject {
    if input.len() != plan.size {
        return not_handled();
    }
    let tuple = unsafe { PyTuple_New(plan.value_count as Py_ssize_t) };
    if tuple.is_null() {
        return ptr::null_mut();
    }
    let mut value_index = 0usize;
    for operation in plan.operations.as_slice() {
        match operation.code {
            b'x' => {}
            b's' => {
                let start = operation.offset;
                let value = return_bytes(&input[start..start + operation.size]);
                if value.is_null()
                    || unsafe { PyTuple_SetItem(tuple, value_index as Py_ssize_t, value) } != 0
                {
                    if !value.is_null() {
                        unsafe { Py_DecRef(tuple) };
                    }
                    return ptr::null_mut();
                }
                value_index += 1;
            }
            code => {
                let width = field_size(code).unwrap();
                for repeat in 0..operation.count {
                    let start = operation.offset + repeat * width;
                    let value = unsafe {
                        decoded_value(code, plan.endian, &input[start..start + width])
                    };
                    if value.is_null()
                        || unsafe {
                            PyTuple_SetItem(tuple, value_index as Py_ssize_t, value)
                        } != 0
                    {
                        if !value.is_null() {
                            unsafe { Py_DecRef(tuple) };
                        }
                        return ptr::null_mut();
                    }
                    value_index += 1;
                }
            }
        }
    }
    tuple
}

unsafe fn unpack_call(
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
    from_offset: bool,
) -> *mut PyObject {
    if (!from_offset && nargs != 2) || (from_offset && nargs != 3) {
        return not_handled();
    }
    let format = unsafe { exact_format(*args) };
    let Some(format) = format else {
        return not_handled();
    };
    let plan = match parse_format(format.as_slice()) {
        Ok(Some(plan)) => plan,
        Ok(None) => return not_handled(),
        Err(()) => return ptr::null_mut(),
    };
    let buffer_object = unsafe { *args.add(1) };
    if !unsafe { exact_buffer(buffer_object) } {
        return not_handled();
    }
    let buffer = match BorrowedBuffer::from_object(buffer_object) {
        Some(buffer) => buffer,
        None => return not_handled(),
    };
    let offset = if from_offset {
        let offset_object = unsafe { *args.add(2) };
        if !unsafe { exact_integer(offset_object) } {
            return not_handled();
        }
        let offset = unsafe { PyLong_AsSsize_t(offset_object) };
        if offset == -1 && !unsafe { ffi::PyErr_Occurred() }.is_null() {
            unsafe { PyErr_Clear() };
            return not_handled();
        }
        if offset < 0 {
            return not_handled();
        }
        offset as usize
    } else {
        0
    };
    let input = buffer.as_slice();
    let Some(end) = offset.checked_add(plan.size) else {
        return not_handled();
    };
    if end > input.len() || (!from_offset && end != input.len()) {
        return not_handled();
    }
    unsafe { unpack_values(&plan, &input[offset..end]) }
}

unsafe extern "C" fn pack(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { pack_call(args, nargs) }
}

unsafe extern "C" fn unpack(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { unpack_call(args, nargs, false) }
}

unsafe extern "C" fn unpack_from(
    _module: *mut PyObject,
    args: *mut *mut PyObject,
    nargs: Py_ssize_t,
) -> *mut PyObject {
    unsafe { unpack_call(args, nargs, true) }
}

pub extern "C" fn _struct_rs_clear(_object: *mut PyObject) -> c_int {
    0
}

pub extern "C" fn _struct_rs_free(_object: *mut c_void) {}

pub struct ModuleDef {
    ffi: UnsafeCell<PyModuleDef>,
}

impl ModuleDef {
    fn init_multi_phase(&'static self) -> *mut PyObject {
        unsafe { PyModuleDef_Init(self.ffi.get()) }
    }
}

unsafe impl Sync for ModuleDef {}

pub static _STRUCT_RS_MODULE_METHODS: [PyMethodDef; 4] = [
    PyMethodDef {
        ml_name: c"pack".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: pack,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Pack supported standard binary records".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"unpack".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: unpack,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Unpack supported standard binary records".as_ptr() as *mut c_char,
    },
    PyMethodDef {
        ml_name: c"unpack_from".as_ptr() as *mut c_char,
        ml_meth: PyMethodDefFuncPointer {
            PyCFunctionFast: unpack_from,
        },
        ml_flags: METH_FASTCALL,
        ml_doc: c"Unpack a standard binary record at an offset".as_ptr() as *mut c_char,
    },
    PyMethodDef::zeroed(),
];

pub static _STRUCT_RS_MODULE: ModuleDef = ModuleDef {
    ffi: UnsafeCell::new(PyModuleDef {
        m_base: PyModuleDef_HEAD_INIT,
        m_name: c"_struct_rs".as_ptr() as *mut _,
        m_doc: c"Rust implementation of standard binary record packing".as_ptr() as *mut _,
        m_size: 0,
        m_methods: &_STRUCT_RS_MODULE_METHODS as *const PyMethodDef as *mut _,
        m_slots: ptr::null_mut(),
        m_traverse: None,
        m_clear: Some(_struct_rs_clear),
        m_free: Some(_struct_rs_free),
    }),
};

#[unsafe(no_mangle)]
pub extern "C" fn PyInit__struct_rs() -> *mut PyObject {
    _STRUCT_RS_MODULE.init_multi_phase()
}
