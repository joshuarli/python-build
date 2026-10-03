/* Check the layouts at the live module boundary against Python's headers. */
#include <Python.h>
#include <stddef.h>
#include <string.h>

_Static_assert(sizeof(PyObject) == 16 && _Alignof(PyObject) == 8, "object layout");
_Static_assert(sizeof(Py_buffer) == 80, "buffer size");
_Static_assert(offsetof(Py_buffer, readonly) == 32, "buffer readonly");
_Static_assert(offsetof(Py_buffer, format) == 40, "buffer format");
_Static_assert(offsetof(Py_buffer, internal) == 72, "buffer internal");
_Static_assert(sizeof(PyMethodDef) == 32, "method size");
_Static_assert(offsetof(PyMethodDef, ml_flags) == 16, "method flags");
_Static_assert(sizeof(PyModuleDef_Base) == 40, "module base size");
_Static_assert(sizeof(PyModuleDef) == 104, "module size");
_Static_assert(offsetof(PyModuleDef, m_methods) == 64, "module methods");
_Static_assert(offsetof(PyModuleDef, m_slots) == 72, "module slots");
_Static_assert(offsetof(PyModuleDef, m_free) == 96, "module free");

static PyObject *check(PyObject *self, PyObject *module)
{
    PyModuleDef *def = PyModule_GetDef(module);
    if (def == NULL) return NULL;
    const char *names[] = {"parse_ipv4", "parse_ipv6", "network_bounds"};
    if (strcmp(def->m_name, "_ipaddress_rs") != 0 || def->m_size != 0 ||
        def->m_slots != NULL || def->m_traverse != NULL ||
        def->m_clear == NULL || def->m_free == NULL || def->m_methods == NULL) {
        PyErr_SetString(PyExc_AssertionError, "address module definition changed");
        return NULL;
    }
    for (size_t i = 0; i < 3; i++) {
        PyMethodDef *method = &def->m_methods[i];
        if (method->ml_name == NULL || strcmp(method->ml_name, names[i]) != 0 ||
            method->ml_flags != METH_FASTCALL || method->ml_meth == NULL ||
            method->ml_doc == NULL) {
            PyErr_SetString(PyExc_AssertionError, "address method table changed");
            return NULL;
        }
        PyObject *function = PyObject_GetAttrString(module, names[i]);
        if (function == NULL) return NULL;
        int valid = PyCFunction_Check(function) && PyCFunction_GetSelf(function) == module &&
                    PyCFunction_GetFunction(function) == method->ml_meth;
        Py_DECREF(function);
        if (!valid) {
            PyErr_SetString(PyExc_AssertionError, "address callback ownership changed");
            return NULL;
        }
    }
    PyMethodDef *end = &def->m_methods[3];
    if (end->ml_name != NULL || end->ml_meth != NULL || end->ml_flags != 0 || end->ml_doc != NULL) {
        PyErr_SetString(PyExc_AssertionError, "method sentinel changed");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {{"check", check, METH_O, NULL}, {NULL, NULL, 0, NULL}};
static PyModuleDef module = {PyModuleDef_HEAD_INIT, "_ipaddress_header_contract", NULL,
                             -1, methods};
PyMODINIT_FUNC PyInit__ipaddress_header_contract(void) { return PyModule_Create(&module); }
