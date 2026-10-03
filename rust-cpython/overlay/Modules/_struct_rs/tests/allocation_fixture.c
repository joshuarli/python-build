#include "Python.h"
#include <stddef.h>
#include <stdatomic.h>
#include <stdint.h>

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
_Static_assert(METH_FASTCALL == 0x80, "fastcall ABI");
_Static_assert(Py_mod_multiple_interpreters == 86, "module slot ABI");

_Static_assert(sizeof(long) == 8 && sizeof(long long) == 8 && sizeof(double) == 8, "scalar C ABI");
_Static_assert(sizeof(Py_ssize_t) == 8, "signed size ABI");
_Static_assert(sizeof(Py_buffer) == 80, "buffer ABI");
_Static_assert(offsetof(Py_buffer, len) == 16, "buffer length offset");
_Static_assert(offsetof(Py_buffer, readonly) == 32, "buffer readonly offset");
_Static_assert(offsetof(Py_buffer, format) == 40, "buffer format offset");
_Static_assert(offsetof(Py_buffer, shape) == 48, "buffer shape offset");
_Static_assert(offsetof(Py_buffer, strides) == 56, "buffer strides offset");
_Static_assert(offsetof(Py_buffer, suboffsets) == 64, "buffer suboffsets offset");
_Static_assert(offsetof(Py_buffer, internal) == 72, "buffer internal offset");
_Static_assert(_Py_STATIC_IMMORTAL_INITIAL_REFCNT == ((UINT64_C(3) << 30) | (UINT64_C(5) << 48)), "static object header ABI");

/* Compare the precise used C signatures with the configured Python headers.
   These expressions do not call Python or install allocation callbacks. */
