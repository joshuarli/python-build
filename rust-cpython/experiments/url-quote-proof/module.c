/* CPython-owned object boundary for the exact-bytes Rust quotation kernel. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

extern Py_ssize_t quote_ascii(const unsigned char *, size_t,
                             const unsigned char *, size_t,
                             unsigned char *, size_t);

static PyObject *quote_bytes(PyObject *self, PyObject *const *args, Py_ssize_t nargs)
{
    (void)self;
    if (nargs != 2 || !PyBytes_CheckExact(args[0]) || !PyBytes_CheckExact(args[1])) {
        PyErr_SetString(PyExc_TypeError, "quote_bytes requires exact bytes input and safe");
        return NULL;
    }
    Py_ssize_t len = PyBytes_GET_SIZE(args[0]);
    Py_ssize_t safe_len = PyBytes_GET_SIZE(args[1]);
    if (len >= 200000) {
        PyErr_SetString(PyExc_ValueError, "quote_bytes input exceeds guarded limit");
        return NULL;
    }
    PyObject *buffer = PyBytes_FromStringAndSize(NULL, len * 3);
    if (buffer == NULL) return NULL;
    Py_ssize_t written = quote_ascii((const unsigned char *)PyBytes_AS_STRING(args[0]),
                                    (size_t)len,
                                    (const unsigned char *)PyBytes_AS_STRING(args[1]),
                                    (size_t)safe_len,
                                    (unsigned char *)PyBytes_AS_STRING(buffer),
                                    (size_t)(len * 3));
    if (written < 0) {
        Py_DECREF(buffer);
        PyErr_SetString(PyExc_RuntimeError, "Rust quotation buffer contract failed");
        return NULL;
    }
    PyObject *result = PyUnicode_DecodeASCII(PyBytes_AS_STRING(buffer), written, NULL);
    Py_DECREF(buffer);
    return result;
}

static PyMethodDef methods[] = {
    {"quote_bytes", (PyCFunction)(void (*)(void))quote_bytes, METH_FASTCALL,
     "Percent-quote exact bytes using a normalized exact-bytes safe set."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_rust_url_quote", NULL, -1, methods
};

PyMODINIT_FUNC PyInit__rust_url_quote(void)
{
    return PyModule_Create(&module);
}
