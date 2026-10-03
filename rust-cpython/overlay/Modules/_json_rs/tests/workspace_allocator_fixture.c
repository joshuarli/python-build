/* Count call-local PyMem owners and inject one allocation failure on the calling
 * thread. Other interpreters delegate unchanged to the prior allocator. The
 * result is released before counting remaining owners and restoring hooks.
 * Inject only reallocations: these ASCII, small-integer documents exercise
 * workspace growth, while their Python containers use malloc/calloc. Run this
 * observer only in a fresh controlled process without concurrent interpreters. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

/* Compile the used signatures and layouts against the actual native headers.
 * Function-like Unicode macros remain unexpanded when their addresses are
 * taken, so these checks bind the exported functions used by the codec. */
#include <stddef.h>
#ifdef Py_GIL_DISABLED
#error "JSON private declarations require the GIL object layout"
#endif
_Static_assert(sizeof(void *) == 8 && sizeof(long long) == 8, "native scalar widths");
_Static_assert(sizeof(PyObject) == 16 && offsetof(PyObject, ob_type) == 8, "object prefix");
_Static_assert(sizeof(PyMethodDef) == 32 && offsetof(PyMethodDef, ml_meth) == 8 && offsetof(PyMethodDef, ml_flags) == 16, "method table");
_Static_assert(sizeof(PyModuleDef_Base) == 40, "module base");
_Static_assert(sizeof(PyModuleDef) == 104 && offsetof(PyModuleDef, m_size) == 56 && offsetof(PyModuleDef, m_methods) == 64 && offsetof(PyModuleDef, m_slots) == 72 && offsetof(PyModuleDef, m_traverse) == 80, "module definition");
_Static_assert(sizeof(PyModuleDef_Slot) == 16, "module slot");
_Static_assert(METH_FASTCALL == 0x0080, "fastcall flag");
_Static_assert(_Py_STATIC_IMMORTAL_INITIAL_REFCNT == ((3ULL << 30) | (5ULL << 48)), "immortal static module header");
_Static_assert(_Generic(&PyDict_New, PyObject * (*)(void): 1, default: 0), "PyDict_New signature");
_Static_assert(_Generic(&PyDict_Next, int (*)(PyObject *, Py_ssize_t *, PyObject * *, PyObject * *): 1, default: 0), "PyDict_Next signature");
_Static_assert(_Generic(&PyDict_SetItem, int (*)(PyObject *, PyObject *, PyObject *): 1, default: 0), "PyDict_SetItem signature");
_Static_assert(_Generic(&PyErr_Clear, void (*)(void): 1, default: 0), "PyErr_Clear signature");
_Static_assert(_Generic(&PyErr_NoMemory, PyObject * (*)(void): 1, default: 0), "PyErr_NoMemory signature");
_Static_assert(_Generic(&PyErr_Occurred, PyObject * (*)(void): 1, default: 0), "PyErr_Occurred signature");
_Static_assert(_Generic(&PyErr_SetString, void (*)(PyObject *, const char *): 1, default: 0), "PyErr_SetString signature");
_Static_assert(_Generic(&PyErr_GetRaisedException, PyObject * (*)(void): 1, default: 0), "PyErr_GetRaisedException signature");
_Static_assert(_Generic(&PyErr_SetRaisedException, void (*)(PyObject *): 1, default: 0), "PyErr_SetRaisedException signature");
_Static_assert(_Generic(&PyFloat_AsDouble, double (*)(PyObject *): 1, default: 0), "PyFloat_AsDouble signature");
_Static_assert(_Generic(&PyFloat_FromDouble, PyObject * (*)(double): 1, default: 0), "PyFloat_FromDouble signature");
_Static_assert(_Generic(&PyList_GetItem, PyObject * (*)(PyObject *, Py_ssize_t): 1, default: 0), "PyList_GetItem signature");
_Static_assert(_Generic(&PyList_New, PyObject * (*)(Py_ssize_t): 1, default: 0), "PyList_New signature");
_Static_assert(_Generic(&PyList_SetItem, int (*)(PyObject *, Py_ssize_t, PyObject *): 1, default: 0), "PyList_SetItem signature");
_Static_assert(_Generic(&PyList_Size, Py_ssize_t (*)(PyObject *): 1, default: 0), "PyList_Size signature");
_Static_assert(_Generic(&PyLong_AsLongLongAndOverflow, long long (*)(PyObject *, int *): 1, default: 0), "PyLong_AsLongLongAndOverflow signature");
_Static_assert(_Generic(&PyLong_FromLongLong, PyObject * (*)(long long): 1, default: 0), "PyLong_FromLongLong signature");
_Static_assert(_Generic(&PyLong_FromString, PyObject * (*)(const char *, char * *, int): 1, default: 0), "PyLong_FromString signature");
_Static_assert(_Generic(&PyMem_Free, void (*)(void *): 1, default: 0), "PyMem_Free signature");
_Static_assert(_Generic(&PyMem_Realloc, void * (*)(void *, size_t): 1, default: 0), "PyMem_Realloc signature");
_Static_assert(_Generic(&PyModuleDef_Init, PyObject * (*)(PyModuleDef *): 1, default: 0), "PyModuleDef_Init signature");
_Static_assert(_Generic(&PyOS_double_to_string, char * (*)(double, char, int, int, int *): 1, default: 0), "PyOS_double_to_string signature");
_Static_assert(_Generic(&PyObject_IsTrue, int (*)(PyObject *): 1, default: 0), "PyObject_IsTrue signature");
_Static_assert(_Generic(&PyObject_Str, PyObject * (*)(PyObject *): 1, default: 0), "PyObject_Str signature");
_Static_assert(_Generic(&PyTuple_GetItem, PyObject * (*)(PyObject *, Py_ssize_t): 1, default: 0), "PyTuple_GetItem signature");
_Static_assert(_Generic(&PyTuple_Size, Py_ssize_t (*)(PyObject *): 1, default: 0), "PyTuple_Size signature");
_Static_assert(_Generic(&PyUnicode_AsUTF8AndSize, const char * (*)(PyObject *, Py_ssize_t *): 1, default: 0), "PyUnicode_AsUTF8AndSize signature");
_Static_assert(_Generic(&PyUnicode_DATA, void * (*)(PyObject *): 1, default: 0), "PyUnicode_DATA signature");
_Static_assert(_Generic(&PyUnicode_KIND, int (*)(PyObject *): 1, default: 0), "PyUnicode_KIND signature");
_Static_assert(_Generic(&PyUnicode_FromStringAndSize, PyObject * (*)(const char *, Py_ssize_t): 1, default: 0), "PyUnicode_FromStringAndSize signature");
_Static_assert(_Generic(&PyUnicode_GetLength, Py_ssize_t (*)(PyObject *): 1, default: 0), "PyUnicode_GetLength signature");
_Static_assert(_Generic(&PyUnicode_New, PyObject * (*)(Py_ssize_t, Py_UCS4): 1, default: 0), "PyUnicode_New signature");
_Static_assert(_Generic(&Py_DecRef, void (*)(PyObject *): 1, default: 0), "Py_DecRef signature");
_Static_assert(_Generic(&Py_IncRef, void (*)(PyObject *): 1, default: 0), "Py_IncRef signature");