_Static_assert(_Generic(&PyBool_FromLong, PyObject *(*)(long): 1, default: 0), "PyBool_FromLong signature");
_Static_assert(_Generic(&PyBytes_AsString, char *(*)(PyObject *): 1, default: 0), "PyBytes_AsString signature");
_Static_assert(_Generic(&PyBytes_FromStringAndSize, PyObject *(*)(const char *, Py_ssize_t): 1, default: 0), "PyBytes_FromStringAndSize signature");
_Static_assert(_Generic(&PyErr_Clear, void (*)(void): 1, default: 0), "PyErr_Clear signature");
_Static_assert(_Generic(&PyErr_NoMemory, PyObject *(*)(void): 1, default: 0), "PyErr_NoMemory signature");
_Static_assert(_Generic(&PyErr_Occurred, PyObject *(*)(void): 1, default: 0), "PyErr_Occurred signature");
_Static_assert(_Generic(&PyFloat_AsDouble, double (*)(PyObject *): 1, default: 0), "PyFloat_AsDouble signature");
_Static_assert(_Generic(&PyFloat_FromDouble, PyObject *(*)(double): 1, default: 0), "PyFloat_FromDouble signature");
_Static_assert(_Generic(&PyLong_AsLongLong, long long (*)(PyObject *): 1, default: 0), "PyLong_AsLongLong signature");
_Static_assert(_Generic(&PyLong_AsSsize_t, Py_ssize_t (*)(PyObject *): 1, default: 0), "PyLong_AsSsize_t signature");
_Static_assert(_Generic(&PyLong_AsUnsignedLongLong, unsigned long long (*)(PyObject *): 1, default: 0), "PyLong_AsUnsignedLongLong signature");
_Static_assert(_Generic(&PyLong_FromLongLong, PyObject *(*)(long long): 1, default: 0), "PyLong_FromLongLong signature");
_Static_assert(_Generic(&PyLong_FromUnsignedLongLong, PyObject *(*)(unsigned long long): 1, default: 0), "PyLong_FromUnsignedLongLong signature");
_Static_assert(_Generic(&PyObject_GetBuffer, int (*)(PyObject *, Py_buffer *, int): 1, default: 0), "PyObject_GetBuffer signature");
_Static_assert(_Generic(&PyObject_IsTrue, int (*)(PyObject *): 1, default: 0), "PyObject_IsTrue signature");
_Static_assert(_Generic(&PyObject_Type, PyObject *(*)(PyObject *): 1, default: 0), "PyObject_Type signature");
_Static_assert(_Generic(&PyTuple_GetItem, PyObject *(*)(PyObject *, Py_ssize_t): 1, default: 0), "PyTuple_GetItem signature");
_Static_assert(_Generic(&PyTuple_New, PyObject *(*)(Py_ssize_t): 1, default: 0), "PyTuple_New signature");
_Static_assert(_Generic(&PyTuple_SetItem, int (*)(PyObject *, Py_ssize_t, PyObject *): 1, default: 0), "PyTuple_SetItem signature");
_Static_assert(_Generic(&PyTuple_Size, Py_ssize_t (*)(PyObject *): 1, default: 0), "PyTuple_Size signature");
_Static_assert(_Generic(&PyUnicode_AsUTF8AndSize, const char *(*)(PyObject *, Py_ssize_t *): 1, default: 0), "PyUnicode_AsUTF8AndSize signature");
_Static_assert(_Generic(&Py_DecRef, void (*)(PyObject *): 1, default: 0), "Py_DecRef signature");
_Static_assert(_Generic(&PyBuffer_Release, void (*)(Py_buffer *): 1, default: 0), "PyBuffer_Release signature");
_Static_assert(_Generic(&PyMem_Free, void (*)(void *): 1, default: 0), "PyMem_Free signature");
_Static_assert(_Generic(&PyMem_Malloc, void *(*)(size_t): 1, default: 0), "PyMem_Malloc signature");
_Static_assert(_Generic(&Py_NewRef, PyObject *(*)(PyObject *): 1, default: 0), "Py_NewRef signature");
_Static_assert(_Generic(&PyModuleDef_Init, PyObject *(*)(PyModuleDef *): 1, default: 0), "PyModuleDef_Init signature");
_Static_assert(_Generic(&Py_FatalError, void (*)(const char *): 1, default: 0), "Py_FatalError signature");
_Static_assert(_Generic(&PyBool_Type, PyTypeObject *: 1, default: 0), "PyBool_Type address type");
_Static_assert(_Generic(&PyByteArray_Type, PyTypeObject *: 1, default: 0), "PyByteArray_Type address type");
_Static_assert(_Generic(&PyBytes_Type, PyTypeObject *: 1, default: 0), "PyBytes_Type address type");
_Static_assert(_Generic(&PyFloat_Type, PyTypeObject *: 1, default: 0), "PyFloat_Type address type");
_Static_assert(_Generic(&PyLong_Type, PyTypeObject *: 1, default: 0), "PyLong_Type address type");
_Static_assert(_Generic(&PyTuple_Type, PyTypeObject *: 1, default: 0), "PyTuple_Type address type");
_Static_assert(_Generic(&PyUnicode_Type, PyTypeObject *: 1, default: 0), "PyUnicode_Type address type");

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
    acquire(); calloc_calls++; release();
    return saved.calloc(saved.ctx, count, size);
}
static void *tracked_realloc(void *context, void *pointer, size_t size)
{
    acquire(); realloc_calls++; release();
    return saved.realloc(saved.ctx, pointer, size);
}

