#include "Python.h"
#include "cpython/longintrepr.h"
#include <stddef.h>
#include <string.h>

#if SIZEOF_VOID_P != 8 || defined(Py_GIL_DISABLED) || defined(Py_DEBUG) || PY_BIG_ENDIAN || PYLONG_BITS_IN_DIGIT != 30
#error "The observer requires the pinned 64-bit little-endian GIL release ABI"
#endif
_Static_assert(sizeof(long) == 8, "C long ABI");
_Static_assert(sizeof(long long) == 8, "C long long ABI");
_Static_assert(sizeof(Py_ssize_t) == 8, "ssize ABI");
_Static_assert(sizeof(digit) == 4, "compact digit ABI");
_Static_assert(_Py_STATIC_IMMORTAL_INITIAL_REFCNT == ((3ULL << 30) | (5ULL << 48)), "static head ABI");
_Static_assert(Py_mod_exec == 85, "exec slot ABI");
_Static_assert(Py_mod_multiple_interpreters == 86, "interpreter slot ABI");
_Static_assert((size_t)Py_MOD_PER_INTERPRETER_GIL_SUPPORTED == 2, "interpreter value ABI");
_Static_assert(sizeof(PyObject) == 16, "_object size");
_Static_assert(_Alignof(PyObject) == 8, "_object alignment");
_Static_assert(offsetof(PyObject, ob_refcnt_full) == 0, "_object.ob_refcnt_full offset");
_Static_assert(offsetof(PyObject, ob_type) == 8, "_object.ob_type offset");
_Static_assert(sizeof(PyObject) == 16, "PyObject size");
_Static_assert(_Alignof(PyObject) == 8, "PyObject alignment");
_Static_assert(sizeof(PyVarObject) == 24, "PyVarObject size");
_Static_assert(_Alignof(PyVarObject) == 8, "PyVarObject alignment");
_Static_assert(offsetof(PyVarObject, ob_base) == 0, "PyVarObject.ob_base offset");
_Static_assert(offsetof(PyVarObject, ob_size) == 16, "PyVarObject.ob_size offset");
_Static_assert(sizeof(PyFloatObject) == 24, "PyFloatObject size");
_Static_assert(_Alignof(PyFloatObject) == 8, "PyFloatObject alignment");
_Static_assert(offsetof(PyFloatObject, ob_base) == 0, "PyFloatObject.ob_base offset");
_Static_assert(offsetof(PyFloatObject, ob_fval) == 16, "PyFloatObject.ob_fval offset");
_Static_assert(sizeof(PyListObject) == 40, "PyListObject size");
_Static_assert(_Alignof(PyListObject) == 8, "PyListObject alignment");
_Static_assert(offsetof(PyListObject, ob_base) == 0, "PyListObject.ob_base offset");
_Static_assert(offsetof(PyListObject, ob_item) == 24, "PyListObject.ob_item offset");
_Static_assert(offsetof(PyListObject, allocated) == 32, "PyListObject.allocated offset");
_Static_assert(sizeof(PyTupleObject) == 40, "PyTupleObject size");
_Static_assert(_Alignof(PyTupleObject) == 8, "PyTupleObject alignment");
_Static_assert(offsetof(PyTupleObject, ob_base) == 0, "PyTupleObject.ob_base offset");
_Static_assert(offsetof(PyTupleObject, ob_hash) == 24, "PyTupleObject.ob_hash offset");
_Static_assert(offsetof(PyTupleObject, ob_item) == 32, "PyTupleObject.ob_item offset");
_Static_assert(sizeof(_PyLongValue) == 16, "LongValue size");
_Static_assert(_Alignof(_PyLongValue) == 8, "LongValue alignment");
_Static_assert(offsetof(_PyLongValue, lv_tag) == 0, "LongValue.lv_tag offset");
_Static_assert(offsetof(_PyLongValue, ob_digit) == 8, "LongValue.ob_digit offset");
_Static_assert(sizeof(PyLongObject) == 32, "_longobject size");
_Static_assert(_Alignof(PyLongObject) == 8, "_longobject alignment");
_Static_assert(offsetof(PyLongObject, ob_base) == 0, "_longobject.ob_base offset");
_Static_assert(offsetof(PyLongObject, long_value) == 16, "_longobject.long_value offset");
_Static_assert(sizeof(PyLongLayout) == 4, "PyLongLayout size");
_Static_assert(_Alignof(PyLongLayout) == 1, "PyLongLayout alignment");
_Static_assert(offsetof(PyLongLayout, bits_per_digit) == 0, "PyLongLayout.bits_per_digit offset");
_Static_assert(offsetof(PyLongLayout, digit_size) == 1, "PyLongLayout.digit_size offset");
_Static_assert(offsetof(PyLongLayout, digits_order) == 2, "PyLongLayout.digits_order offset");
_Static_assert(offsetof(PyLongLayout, digit_endianness) == 3, "PyLongLayout.digit_endianness offset");
_Static_assert(sizeof(PyLongExport) == 40, "PyLongExport size");
_Static_assert(_Alignof(PyLongExport) == 8, "PyLongExport alignment");
_Static_assert(offsetof(PyLongExport, value) == 0, "PyLongExport.value offset");
_Static_assert(offsetof(PyLongExport, negative) == 8, "PyLongExport.negative offset");
_Static_assert(offsetof(PyLongExport, ndigits) == 16, "PyLongExport.ndigits offset");
_Static_assert(offsetof(PyLongExport, digits) == 24, "PyLongExport.digits offset");
_Static_assert(offsetof(PyLongExport, _reserved) == 32, "PyLongExport._reserved offset");
_Static_assert(sizeof(PyModuleDef_Base) == 40, "PyModuleDef_Base size");
_Static_assert(_Alignof(PyModuleDef_Base) == 8, "PyModuleDef_Base alignment");
_Static_assert(offsetof(PyModuleDef_Base, ob_base) == 0, "PyModuleDef_Base.ob_base offset");
_Static_assert(offsetof(PyModuleDef_Base, m_init) == 16, "PyModuleDef_Base.m_init offset");
_Static_assert(offsetof(PyModuleDef_Base, m_index) == 24, "PyModuleDef_Base.m_index offset");
_Static_assert(offsetof(PyModuleDef_Base, m_copy) == 32, "PyModuleDef_Base.m_copy offset");
_Static_assert(sizeof(PyModuleDef_Slot) == 16, "PyModuleDef_Slot size");
_Static_assert(_Alignof(PyModuleDef_Slot) == 8, "PyModuleDef_Slot alignment");
_Static_assert(offsetof(PyModuleDef_Slot, slot) == 0, "PyModuleDef_Slot.slot offset");
_Static_assert(offsetof(PyModuleDef_Slot, value) == 8, "PyModuleDef_Slot.value offset");
_Static_assert(sizeof(PyModuleDef) == 104, "PyModuleDef size");
_Static_assert(_Alignof(PyModuleDef) == 8, "PyModuleDef alignment");
_Static_assert(offsetof(PyModuleDef, m_base) == 0, "PyModuleDef.m_base offset");
_Static_assert(offsetof(PyModuleDef, m_name) == 40, "PyModuleDef.m_name offset");
_Static_assert(offsetof(PyModuleDef, m_doc) == 48, "PyModuleDef.m_doc offset");
_Static_assert(offsetof(PyModuleDef, m_size) == 56, "PyModuleDef.m_size offset");
_Static_assert(offsetof(PyModuleDef, m_methods) == 64, "PyModuleDef.m_methods offset");
_Static_assert(offsetof(PyModuleDef, m_slots) == 72, "PyModuleDef.m_slots offset");
_Static_assert(offsetof(PyModuleDef, m_traverse) == 80, "PyModuleDef.m_traverse offset");
_Static_assert(offsetof(PyModuleDef, m_clear) == 88, "PyModuleDef.m_clear offset");
_Static_assert(offsetof(PyModuleDef, m_free) == 96, "PyModuleDef.m_free offset");

