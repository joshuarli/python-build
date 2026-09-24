/* CPython-owned object boundary for an exact-size, ASCII-only Rust quote. */
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
    const unsigned char *input = (const unsigned char *)PyBytes_AS_STRING(args[0]);
    const unsigned char *safe = (const unsigned char *)PyBytes_AS_STRING(args[1]);
    Py_ssize_t output_len = quote_ascii(input, (size_t)len, safe, (size_t)safe_len, NULL, 0);
    if (output_len < 0 || output_len > len * 3) {
        PyErr_SetString(PyExc_RuntimeError, "Rust quotation length contract failed");
        return NULL;
    }
    PyObject *result = PyUnicode_New(output_len, 127);
    if (result == NULL) return NULL;
    Py_ssize_t written = quote_ascii(input, (size_t)len, safe, (size_t)safe_len,
                                    PyUnicode_1BYTE_DATA(result), (size_t)output_len);
    if (written != output_len) {
        Py_DECREF(result);
        PyErr_SetString(PyExc_RuntimeError, "Rust quotation fill contract failed");
        return NULL;
    }
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