typedef struct {
    PyMemAllocatorEx previous;
    unsigned long owner;
    size_t calls, fail_at, live, overflow;
    uintptr_t addresses[4096];
    int failed;
} Scope;

static int owned(Scope *s) { return PyThread_get_thread_ident() == s->owner; }
static int fails(Scope *s) {
    if (!owned(s)) return 0;
    s->calls++;
    if (s->calls == s->fail_at) { s->failed = 1; return 1; }
    return 0;
}
static void remember(Scope *s, void *p) {
    if (!p || !owned(s)) return;
    for (size_t i = 0; i < 4096; i++) {
        if (!s->addresses[i]) { s->addresses[i] = (uintptr_t)p; s->live++; return; }
    }
    s->overflow = 1;
}
static void forget_address(Scope *s, uintptr_t address) {
    if (!address || !owned(s)) return;
    for (size_t i = 0; i < 4096; i++) {
        if (s->addresses[i] == address) { s->addresses[i] = 0; s->live--; return; }
    }
}
static void *allocate(void *ctx, size_t n) {
    Scope *s = ctx;
    void *p = s->previous.malloc(s->previous.ctx, n); remember(s, p); return p;
}
static void *zero_allocate(void *ctx, size_t n, size_t size) {
    Scope *s = ctx;
    void *p = s->previous.calloc(s->previous.ctx, n, size); remember(s, p); return p;
}
static void *resize(void *ctx, void *p, size_t n) {
    Scope *s = ctx;
    if (fails(s)) return NULL;
    uintptr_t address = (uintptr_t)p;
    void *q = s->previous.realloc(s->previous.ctx, p, n);
    if (q) { forget_address(s, address); remember(s, q); }
    return q;
}
static void release(void *ctx, void *p) {
    Scope *s = ctx; forget_address(s, (uintptr_t)p); s->previous.free(s->previous.ctx, p);
}
static PyObject *exercise(PyObject *self, PyObject *args) {
    PyObject *callable, *input;
    Py_ssize_t fail_at;
    if (!PyArg_ParseTuple(args, "OOn", &callable, &input, &fail_at)) return NULL;
    if (fail_at < 0) { PyErr_SetString(PyExc_ValueError, "negative failure index"); return NULL; }
    Scope scope = {0};
    scope.owner = PyThread_get_thread_ident(); scope.fail_at = (size_t)fail_at;
    PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &scope.previous);
    PyMemAllocatorEx hook = {&scope, allocate, zero_allocate, resize, release};
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &hook);
    PyObject *result = PyObject_CallOneArg(callable, input);
    int marker = result == Py_NotImplemented;
    PyObject *error = result ? NULL : PyErr_GetRaisedException();
    Py_XDECREF(result);
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &scope.previous);
    if (!error) error = Py_NewRef(Py_None);
    if (scope.overflow) { Py_DECREF(error); PyErr_SetString(PyExc_RuntimeError, "owner accounting capacity exceeded"); return NULL; }
    return Py_BuildValue("ninnN", (Py_ssize_t)scope.calls, marker,
                         (Py_ssize_t)scope.failed, (Py_ssize_t)scope.live, error);
}
/* Use the header's typed FASTCALL pointer on the live Rust method table.
 * References to methods, encoded input and result remain strong across calls. */
