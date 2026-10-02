#include "Python.h"
#include <stddef.h>
#include <stdatomic.h>

#if SIZEOF_VOID_P != 8 || defined(Py_GIL_DISABLED)
#error "The observer requires the qualified 64-bit GIL ABI"
#endif
_Static_assert(sizeof(PyObject) == 16, "PyObject ABI");
_Static_assert(sizeof(PyMethodDef) == 32, "PyMethodDef ABI");
_Static_assert(sizeof(PyModuleDef_Base) == 40, "module base ABI");
_Static_assert(sizeof(PyModuleDef_Slot) == 16, "module slot ABI");
_Static_assert(sizeof(PyModuleDef) == 104, "module definition ABI");
_Static_assert(offsetof(PyObject, ob_type) == 8, "object type offset");
_Static_assert(offsetof(PyModuleDef, m_methods) == 64, "method offset");
_Static_assert(offsetof(PyModuleDef, m_slots) == 72, "slot offset");
_Static_assert(offsetof(PyModuleDef, m_free) == 96, "free offset");
_Static_assert(sizeof(Py_buffer) == 80, "buffer ABI");
_Static_assert(offsetof(Py_buffer, len) == 16, "buffer length offset");
_Static_assert(offsetof(Py_buffer, readonly) == 32, "buffer readonly offset");
_Static_assert(offsetof(Py_buffer, format) == 40, "buffer format offset");
_Static_assert(offsetof(Py_buffer, shape) == 48, "buffer shape offset");
_Static_assert(offsetof(Py_buffer, strides) == 56, "buffer strides offset");
_Static_assert(offsetof(Py_buffer, suboffsets) == 64, "buffer suboffsets offset");
_Static_assert(offsetof(Py_buffer, internal) == 72, "buffer internal offset");
_Static_assert(METH_KEYWORDS == 2, "keyword call ABI");
_Static_assert(Py_mod_exec == 85, "module exec ABI");
_Static_assert(METH_FASTCALL == 0x80, "fastcall ABI");
_Static_assert(Py_mod_multiple_interpreters == 86, "module slot ABI");

static PyMemAllocatorEx saved;
static atomic_flag lock = ATOMIC_FLAG_INIT;
static atomic_flag active = ATOMIC_FLAG_INIT;
static void *owners[64];
static unsigned long attempts, successes, frees, live, failed;
static unsigned long foreign_free, overflow, backend_failure, calloc_calls, realloc_calls;
static unsigned long fail_at;

static void acquire(void) { while (atomic_flag_test_and_set(&lock)) {} }
static void release(void) { atomic_flag_clear(&lock); }

static void *tracked_malloc(void *context, size_t size)
{
    acquire();
    unsigned long index = ++attempts;
    int reject = fail_at && index == fail_at;
    if (reject) failed++;
    release();
    if (reject) return NULL;
    void *pointer = saved.malloc(saved.ctx, size);
    acquire();
    if (!pointer) backend_failure++;
    else {
        successes++; live++;
        size_t slot;
        for (slot = 0; slot < 64 && owners[slot]; slot++) {}
        if (slot == 64) overflow++;
        else owners[slot] = pointer;
    }
    release();
    return pointer;
}

static void tracked_free(void *context, void *pointer)
{
    if (pointer) {
        acquire();
        size_t slot;
        for (slot = 0; slot < 64 && owners[slot] != pointer; slot++) {}
        if (slot == 64) foreign_free++;
        else { owners[slot] = NULL; frees++; live--; }
        release();
    }
    saved.free(saved.ctx, pointer);
}

static void *tracked_calloc(void *context, size_t count, size_t size)
{
    /* No selected call uses calloc; any observation invalidates the proof. */
    acquire(); calloc_calls++; release();
    return saved.calloc(saved.ctx, count, size);
}
static void *tracked_realloc(void *context, void *pointer, size_t size)
{
    if (!pointer) return tracked_malloc(context, size);
    acquire();
    realloc_calls++;
    size_t slot;
    for (slot = 0; slot < 64 && owners[slot] != pointer; slot++) {}
    if (slot == 64) foreign_free++;
    unsigned long index = ++attempts;
    int reject = fail_at && index == fail_at;
    if (reject) failed++;
    release();
    if (reject) return NULL;
    void *replacement = saved.realloc(saved.ctx, pointer, size);
    acquire();
    if (!replacement) backend_failure++;
    else if (slot != 64) owners[slot] = replacement;
    release();
    return replacement;
}