#define SIGNATURE(name, result, ...) _Static_assert(_Generic(&(name), result (*)(__VA_ARGS__): 1, default: 0), #name " signature")
SIGNATURE(PyBool_FromLong, PyObject *, long);
SIGNATURE(PyBytes_FromStringAndSize, PyObject *, const char *, Py_ssize_t);
SIGNATURE(PyBytes_AsString, char *, PyObject *);
SIGNATURE(PyBytes_Size, Py_ssize_t, PyObject *);
SIGNATURE(_PyBytes_Resize, int, PyObject * *, Py_ssize_t);
SIGNATURE(PyCapsule_New, PyObject *, void *, const char *, PyCapsule_Destructor);
SIGNATURE(PyComplex_FromDoubles, PyObject *, double, double);
SIGNATURE(PyComplex_ImagAsDouble, double, PyObject *);
SIGNATURE(PyComplex_RealAsDouble, double, PyObject *);
SIGNATURE(Py_DecRef, void, PyObject *);
SIGNATURE(Py_IncRef, void, PyObject *);
SIGNATURE(PyDict_New, PyObject *, void);
SIGNATURE(PyDict_Next, int, PyObject *, Py_ssize_t *, PyObject * *, PyObject * *);
SIGNATURE(PyDict_SetItem, int, PyObject *, PyObject *, PyObject *);
SIGNATURE(PyErr_Clear, void, void);
SIGNATURE(PyErr_Occurred, PyObject *, void);
SIGNATURE(PyFloat_FromDouble, PyObject *, double);
SIGNATURE(PyFrozenSet_New, PyObject *, PyObject *);
SIGNATURE(PyIter_Next, PyObject *, PyObject *);
SIGNATURE(PyList_Append, int, PyObject *, PyObject *);
SIGNATURE(PyList_GetItem, PyObject *, PyObject *, Py_ssize_t);
SIGNATURE(PyList_New, PyObject *, Py_ssize_t);
SIGNATURE(PyList_SetItem, int, PyObject *, Py_ssize_t, PyObject *);
SIGNATURE(PyList_Size, Py_ssize_t, PyObject *);
SIGNATURE(PyList_Sort, int, PyObject *);
SIGNATURE(PyLong_AsLongLongAndOverflow, long long, PyObject *, int *);
SIGNATURE(PyLong_Export, int, PyObject *, PyLongExport *);
SIGNATURE(PyLong_FreeExport, void, PyLongExport *);
SIGNATURE(PyLong_FromLongLong, PyObject *, long long);
SIGNATURE(PyLong_GetNativeLayout, const PyLongLayout *, void);
SIGNATURE(PyLongWriter_Create, PyLongWriter *, int, Py_ssize_t, void * *);
SIGNATURE(PyLongWriter_Discard, void, PyLongWriter *);
SIGNATURE(PyLongWriter_Finish, PyObject *, PyLongWriter *);
SIGNATURE(PyMem_Calloc, void *, size_t, size_t);
SIGNATURE(PyMem_Free, void, void *);
SIGNATURE(PyMem_Realloc, void *, void *, size_t);
SIGNATURE(PyModule_Add, int, PyObject *, const char *, PyObject *);
SIGNATURE(PyModuleDef_Init, PyObject *, PyModuleDef *);
SIGNATURE(PyObject_GetIter, PyObject *, PyObject *);
SIGNATURE(PyObject_IsTrue, int, PyObject *);
SIGNATURE(PySet_Add, int, PyObject *, PyObject *);
SIGNATURE(PySet_New, PyObject *, PyObject *);
SIGNATURE(PyTuple_GetItem, PyObject *, PyObject *, Py_ssize_t);
SIGNATURE(PyTuple_New, PyObject *, Py_ssize_t);
SIGNATURE(PyTuple_SetItem, int, PyObject *, Py_ssize_t, PyObject *);
SIGNATURE(PyUnicode_AsEncodedString, PyObject *, PyObject *, const char *, const char *);
SIGNATURE(PyUnicode_DecodeUTF8, PyObject *, const char *, Py_ssize_t, const char *);
SIGNATURE(PyUnicode_InternInPlace, void, PyObject * *);


