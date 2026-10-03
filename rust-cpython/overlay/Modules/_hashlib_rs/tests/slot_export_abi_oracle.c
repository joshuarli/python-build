#include <Python.h>
#include <dlfcn.h>
#include <stddef.h>
#include <string.h>

_Static_assert(sizeof(PySlot) == 16, "64-bit slot size");
_Static_assert(_Alignof(PySlot) == 8, "64-bit slot alignment");
_Static_assert(offsetof(PySlot, sl_id) == 0, "slot identifier offset");
_Static_assert(offsetof(PySlot, sl_flags) == 2, "slot flags offset");
_Static_assert(offsetof(PySlot, sl_reserved) == 4, "slot reserved offset");
_Static_assert(offsetof(PySlot, sl_ptr) == 8, "slot payload offset");
_Static_assert(sizeof(PyABIInfo) == 12, "ABI descriptor size");

static PyObject *
check(PyObject *self, PyObject *filename)
{
    const char *path = PyUnicode_AsUTF8(filename);
    if (path == NULL) return NULL;
    void *image = dlopen(path, RTLD_NOW | RTLD_NOLOAD);
    if (image == NULL) {
        PyErr_SetString(PyExc_AssertionError, "hashlib image was not already loaded");
        return NULL;
    }
    PySlot *(*export_slots)(void) = (PySlot *(*)(void))dlsym(image, "PyModExport__hashlib_rs");
    if (export_slots == NULL || dlsym(image, "PyInit__hashlib_rs") != NULL) {
        dlclose(image);
        PyErr_SetString(PyExc_AssertionError, "hashlib loader export differs");
        return NULL;
    }
    PySlot *slots = export_slots();
    PyObject *helper = PyImport_ImportModule("_hashlib_rs");
    if (helper == NULL) {
        dlclose(image);
        return NULL;
    }
    void *token = NULL;
    Py_ssize_t state_size = -1;
    if (PyModule_GetToken(helper, &token) < 0 || PyModule_GetStateSize(helper, &state_size) < 0) {
        Py_DECREF(helper);
        dlclose(image);
        return NULL;
    }
    const uint16_t ids[] = {Py_mod_abi, Py_mod_name, Py_mod_doc, Py_mod_methods,
        Py_mod_state_size, Py_mod_exec, Py_mod_multiple_interpreters,
        Py_mod_state_clear, Py_mod_state_free, 0};
    int valid = slots != NULL && slots == export_slots()
        && PyModule_GetDef(helper) == NULL && token == slots && state_size == 0;
    for (size_t i = 0; valid && i < sizeof(ids)/sizeof(ids[0]); i++) {
        const uint16_t flags = i == 3 ? PySlot_INTPTR | PySlot_STATIC
            : i < 4 ? PySlot_INTPTR : 0;
        valid = slots[i].sl_id == ids[i] && slots[i].sl_flags == flags
            && slots[i].sl_reserved == 0;
    }
    if (valid) {
        PyABIInfo *abi = slots[0].sl_ptr;
        valid = abi && abi->abiinfo_major_version == 1 && abi->abiinfo_minor_version == 0
            && abi->flags == PyABIInfo_GIL && abi->build_version == PY_VERSION_HEX
            && abi->abi_version == PY_VERSION_HEX
            && slots[1].sl_ptr != NULL && strcmp(slots[1].sl_ptr, "_hashlib_rs") == 0
            && slots[2].sl_ptr != NULL
            && strcmp(slots[2].sl_ptr, "RustCrypto digest implementations used by hashlib.") == 0
            && slots[4].sl_size == 0 && slots[5].sl_func != NULL
            && slots[6].sl_uint64 == (uint64_t)(uintptr_t)Py_MOD_MULTIPLE_INTERPRETERS_SUPPORTED
            && slots[7].sl_func != NULL && slots[8].sl_func != NULL
            && slots[9].sl_ptr == NULL;
    }
    PyMethodDef *methods = valid ? slots[3].sl_ptr : NULL;
    valid = valid && methods != NULL && methods[0].ml_name != NULL
        && strcmp(methods[0].ml_name, "new") == 0
        && methods[0].ml_flags == METH_VARARGS && methods[0].ml_meth != NULL
        && methods[0].ml_doc != NULL
        && strcmp(methods[0].ml_doc, "Create a Rust-backed fixed-output digest object.") == 0
        && methods[1].ml_name == NULL && methods[1].ml_meth == NULL
        && methods[1].ml_flags == 0 && methods[1].ml_doc == NULL;
    PyObject *factory = valid ? PyObject_GetAttrString(helper, "new") : NULL;
    if (factory != NULL) {
        valid = PyCFunction_Check(factory) && PyCFunction_GetSelf(factory) == helper
            && PyCFunction_GetFunction(factory) == methods[0].ml_meth
            && PyCFunction_GetFlags(factory) == METH_VARARGS;
        Py_DECREF(factory);
    } else if (valid) {
        Py_DECREF(helper);
        dlclose(image);
        return NULL;
    }
    if (valid) {
        PyObject *args = Py_BuildValue("(sy#)", "sha256", "data", (Py_ssize_t)4);
        PyObject *context = args ? methods[0].ml_meth(helper, args) : NULL;
        Py_XDECREF(args);
        if (context == NULL) {
            Py_DECREF(helper);
            dlclose(image);
            return NULL;
        }
        PyObject *hash_type = PyObject_GetAttrString(helper, "HASH");
        valid = hash_type && (PyObject *)Py_TYPE(context) == hash_type;
        Py_XDECREF(hash_type);
        Py_DECREF(context);
    }
    Py_DECREF(helper);
    dlclose(image);
    if (!valid) {
        PyErr_SetString(PyExc_AssertionError, "hashlib slots disagree with native headers");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"check", check, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_hashlib_slot_export_abi", NULL, 0, methods
};
PyMODINIT_FUNC PyInit__hashlib_slot_export_abi(void)
{
    return PyModule_Create(&module);
}
