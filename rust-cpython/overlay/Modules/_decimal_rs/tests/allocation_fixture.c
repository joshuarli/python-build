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
    if (!PyModule_Check(self) || strcmp(PyModule_GetName(self), "_decimal_rs") != 0) {
        PyErr_SetString(PyExc_TypeError, "driver requires the decimal helper");
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
    if (!definition || strcmp(definition->m_name, "_decimal_rs") != 0 ||
        definition->m_size != 0 || definition->m_traverse || definition->m_clear || definition->m_free ||
        !definition->m_methods || !definition->m_slots) {
        PyErr_SetString(PyExc_AssertionError, "decimal module state ABI"); return NULL;
    }
    PyMethodDef *methods = definition->m_methods;
    if (!methods[0].ml_name || !methods[1].ml_name || methods[2].ml_name ||
        strcmp(methods[0].ml_name, "multiply_exact_integers") ||
        strcmp(methods[1].ml_name, "add_exact_integers") ||
        methods[0].ml_flags != METH_FASTCALL || methods[1].ml_flags != METH_FASTCALL ||
        definition->m_slots[0].slot != Py_mod_multiple_interpreters ||
        definition->m_slots[0].value != Py_MOD_PER_INTERPRETER_GIL_SUPPORTED ||
        definition->m_slots[1].slot != 0) {
        PyErr_SetString(PyExc_AssertionError, "decimal methods and interpreter slot ABI"); return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"drive", drive, METH_VARARGS, NULL},
    {"counts", counts, METH_NOARGS, NULL},
    {"module_contract", module_contract, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef definition = {PyModuleDef_HEAD_INIT, "_decimal_allocation_test", NULL, -1, methods};
PyMODINIT_FUNC PyInit__decimal_allocation_test(void) { return PyModule_Create(&definition); }
