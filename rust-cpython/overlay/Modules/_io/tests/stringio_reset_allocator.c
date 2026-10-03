#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <string.h>

/* This probe must run alone in a fresh GIL-enabled process, with no other
 * threads or interpreters: the MEM allocator domain is process-global. */
typedef struct {
    PyMemAllocatorEx original;
    size_t reject_min;
    size_t maximum;
    size_t calls;
    size_t rejected;
} Probe;

static size_t last_calls, last_maximum, last_rejected;

static void *probe_malloc(void *ctx, size_t n)
{
    Probe *p = ctx;
    return p->original.malloc(p->original.ctx, n);
}

static void *probe_calloc(void *ctx, size_t n, size_t size)
{
    Probe *p = ctx;
    return p->original.calloc(p->original.ctx, n, size);
}

static void *probe_realloc(void *ctx, void *ptr, size_t n)
{
    Probe *p = ctx;
    p->calls++;
    if (n > p->maximum) p->maximum = n;
    if (n >= p->reject_min) {
        p->rejected++;
        return NULL;
    }
    return p->original.realloc(p->original.ctx, ptr, n);
}

static void probe_free(void *ctx, void *ptr)
{
    Probe *p = ctx;
    p->original.free(p->original.ctx, ptr);
}

static PyObject *probe_reset(PyObject *module, PyObject *args)
{
    PyObject *method;
    Py_ssize_t minimum;
    if (!PyArg_ParseTuple(args, "On", &method, &minimum)) return NULL;
    if (!PyCFunction_Check(method) || minimum <= 0) {
        PyErr_SetString(PyExc_TypeError, "a native bound truncate method and positive threshold are required");
        return NULL;
    }
    PyObject *owner = PyCFunction_GetSelf(method);
    /* Python subclasses do not own the defining module of their base type.
     * Resolve the canonical exported type through that association, then
     * compare the actual native bound dispatch before installing hooks. */
    PyObject *io_module = owner == NULL ? NULL : PyType_GetModule(Py_TYPE(owner));
    if (io_module == NULL) {
        PyErr_Clear();
        PyErr_SetString(PyExc_TypeError, "only an exact StringIO native truncate method is supported");
        return NULL;
    }
    PyObject *published = PyImport_ImportModule("_io");
    if (published == NULL) return NULL;
    PyModuleDef *definition = PyModule_Check(io_module) ? PyModule_GetDef(io_module) : NULL;
    int canonical_module = published == io_module && definition != NULL
                           && definition->m_name != NULL
                           && strcmp(definition->m_name, "_io") == 0;
    Py_DECREF(published);
    if (!canonical_module) {
        PyErr_SetString(PyExc_TypeError, "the original published _io module is required");
        return NULL;
    }
    PyObject *canonical = PyObject_GetAttrString(io_module, "StringIO");
    if (canonical == NULL) return NULL;
    int exact_type = (PyObject *)Py_TYPE(owner) == canonical
                     && (PyType_GetFlags(Py_TYPE(owner)) & Py_TPFLAGS_IMMUTABLETYPE);
    if (!exact_type) {
        Py_DECREF(canonical);
        PyErr_SetString(PyExc_TypeError, "only an exact StringIO native truncate method is supported");
        return NULL;
    }
    /* The instance dictionary may shadow truncate with another bound method.
     * Bind the immutable type's descriptor, bypassing that dictionary. */
    PyObject *descriptor = PyObject_GetAttrString(canonical, "truncate");
    if (descriptor == NULL) {
        Py_DECREF(canonical);
        return NULL;
    }
    PyObject *truncate = PyObject_CallMethod(descriptor, "__get__", "OO", owner, canonical);
    Py_DECREF(descriptor);
    Py_DECREF(canonical);
    if (truncate == NULL) return NULL;
    int valid = PyCFunction_Check(truncate)
                && PyCFunction_GetSelf(truncate) == owner
                && PyCFunction_GetFunction(truncate) == PyCFunction_GetFunction(method)
                && PyCFunction_GetFlags(truncate) == PyCFunction_GetFlags(method);
    Py_DECREF(truncate);
    if (!valid) {
        PyErr_SetString(PyExc_TypeError, "only an exact StringIO native truncate method is supported");
        return NULL;
    }
    PyObject *zero = PyLong_FromLong(0);
    if (zero == NULL) return NULL;
    Probe p = {0};
    p.reject_min = (size_t)minimum;
    PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &p.original);
    PyMemAllocatorEx wrapped = {&p, probe_malloc, probe_calloc, probe_realloc, probe_free};
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &wrapped);
    PyObject *result = PyObject_CallOneArg(method, zero);
    PyObject *exception = result == NULL ? PyErr_GetRaisedException() : NULL;
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &p.original);
    last_calls = p.calls;
    last_maximum = p.maximum;
    last_rejected = p.rejected;
    Py_DECREF(zero);
    if (result == NULL) {
        PyErr_SetRaisedException(exception);
        return NULL;
    }
    return Py_BuildValue("NKKK", result,
                         (unsigned long long)p.calls,
                         (unsigned long long)p.maximum,
                         (unsigned long long)p.rejected);
}

static PyObject *last_stats(PyObject *module, PyObject *unused)
{
    return Py_BuildValue("KKK", (unsigned long long)last_calls,
                         (unsigned long long)last_maximum,
                         (unsigned long long)last_rejected);
}

static PyMethodDef methods[] = {
    {"reset", probe_reset, METH_VARARGS, NULL},
    {"last_stats", last_stats, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_stringio_reset_allocator", NULL, -1, methods
};

PyMODINIT_FUNC PyInit__stringio_reset_allocator(void)
{
    return PyModule_Create(&module);
}