static PyObject *drive(PyObject *module, PyObject *args)
{
    PyObject *method, *values, *sink;
    unsigned long failure;
    int domain;
    if (!PyArg_ParseTuple(args, "OOOki", &method, &values, &sink, &failure, &domain)) return NULL;
    if (!PyTuple_CheckExact(values) || !PyByteArray_CheckExact(sink) ||
        (domain != PYMEM_DOMAIN_MEM && domain != PYMEM_DOMAIN_OBJ) ||
        !PyCFunction_CheckExact(method)) {
        PyErr_SetString(PyExc_TypeError, "driver requires a native method, tuple, bytearray and MEM or OBJ domain");
        return NULL;
    }
    int flags = PyCFunction_GetFlags(method);
    if (flags != METH_FASTCALL && flags != (METH_FASTCALL | METH_KEYWORDS)) {
        PyErr_SetString(PyExc_TypeError, "driver requires an exact native fastcall signature"); return NULL;
    }
    PyObject *self = PyCFunction_GetSelf(method);
    if (!PyModule_Check(self) || strcmp(PyModule_GetName(self), "_binascii_rs") != 0) {
        PyErr_SetString(PyExc_TypeError, "driver requires the binascii helper"); return NULL;
    }
    PyModuleDef *definition = PyModule_GetDef(self);
    int registered = 0;
    if (definition && definition->m_methods) {
        for (size_t i = 0; i < 21 && definition->m_methods[i].ml_name; i++) {
            PyMethodDef *entry = &definition->m_methods[i];
            if (entry->ml_flags == flags && entry->ml_meth == PyCFunction_GetFunction(method)) registered = 1;
        }
    }
    if (!registered) { PyErr_SetString(PyExc_TypeError, "driver requires a registered helper method"); return NULL; }
    Py_ssize_t nargs = PyTuple_GET_SIZE(values);
    if (nargs > 3) { PyErr_SetString(PyExc_ValueError, "driver allows at most three prepared arguments"); return NULL; }
    PyObject *arguments[3];
    for (Py_ssize_t i = 0; i < nargs; i++) {
        arguments[i] = PyTuple_GET_ITEM(values, i);
        if (!(PyBytes_CheckExact(arguments[i]) || arguments[i] == Py_True || arguments[i] == Py_False)) {
            PyErr_SetString(PyExc_TypeError, "only exact bytes and bool arguments are permitted in the allocator scope"); return NULL;
        }
    }
    /* All inputs, the destination and the exception singleton exist before
       the scope. Only the native helper and bytes disposal run under hooks. */
    PyErr_NoMemory(); PyErr_Clear();
    if (atomic_flag_test_and_set(&active)) {
        PyErr_SetString(PyExc_RuntimeError, "allocator observer already active"); return NULL;
    }
    acquire();
    memset(owners, 0, sizeof owners);
    attempts = successes = frees = live = failed = 0;
    foreign_free = overflow = backend_failure = calloc_calls = realloc_calls = 0;
    fail_at = failure;
    release();
    PyMem_GetAllocator(domain, &saved);
    PyMemAllocatorEx hooked = saved;
    hooked.malloc = tracked_malloc; hooked.calloc = tracked_calloc;
    hooked.realloc = tracked_realloc; hooked.free = tracked_free;
    PyMem_SetAllocator(domain, &hooked);
    PyCFunction function = PyCFunction_GetFunction(method);
    PyObject *result = flags == METH_FASTCALL
        ? _PyCFunctionFast_CAST(function)(self, arguments, nargs)
        : _PyCFunctionFastWithKeywords_CAST(function)(self, arguments, nargs, NULL);
    int bad_result = 0;
    if (result) {
        if (!PyBytes_CheckExact(result) || PyBytes_GET_SIZE(result) != PyByteArray_GET_SIZE(sink)) bad_result = 1;
        else memcpy(PyByteArray_AS_STRING(sink), PyBytes_AS_STRING(result), PyBytes_GET_SIZE(result));
        Py_DECREF(result);
    }
    PyMem_SetAllocator(domain, &saved);
    atomic_flag_clear(&active);
    if (!result) return NULL;
    if (bad_result) { PyErr_SetString(PyExc_AssertionError, "native output does not match the prepared destination"); return NULL; }
    Py_RETURN_NONE;
}