static PyObject *drive(PyObject *module, PyObject *args)
{
    PyObject *method, *left, *right;
    unsigned long failure;
    if (!PyArg_ParseTuple(args, "OOOk", &method, &left, &right, &failure)) return NULL;
    if (!PyCFunction_CheckExact(method) || PyCFunction_GetFlags(method) != METH_FASTCALL) {
        PyErr_SetString(PyExc_TypeError, "driver requires an exact native fastcall method");
        return NULL;
    }
    PyObject *self = PyCFunction_GetSelf(method);
    if (!PyModule_Check(self) || strcmp(PyModule_GetName(self), "_struct_rs") != 0) {
        PyErr_SetString(PyExc_TypeError, "driver requires the struct helper");
        return NULL;
    }
    PyObject *pack = PyObject_GetAttrString(self, "pack");
    if (!pack) return NULL;
    PyObject *unpack = PyObject_GetAttrString(self, "unpack");
    if (!unpack) { Py_DECREF(pack); return NULL; }
    int supported = method == pack || method == unpack;
    Py_DECREF(pack); Py_DECREF(unpack);
    if (!supported) {
        PyErr_SetString(PyExc_TypeError, "driver requires a two-argument struct helper");
        return NULL;
    }
    /* Prepare UTF-8 and the exception singleton before the allocator scope.
       Only the native helper executes while the MEM callbacks are installed. */
    if (PyUnicode_Check(left) && !PyUnicode_AsUTF8(left)) return NULL;
    if (PyUnicode_Check(right) && !PyUnicode_AsUTF8(right)) return NULL;
    PyErr_NoMemory(); PyErr_Clear();
    if (atomic_flag_test_and_set(&active)) {
        PyErr_SetString(PyExc_RuntimeError, "allocator observer already active");
        return NULL;
    }
    acquire();
    memset(owners, 0, sizeof owners);
    attempts = successes = frees = live = failed = 0;
    foreign_free = overflow = backend_failure = calloc_calls = realloc_calls = 0;
    fail_at = failure;
    release();
    PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &saved);
    PyMemAllocatorEx hooked = saved;
    hooked.malloc = tracked_malloc; hooked.calloc = tracked_calloc;
    hooked.realloc = tracked_realloc; hooked.free = tracked_free;
    PyObject *values[2] = {left, right};
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &hooked);
    PyObject *result = _PyCFunctionFast_CAST(PyCFunction_GetFunction(method))(self, values, 2);
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &saved);
    atomic_flag_clear(&active);
    return result;
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
    if (!definition || strcmp(definition->m_name, "_struct_rs") != 0 ||
        definition->m_size != 0 || definition->m_traverse || !definition->m_clear || !definition->m_free ||
        !definition->m_methods || definition->m_slots) {
        PyErr_SetString(PyExc_AssertionError, "struct module state ABI"); return NULL;
    }
    PyMethodDef *methods = definition->m_methods;
    if (!methods[0].ml_name || !methods[1].ml_name || !methods[2].ml_name || methods[3].ml_name ||
        strcmp(methods[0].ml_name, "pack") || strcmp(methods[1].ml_name, "unpack") ||
        strcmp(methods[2].ml_name, "unpack_from") ||
        methods[0].ml_flags != METH_FASTCALL || methods[1].ml_flags != METH_FASTCALL ||
        methods[2].ml_flags != METH_FASTCALL || !methods[0].ml_meth ||
        !methods[1].ml_meth || !methods[2].ml_meth) {
        PyErr_SetString(PyExc_AssertionError, "struct methods ABI"); return NULL;
    }
    const char *names[3] = {"pack", "unpack", "unpack_from"};
    for (size_t index = 0; index < 3; index++) {
        PyObject *method = PyObject_GetAttrString(target, names[index]);
        if (!method) return NULL;
        int valid = PyCFunction_CheckExact(method) && PyCFunction_GetSelf(method) == target &&
            PyCFunction_GetFlags(method) == METH_FASTCALL &&
            PyCFunction_GetFunction(method) == methods[index].ml_meth;
        Py_DECREF(method);
        if (!valid) { PyErr_SetString(PyExc_AssertionError, "live struct native signature differs from table"); return NULL; }
    }
    if (methods[3].ml_meth || methods[3].ml_flags || methods[3].ml_doc) {
        PyErr_SetString(PyExc_AssertionError, "struct method sentinel ABI"); return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"drive", drive, METH_VARARGS, NULL},
    {"counts", counts, METH_NOARGS, NULL},
    {"module_contract", module_contract, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef definition = {PyModuleDef_HEAD_INIT, "_struct_allocation_test", NULL, -1, methods};
PyMODINIT_FUNC PyInit__struct_allocation_test(void) { return PyModule_Create(&definition); }
