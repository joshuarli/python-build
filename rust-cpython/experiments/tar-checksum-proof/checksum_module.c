#define PY_SSIZE_T_CLEAN
#include <Python.h>

extern void tar_checksum_scan(const unsigned char *buf, int *unsigned_sum, int *signed_sum);

static PyObject *scan(PyObject *self, PyObject *arg) {
    int unsigned_sum;
    int signed_sum;
    (void)self;
    if (!PyBytes_CheckExact(arg) || PyBytes_GET_SIZE(arg) != 512) {
        PyErr_SetString(PyExc_TypeError, "scan requires exact bytes of length 512");
        return NULL;
    }
    tar_checksum_scan((const unsigned char *)PyBytes_AS_STRING(arg), &unsigned_sum, &signed_sum);
    return Py_BuildValue("(ii)", unsigned_sum, signed_sum);
}

static PyMethodDef methods[] = {
    {"scan", scan, METH_O, "Return unsigned and signed TAR header checksums."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_tar_checksum_proof",
    NULL,
    -1,
    methods
};

PyMODINIT_FUNC PyInit__tar_checksum_proof(void) {
    return PyModule_Create(&module);
}
