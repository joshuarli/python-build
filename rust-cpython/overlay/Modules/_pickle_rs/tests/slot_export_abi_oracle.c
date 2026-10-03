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

static PyObject *
check(PyObject *self, PyObject *filename)
{
    const char *path = PyUnicode_AsUTF8(filename);
    if (path == NULL) return NULL;
    void *image = dlopen(path, RTLD_NOW | RTLD_NOLOAD);
    if (image == NULL) {
        PyErr_SetString(PyExc_AssertionError, "pickle image was not already loaded");
        return NULL;
    }
    PySlot *(*export_slots)(void) = (PySlot *(*)(void))dlsym(image, "PyModExport__pickle_rs");
    if (export_slots == NULL || dlsym(image, "PyInit__pickle_rs") != NULL) {
        dlclose(image);
        PyErr_SetString(PyExc_AssertionError, "pickle loader export contract differs");
        return NULL;
    }
    PySlot *slots = export_slots();
    PyObject *helper = PyImport_ImportModule("_pickle_rs");
    if (helper == NULL) { dlclose(image); return NULL; }
    void *token = NULL;
    if (PyModule_GetToken(helper, &token) < 0) {
        Py_DECREF(helper); dlclose(image); return NULL;
    }
    Py_ssize_t state_size = -1;
    if (PyModule_GetStateSize(helper, &state_size) < 0) {
        Py_DECREF(helper); dlclose(image); return NULL;
    }
    const uint16_t ids[] = {Py_mod_abi, Py_mod_name, Py_mod_doc, Py_mod_methods,
        Py_mod_multiple_interpreters, Py_mod_state_clear, Py_mod_state_free, 0};
    int valid = slots != NULL && slots == export_slots()
        && PyModule_GetDef(helper) == NULL && token == slots && state_size == 0;
    for (size_t index = 0; valid && index < sizeof(ids)/sizeof(ids[0]); index++) {
        const uint16_t flags = index == 3 ? PySlot_INTPTR | PySlot_STATIC
            : index < 4 ? PySlot_INTPTR : 0;
        valid = slots[index].sl_id == ids[index] && slots[index].sl_reserved == 0
            && slots[index].sl_flags == flags;
    }
    if (valid) {
        PyABIInfo *abi = slots[0].sl_ptr;
        valid = abi && abi->abiinfo_major_version == 1 && abi->abiinfo_minor_version == 0
            && abi->flags == PyABIInfo_GIL && abi->build_version == PY_VERSION_HEX
            && abi->abi_version == PY_VERSION_HEX;
        valid = valid && strcmp(slots[1].sl_ptr, "_pickle_rs") == 0
            && strcmp(slots[2].sl_ptr, "Rust pickle codec for common builtin object graphs") == 0
            && slots[4].sl_uint64 == 2 && slots[5].sl_func != NULL
            && slots[6].sl_func != NULL && slots[7].sl_ptr == NULL;
    }
    const char *names[] = {"dumps", "loads"};
    const char *docs[] = {"Serialize a supported builtin pickle graph",
        "Deserialize a supported builtin pickle graph"};
    PyMethodDef *definitions = valid ? slots[3].sl_ptr : NULL;
    valid = valid && definitions != NULL;
    for (size_t index = 0; valid && index < 2; index++) {
        PyObject *method = PyObject_GetAttrString(helper, names[index]);
        if (method == NULL) { Py_DECREF(helper); dlclose(image); return NULL; }
        valid = definitions[index].ml_name && strcmp(definitions[index].ml_name, names[index]) == 0
            && definitions[index].ml_doc && strcmp(definitions[index].ml_doc, docs[index]) == 0
            && definitions[index].ml_flags == METH_FASTCALL
            && PyCFunction_Check(method) && PyCFunction_GetSelf(method) == helper
            && PyCFunction_GetFunction(method) == definitions[index].ml_meth;
        Py_DECREF(method);
    }
    valid = valid && definitions[2].ml_name == NULL && definitions[2].ml_meth == NULL;
    Py_DECREF(helper);
    dlclose(image);
    if (!valid) {
        PyErr_SetString(PyExc_AssertionError, "pickle slots disagree with native headers");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"check", check, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_pickle_slot_export_abi", NULL, 0, methods
};
PyMODINIT_FUNC PyInit__pickle_slot_export_abi(void)
{
    return PyModule_Create(&module);
}
