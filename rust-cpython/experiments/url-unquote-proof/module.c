/* CPython owns objects and text decoding around the Rust percent-byte scans. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

extern Py_ssize_t quote_ascii(const unsigned char *, size_t,
                             const unsigned char *, size_t,
                             unsigned char *, size_t);
extern Py_ssize_t unquote_ascii(const unsigned char *, size_t,
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

static PyObject *unquote_ascii_text(PyObject *self, PyObject *arg)
{
    (void)self;
    if (!PyUnicode_CheckExact(arg)) {
        PyErr_SetString(PyExc_TypeError, "unquote_ascii requires exact str input");
        return NULL;
    }
    if (!PyUnicode_IS_ASCII(arg)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    Py_ssize_t len = PyUnicode_GET_LENGTH(arg);
    PyObject *buffer = PyBytes_FromStringAndSize(NULL, len);
    if (buffer == NULL) return NULL;
    Py_ssize_t written = unquote_ascii(PyUnicode_1BYTE_DATA(arg), (size_t)len,
                                       (unsigned char *)PyBytes_AS_STRING(buffer), (size_t)len);
    if (written < 0 || written > len) {
        Py_DECREF(buffer);
        PyErr_SetString(PyExc_RuntimeError, "Rust unquote length contract failed");
        return NULL;
    }
    PyObject *result = PyUnicode_DecodeUTF8(PyBytes_AS_STRING(buffer), written, "replace");
    Py_DECREF(buffer);
    return result;
}

static PyMethodDef methods[] = {
    {"quote_bytes", (PyCFunction)(void (*)(void))quote_bytes, METH_FASTCALL,
     "Percent-quote exact bytes using a normalized exact-bytes safe set."},
    {"unquote_ascii", unquote_ascii_text, METH_O,
     "Percent-decode exact ASCII str with UTF-8 replacement semantics."},
    {NULL, NULL, 0, NULL}
};

static int module_exec(PyObject *module)
{
    (void)module;
    return 0;
}

static PyModuleDef_Slot slots[] = {
    {Py_mod_exec, module_exec},
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
    {0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_rust_url_quote",
    .m_size = 0,
    .m_methods = methods,
    .m_slots = slots,
};

PyMODINIT_FUNC PyInit__rust_url_quote(void)
{
    return PyModuleDef_Init(&module);
}
