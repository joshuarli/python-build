#include <Python.h>
#include <dlfcn.h>
#include <stddef.h>
#include <string.h>

_Static_assert(sizeof(PySlot) == 16, "64-bit PySlot layout");
_Static_assert(_Alignof(PySlot) == 8, "64-bit PySlot alignment");
_Static_assert(offsetof(PySlot, sl_id) == 0, "slot identifier offset");
_Static_assert(offsetof(PySlot, sl_flags) == 2, "slot flags offset");
_Static_assert(offsetof(PySlot, sl_reserved) == 4, "slot reserved offset");
_Static_assert(offsetof(PySlot, sl_ptr) == 8, "slot payload offset");
_Static_assert(sizeof(PyABIInfo) == 12, "ABI info layout");
_Static_assert(_Alignof(PyABIInfo) == 4, "ABI info alignment");

static PyObject *
check(PyObject *self, PyObject *filename)
{
    const char *path = PyUnicode_AsUTF8(filename);
    if (path == NULL) return NULL;
    void *image = dlopen(path, RTLD_NOW | RTLD_NOLOAD);
    if (image == NULL) {
        PyErr_SetString(PyExc_AssertionError, "socket helper image was not already loaded");
        return NULL;
    }
    PySlot *(*export_slots)(void) = (PySlot *(*)(void))dlsym(image, "PyModExport__socket_rs");
    if (export_slots == NULL || dlsym(image, "PyInit__socket_rs") != NULL) {
        dlclose(image);
        PyErr_SetString(PyExc_AssertionError, "socket loader export contract differs");
        return NULL;
    }
    PySlot *slots = export_slots();
    PyObject *helper = PyImport_ImportModule("_socket_rs");
    if (helper == NULL) {
        dlclose(image);
        return NULL;
    }
    void *token = NULL;
    Py_ssize_t state_size = -1;
    if (PyModule_GetToken(helper, &token) < 0 ||
        PyModule_GetStateSize(helper, &state_size) < 0) {
        Py_DECREF(helper);
        dlclose(image);
        return NULL;
    }
    const uint16_t ids[] = {Py_mod_abi, Py_mod_name, Py_mod_doc,
        Py_mod_methods, Py_mod_multiple_interpreters, 0};
    int valid = slots != NULL && slots == export_slots()
        && PyModule_GetDef(helper) == NULL && token == slots && state_size == 0;
    for (size_t index = 0; valid && index < sizeof(ids)/sizeof(ids[0]); index++) {
        valid = slots[index].sl_id == ids[index] && slots[index].sl_reserved == 0;
        const uint16_t flags = index == 3 ? PySlot_INTPTR | PySlot_STATIC
            : index < 4 ? PySlot_INTPTR : 0;
        valid = valid && slots[index].sl_flags == flags;
    }
    if (valid) {
        PyABIInfo *abi = slots[0].sl_ptr;
        valid = abi && abi->abiinfo_major_version == 1 && abi->abiinfo_minor_version == 0
            && abi->flags == PyABIInfo_GIL && abi->build_version == PY_VERSION_HEX
            && abi->abi_version == PY_VERSION_HEX;
        valid = valid && slots[1].sl_ptr && slots[2].sl_ptr
            && strcmp(slots[1].sl_ptr, "_socket_rs") == 0
            && strcmp(slots[2].sl_ptr, "Rust address conversion and blocking socket I/O") == 0
            && slots[4].sl_uint64 == 2 && slots[5].sl_ptr == NULL;
    }
    const char *names[] = {"parse_address", "format_address", "send", "recv"};
    const char *docs[] = {
        "Parse an IPv4 or IPv6 address into network-order bytes",
        "Format network-order IPv4 or IPv6 bytes",
        "Send bytes through a borrowed blocking socket descriptor",
        "Receive bytes through a borrowed blocking socket descriptor"
    };
    PyMethodDef *methods = valid ? slots[3].sl_ptr : NULL;
    valid = valid && methods != NULL;
    for (size_t index = 0; valid && index < sizeof(names)/sizeof(names[0]); index++) {
        valid = methods[index].ml_name && strcmp(methods[index].ml_name, names[index]) == 0
            && methods[index].ml_meth != NULL && methods[index].ml_flags == METH_FASTCALL
            && methods[index].ml_doc && strcmp(methods[index].ml_doc, docs[index]) == 0;
        if (!valid) break;
        PyObject *method = PyObject_GetAttrString(helper, names[index]);
        if (method == NULL) {
            Py_DECREF(helper);
            dlclose(image);
            return NULL;
        }
        valid = PyCFunction_Check(method) && PyCFunction_GetSelf(method) == helper
            && PyCFunction_GetFunction(method) == methods[index].ml_meth
            && PyCFunction_GetFlags(method) == METH_FASTCALL;
        Py_DECREF(method);
    }
    valid = valid && methods[4].ml_name == NULL && methods[4].ml_meth == NULL
        && methods[4].ml_flags == 0 && methods[4].ml_doc == NULL;
    Py_DECREF(helper);
    dlclose(image);
    if (!valid) {
        PyErr_SetString(PyExc_AssertionError, "socket slots disagree with native headers");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"check", check, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_socket_slot_export_abi", NULL, 0, methods
};
PyMODINIT_FUNC PyInit__socket_slot_export_abi(void)
{
    return PyModule_Create(&module);
}