/* Imported singleton/type declarations are native data symbols, not pointer variables. */
_Static_assert(_Generic(&PyBool_Type, PyTypeObject *: 1, default: 0), "PyBool_Type data symbol type");
_Static_assert(_Generic(&PyBytes_Type, PyTypeObject *: 1, default: 0), "PyBytes_Type data symbol type");
_Static_assert(_Generic(&PyComplex_Type, PyTypeObject *: 1, default: 0), "PyComplex_Type data symbol type");
_Static_assert(_Generic(&PyCode_Type, PyTypeObject *: 1, default: 0), "PyCode_Type data symbol type");
_Static_assert(_Generic(&PyDict_Type, PyTypeObject *: 1, default: 0), "PyDict_Type data symbol type");
_Static_assert(_Generic(&PyFloat_Type, PyTypeObject *: 1, default: 0), "PyFloat_Type data symbol type");
_Static_assert(_Generic(&PyFrozenSet_Type, PyTypeObject *: 1, default: 0), "PyFrozenSet_Type data symbol type");
_Static_assert(_Generic(&PyList_Type, PyTypeObject *: 1, default: 0), "PyList_Type data symbol type");
_Static_assert(_Generic(&PyLong_Type, PyTypeObject *: 1, default: 0), "PyLong_Type data symbol type");
_Static_assert(_Generic(&PySet_Type, PyTypeObject *: 1, default: 0), "PySet_Type data symbol type");
_Static_assert(_Generic(&PyTuple_Type, PyTypeObject *: 1, default: 0), "PyTuple_Type data symbol type");
_Static_assert(_Generic(&PyUnicode_Type, PyTypeObject *: 1, default: 0), "PyUnicode_Type data symbol type");
_Static_assert(_Generic(&_Py_NoneStruct, PyObject *: 1, default: 0), "_Py_NoneStruct data symbol type");