static PyObject *ffi_fast_roundtrip(PyObject *self, PyObject *args) {
    PyObject *module, *value;
    if (!PyArg_ParseTuple(args, "OO", &module, &value)) return NULL;
    PyModuleDef *def = PyModule_GetDef(module);
    if (!def) return NULL;
    if (def->m_size != 0 || def->m_slots || def->m_traverse || !def->m_clear || !def->m_free ||
        strcmp(def->m_name, "_json_rs") || strcmp(def->m_doc, "Rust JSON document codec") ||
        def->m_base.ob_base.ob_refcnt_full != _Py_STATIC_IMMORTAL_INITIAL_REFCNT ||
        !def->m_methods || strcmp(def->m_methods[0].ml_name, "dumps") ||
        strcmp(def->m_methods[1].ml_name, "loads") || def->m_methods[2].ml_name ||
        def->m_methods[0].ml_flags != METH_FASTCALL || def->m_methods[1].ml_flags != METH_FASTCALL) {
        PyErr_SetString(PyExc_AssertionError, "native module definition differs"); return NULL;
    }
    PyObject *dumps = PyObject_GetAttrString(module, "dumps");
    if (!dumps) return NULL;
    PyObject *loads = PyObject_GetAttrString(module, "loads");
    if (!loads) { Py_DECREF(dumps); return NULL; }
    PyObject *encoded = NULL, *decoded = NULL, *output = NULL;
    if (!PyCFunction_Check(dumps) || !PyCFunction_Check(loads) ||
        PyCFunction_GET_FLAGS(dumps) != METH_FASTCALL || PyCFunction_GET_FLAGS(loads) != METH_FASTCALL ||
        PyCFunction_GET_SELF(dumps) != module || PyCFunction_GET_SELF(loads) != module) {
        PyErr_SetString(PyExc_AssertionError, "native method ownership differs"); goto done;
    }
    PyObject *arguments[1] = {value};
    encoded = _PyCFunctionFast_CAST(PyCFunction_GET_FUNCTION(dumps))(module, arguments, 1);
    if (!encoded) goto done;
    if (!PyUnicode_CheckExact(encoded)) { PyErr_SetString(PyExc_AssertionError, "native encoding declined"); goto done; }
    arguments[0] = encoded;
    decoded = _PyCFunctionFast_CAST(PyCFunction_GET_FUNCTION(loads))(module, arguments, 1);
    if (!decoded) goto done;
    if (decoded == Py_NotImplemented) { PyErr_SetString(PyExc_AssertionError, "native decoding declined"); goto done; }
    output = PyTuple_Pack(2, encoded, decoded);
 done:
    Py_XDECREF(decoded); Py_XDECREF(encoded); Py_DECREF(loads); Py_DECREF(dumps);
    return output;
}
static PyMethodDef methods[] = {{"exercise", exercise, METH_VARARGS, NULL}, {"ffi_fast_roundtrip", ffi_fast_roundtrip, METH_VARARGS, NULL}, {NULL}};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_json_workspace_allocator_fixture", NULL, -1, methods};
PyMODINIT_FUNC PyInit__json_workspace_allocator_fixture(void) { return PyModule_Create(&module); }
