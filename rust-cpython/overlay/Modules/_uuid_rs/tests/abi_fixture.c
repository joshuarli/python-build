#include "Python.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

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
_Static_assert(sizeof(Py_buffer) == 80, "buffer ABI");
_Static_assert(offsetof(Py_buffer, len) == 16, "buffer length offset");
_Static_assert(offsetof(Py_buffer, readonly) == 32, "buffer readonly offset");
_Static_assert(offsetof(Py_buffer, format) == 40, "buffer format offset");
_Static_assert(offsetof(Py_buffer, shape) == 48, "buffer shape offset");
_Static_assert(offsetof(Py_buffer, strides) == 56, "buffer strides offset");
_Static_assert(offsetof(Py_buffer, suboffsets) == 64, "buffer suboffsets offset");
_Static_assert(offsetof(Py_buffer, internal) == 72, "buffer internal offset");
_Static_assert(METH_FASTCALL == 0x80 && METH_O == 8 && METH_VARARGS == 1, "method flags ABI");
_Static_assert(_Py_STATIC_IMMORTAL_INITIAL_REFCNT == ((INT64_C(3) << 30) | (INT64_C(5) << 48)), "static module head flags ABI");

static const char *names[] = {"parse_hex", "normalize", "set_version", "uuid3", "uuid4", "uuid5", "format", "format_hex"};
static const int flags[] = {METH_FASTCALL, METH_FASTCALL, METH_FASTCALL, METH_FASTCALL, METH_FASTCALL, METH_FASTCALL, METH_FASTCALL, METH_FASTCALL};
static PyObject *module_contract(PyObject *module, PyObject *target)
{
    if (!PyModule_Check(target)) { PyErr_SetString(PyExc_TypeError, "module required"); return NULL; }
    PyModuleDef *definition = PyModule_GetDef(target);
    if (!definition || strcmp(definition->m_name, "_uuid_rs") || definition->m_size != 0 ||
        !definition->m_methods || definition->m_slots || definition->m_traverse ||
        !definition->m_clear || !definition->m_free) {
        PyErr_SetString(PyExc_AssertionError, "module definition ABI"); return NULL;
    }
    for (size_t i = 0; i < 8; i++) {
        PyMethodDef *entry = &definition->m_methods[i];
        if (!entry->ml_name || strcmp(entry->ml_name, names[i]) || !entry->ml_meth ||
            !entry->ml_doc || entry->ml_flags != flags[i]) {
            PyErr_SetString(PyExc_AssertionError, "method table ABI"); return NULL;
        }
        PyObject *method = PyObject_GetAttrString(target, names[i]);
        if (!method) return NULL;
        int valid = PyCFunction_CheckExact(method) && PyCFunction_GetSelf(method) == target &&
            PyCFunction_GetFlags(method) == flags[i] && PyCFunction_GetFunction(method) == entry->ml_meth;
        Py_DECREF(method);
        if (!valid) { PyErr_SetString(PyExc_AssertionError, "live method pointer or self ABI"); return NULL; }
    }
    PyMethodDef *end = &definition->m_methods[8];
    if (end->ml_name || end->ml_meth || end->ml_flags || end->ml_doc) {
        PyErr_SetString(PyExc_AssertionError, "method sentinel ABI"); return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *drive(PyObject *module, PyObject *args)
{
    PyObject *target, *values;
    const char *name;
    if (!PyArg_ParseTuple(args, "OsO", &target, &name, &values)) return NULL;
    if (!PyTuple_CheckExact(values)) { PyErr_SetString(PyExc_TypeError, "exact argument tuple required"); return NULL; }
    PyObject *checked = module_contract(module, target);
    if (!checked) return NULL;
    Py_DECREF(checked);
    size_t index;
    for (index = 0; index < 8 && strcmp(name, names[index]); index++) {}
    if (index == 8) { PyErr_SetString(PyExc_ValueError, "unregistered method"); return NULL; }
    PyMethodDef *entry = &PyModule_GetDef(target)->m_methods[index];
    Py_ssize_t count = PyTuple_GET_SIZE(values);
    if (entry->ml_flags == METH_FASTCALL) {
        if (count > 3) { PyErr_SetString(PyExc_ValueError, "at most three arguments"); return NULL; }
        PyObject *arguments[3];
        for (Py_ssize_t i = 0; i < count; i++) arguments[i] = PyTuple_GET_ITEM(values, i);
        return _PyCFunctionFast_CAST(entry->ml_meth)(target, arguments, count);
    }
    if (entry->ml_flags == METH_O) {
        if (count != 1) { PyErr_SetString(PyExc_ValueError, "exactly one argument"); return NULL; }
        return entry->ml_meth(target, PyTuple_GET_ITEM(values, 0));
    }
    return entry->ml_meth(target, values);
}
static PyMethodDef methods[] = {
    {"module_contract", module_contract, METH_O, NULL},
    {"drive", drive, METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef definition = {PyModuleDef_HEAD_INIT, "_uuid_rs_abi_test", NULL, -1, methods};
PyMODINIT_FUNC PyInit__uuid_rs_abi_test(void) { return PyModule_Create(&definition); }