static PyObject *counts(PyObject *module, PyObject *unused)
{
    acquire();
    unsigned long values[10] = {attempts, successes, frees, live, failed,
        foreign_free, overflow, backend_failure, calloc_calls, realloc_calls};
    release();
    return Py_BuildValue("(kkkkkkkkkk)", values[0], values[1], values[2], values[3], values[4],
        values[5], values[6], values[7], values[8], values[9]);
}

static PyObject *module_contract(PyObject *module, PyObject *target)
{
    if (!PyModule_Check(target)) { PyErr_SetString(PyExc_TypeError, "module required"); return NULL; }
    PyModuleDef *definition = PyModule_GetDef(target);
    if (!definition || strcmp(definition->m_name, "_binascii_rs") != 0 ||
        definition->m_size != 0 || definition->m_traverse || definition->m_clear || definition->m_free ||
        !definition->m_methods || !definition->m_slots) {
        PyErr_SetString(PyExc_AssertionError, "binascii module state ABI"); return NULL;
    }
    const char *names[] = {"b2a_hex", "hexlify", "a2b_hex", "unhexlify", "crc32", "crc_hqx",
        "standard_b64encode", "urlsafe_b64encode", "b64decode", "b16encode", "b16decode",
        "b32encode", "b32decode", "b32hexencode", "b32hexdecode", "b85encode", "b85decode",
        "z85encode", "z85decode", "a85encode", "a85decode"};
    PyMethodDef *methods = definition->m_methods;
    for (size_t i = 0; i < 21; i++) {
        int flags = METH_FASTCALL | (i < 6 ? METH_KEYWORDS : 0);
        if (!methods[i].ml_name || strcmp(methods[i].ml_name, names[i]) ||
            !methods[i].ml_meth || !methods[i].ml_doc || methods[i].ml_flags != flags) {
            PyErr_SetString(PyExc_AssertionError, "binascii method table ABI"); return NULL;
        }
        PyObject *method = PyObject_GetAttrString(target, names[i]);
        if (!method) return NULL;
        int valid = PyCFunction_CheckExact(method) && PyCFunction_GetSelf(method) == target &&
            PyCFunction_GetFlags(method) == flags && PyCFunction_GetFunction(method) == methods[i].ml_meth;
        Py_DECREF(method);
        if (!valid) { PyErr_SetString(PyExc_AssertionError, "live native method signature differs from table"); return NULL; }
    }
    if (methods[21].ml_name || methods[21].ml_meth || methods[21].ml_flags || methods[21].ml_doc ||
        definition->m_slots[0].slot != Py_mod_exec || !definition->m_slots[0].value ||
        definition->m_slots[1].slot != Py_mod_multiple_interpreters ||
        definition->m_slots[1].value != Py_MOD_PER_INTERPRETER_GIL_SUPPORTED ||
        definition->m_slots[2].slot != 0 || definition->m_slots[2].value) {
        PyErr_SetString(PyExc_AssertionError, "binascii sentinel and interpreter slot ABI"); return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"drive", drive, METH_VARARGS, NULL},
    {"counts", counts, METH_NOARGS, NULL},
    {"module_contract", module_contract, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef definition = {PyModuleDef_HEAD_INIT, "_binascii_allocation_test", NULL, -1, methods};
PyMODINIT_FUNC PyInit__binascii_allocation_test(void) { return PyModule_Create(&definition); }