typedef struct {
    PyObject *(*dumps)(PyObject *, int);
    PyObject *(*loads)(const char *, Py_ssize_t, int);
} MarshalApi;
_Static_assert(sizeof(MarshalApi) == 16, "capsule API size");
_Static_assert(offsetof(MarshalApi, loads) == 8, "capsule loads offset");

static MarshalApi *get_api(PyObject *helper)
{
    if (!PyModule_Check(helper) || strcmp(PyModule_GetName(helper), "_marshal_rs") != 0) {
        PyErr_SetString(PyExc_TypeError, "expected the marshal helper module");
        return NULL;
    }
    PyObject *capsule = PyObject_GetAttrString(helper, "_api");
    if (!capsule) return NULL;
    MarshalApi *api = PyCapsule_GetPointer(capsule, "_marshal_rs._api");
    Py_DECREF(capsule);
    if (api && (!api->dumps || !api->loads)) {
        PyErr_SetString(PyExc_AssertionError, "marshal capsule has a null entry point");
        return NULL;
    }
    return api;
}

static PyObject *module_contract(PyObject *self, PyObject *helper)
{
    if (!get_api(helper)) return NULL;
    PyModuleDef *d = PyModule_GetDef(helper);
    if (!d || d->m_size != 0 || d->m_methods || !d->m_slots || d->m_traverse ||
        d->m_clear || d->m_free || strcmp(d->m_name, "_marshal_rs") != 0 ||
        d->m_slots[0].slot != Py_mod_exec || !d->m_slots[0].value ||
        d->m_slots[1].slot != Py_mod_multiple_interpreters ||
        d->m_slots[1].value != Py_MOD_PER_INTERPRETER_GIL_SUPPORTED ||
        d->m_slots[2].slot != 0 || d->m_slots[2].value != NULL ||
        d->m_base.m_init || d->m_base.m_copy ||
        d->m_base.ob_base.ob_flags != 5 || !Py_IS_TYPE((PyObject *)d, &PyModuleDef_Type)) {
        PyErr_SetString(PyExc_AssertionError, "marshal native module definition changed");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *handled(PyObject *value)
{
    if (!value) {
        if (PyErr_Occurred()) {
            PyErr_SetString(PyExc_AssertionError, "marshal rejection left an exception");
            return NULL;
        }
        return PyTuple_Pack(2, Py_False, Py_None);
    }
    PyObject *result = PyTuple_Pack(2, Py_True, value);
    Py_DECREF(value);
    return result;
}

static PyObject *dumps(PyObject *self, PyObject *args)
{
    PyObject *helper, *value;
    int allow;
    if (!PyArg_ParseTuple(args, "OOi", &helper, &value, &allow)) return NULL;
    MarshalApi *api = get_api(helper);
    if (!api) return NULL;
    return handled(api->dumps(value, allow));
}

static PyObject *loads(PyObject *self, PyObject *args)
{
    PyObject *helper, *data;
    int allow;
    if (!PyArg_ParseTuple(args, "OOi", &helper, &data, &allow)) return NULL;
    if (!PyBytes_CheckExact(data)) {
        PyErr_SetString(PyExc_TypeError, "expected bytes");
        return NULL;
    }
    MarshalApi *api = get_api(helper);
    if (!api) return NULL;
    return handled(api->loads(PyBytes_AS_STRING(data), PyBytes_GET_SIZE(data), allow));
}

/* Compare the direct fields the Rust codec reads with independent public APIs. */
static PyObject *live_fields(PyObject *self, PyObject *value)
{
    if (value->ob_type != Py_TYPE(value) || value->ob_refcnt != Py_REFCNT(value)) goto mismatch;
    if (PyFloat_CheckExact(value)) {
        if (((PyFloatObject *)value)->ob_fval != PyFloat_AsDouble(value)) goto mismatch;
    }
    else if (PyList_CheckExact(value)) {
        PyListObject *list = (PyListObject *)value;
        if (list->ob_base.ob_size != PyList_Size(value)) goto mismatch;
        for (Py_ssize_t i = 0; i < list->ob_base.ob_size; ++i)
            if (list->ob_item[i] != PyList_GetItem(value, i)) goto mismatch;
    }
    else if (PyTuple_CheckExact(value)) {
        PyTupleObject *tuple = (PyTupleObject *)value;
        if (tuple->ob_base.ob_size != PyTuple_Size(value)) goto mismatch;
        for (Py_ssize_t i = 0; i < tuple->ob_base.ob_size; ++i)
            if (tuple->ob_item[i] != PyTuple_GetItem(value, i)) goto mismatch;
    }
    else if (PyLong_CheckExact(value)) {
        PyLongObject *integer = (PyLongObject *)value;
        if (integer->long_value.lv_tag < 16) {
            long long direct = (1 - (long long)(integer->long_value.lv_tag & 3)) * integer->long_value.ob_digit[0];
            if (direct != PyLong_AsLongLong(value)) goto mismatch;
        }
        const PyLongLayout *layout = PyLong_GetNativeLayout();
        if (layout->bits_per_digit != 30 || layout->digit_size != 4 ||
            layout->digits_order != -1 || layout->digit_endianness != -1) goto mismatch;
        PyLongExport exported;
        if (PyLong_Export(value, &exported)) return NULL;
        PyObject *rebuilt;
        if (exported.digits) {
            void *digits;
            PyLongWriter *writer = PyLongWriter_Create(exported.negative, exported.ndigits, &digits);
            if (!writer) { PyLong_FreeExport(&exported); return NULL; }
            memcpy(digits, exported.digits, (size_t)exported.ndigits * layout->digit_size);
            rebuilt = PyLongWriter_Finish(writer);
            PyLong_FreeExport(&exported);
        }
        else rebuilt = PyLong_FromLongLong(exported.value);
        if (!rebuilt) return NULL;
        int equal = PyObject_RichCompareBool(value, rebuilt, Py_EQ);
        Py_DECREF(rebuilt);
        if (equal < 0) return NULL;
        if (!equal) goto mismatch;
    }
    Py_RETURN_NONE;
mismatch:
    PyErr_SetString(PyExc_AssertionError, "marshal direct field differs from CPython API");
    return NULL;
}

/* Fail MEM-domain requests only during the synchronous capsule call. The
   observer creates arguments before arming and restores hooks before Python
   result construction; no allocator state survives this function. */
static PyMemAllocatorEx saved_mem;
static size_t failed_requests;
static int fault_active;
static void *reject_malloc(void *ctx, size_t size) { ++failed_requests; return NULL; }
static void *reject_calloc(void *ctx, size_t count, size_t size) { ++failed_requests; return NULL; }
static void *reject_realloc(void *ctx, void *pointer, size_t size) { ++failed_requests; return NULL; }
static void delegate_free(void *ctx, void *pointer) { saved_mem.free(saved_mem.ctx, pointer); }

static PyObject *memory_rejection(PyObject *self, PyObject *args)
{
    PyObject *helper, *value;
    int reading;
    if (!PyArg_ParseTuple(args, "OOi", &helper, &value, &reading)) return NULL;
    if (reading && !PyBytes_CheckExact(value)) {
        PyErr_SetString(PyExc_TypeError, "reader fault requires bytes"); return NULL;
    }
    MarshalApi *api = get_api(helper);
    if (!api) return NULL;
    if (fault_active) {
        PyErr_SetString(PyExc_RuntimeError, "allocator observer already active"); return NULL;
    }
    PyMemAllocatorEx replacement = {NULL, reject_malloc, reject_calloc, reject_realloc, delegate_free};
    PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &saved_mem);
    failed_requests = 0;
    fault_active = 1;
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &replacement);
    PyObject *result = reading
        ? api->loads(PyBytes_AS_STRING(value), PyBytes_GET_SIZE(value), 1)
        : api->dumps(value, 1);
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &saved_mem);
    fault_active = 0;
    if (result || PyErr_Occurred() || failed_requests == 0) {
        Py_XDECREF(result);
        PyErr_SetString(PyExc_AssertionError, "marshal MEM rejection contract changed");
        return NULL;
    }
    return PyLong_FromSize_t(failed_requests);
}

static PyMethodDef methods[] = {
    {"module_contract", module_contract, METH_O, NULL},
    {"dumps", dumps, METH_VARARGS, NULL},
    {"loads", loads, METH_VARARGS, NULL},
    {"live_fields", live_fields, METH_O, NULL},
    {"memory_rejection", memory_rejection, METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef definition = {
    PyModuleDef_HEAD_INIT, "_marshal_abi_test", NULL, 0, methods
};
PyMODINIT_FUNC PyInit__marshal_abi_test(void) { return PyModule_Create(&definition); }
