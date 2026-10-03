#include <Python.h>
#include <dlfcn.h>
#include <stddef.h>
#include <string.h>

_Static_assert(sizeof(void *) == 8, "64-bit module export");
_Static_assert(sizeof(PySlot) == 16, "slot size");
_Static_assert(_Alignof(PySlot) == 8, "slot alignment");
_Static_assert(offsetof(PySlot, sl_id) == 0, "slot identifier offset");
_Static_assert(offsetof(PySlot, sl_flags) == 2, "slot flags offset");
_Static_assert(offsetof(PySlot, sl_reserved) == 4, "reserved offset");
_Static_assert(offsetof(PySlot, sl_ptr) == 8, "payload offset");
_Static_assert(sizeof(PyABIInfo) == 12, "ABI descriptor size");
_Static_assert(_Alignof(PyABIInfo) == 4, "ABI descriptor alignment");
_Static_assert(sizeof(PyMethodDef) == 32, "method definition size");

static PyObject *
check(PyObject *self, PyObject *filename)
{
    const char *path = PyUnicode_AsUTF8(filename);
    if (path == NULL) return NULL;
    void *image = dlopen(path, RTLD_NOW | RTLD_NOLOAD);
    if (image == NULL) {
        PyErr_SetString(PyExc_AssertionError, "regex image was not already loaded");
        return NULL;
    }
    PySlot *(*export_slots)(void) = (PySlot *(*)(void))dlsym(image, "PyModExport__re_rs");
    if (export_slots == NULL || dlsym(image, "PyInit__re_rs") != NULL) {
        dlclose(image);
        PyErr_SetString(PyExc_AssertionError, "regex loader export differs");
        return NULL;
    }
    PySlot *slots = export_slots();
    if (slots == NULL) {
        dlclose(image);
        PyErr_SetString(PyExc_AssertionError, "regex export returned null");
        return NULL;
    }
    const uint16_t ids[] = {Py_mod_abi, Py_mod_name, Py_mod_doc,
        Py_mod_state_size, Py_mod_methods, Py_mod_exec,
        Py_mod_multiple_interpreters, Py_mod_gil, Py_mod_state_clear,
        Py_mod_state_free, 0};
    PySlot snapshot[sizeof(ids) / sizeof(ids[0])];
    int valid = slots == export_slots();
    for (size_t index = 0; valid && index < sizeof(ids) / sizeof(ids[0]); index++) {
        uint16_t flags = index < 3 ? PySlot_INTPTR
            : index == 4 ? PySlot_INTPTR | PySlot_STATIC : 0;
        valid = slots[index].sl_id == ids[index]
            && slots[index].sl_reserved == 0 && slots[index].sl_flags == flags;
    }
    if (valid) {
        const PyABIInfo *abi = slots[0].sl_ptr;
        valid = abi && abi->abiinfo_major_version == 1 && abi->abiinfo_minor_version == 0
            && abi->flags == PyABIInfo_GIL && abi->build_version == PY_VERSION_HEX
            && abi->abi_version == PY_VERSION_HEX;
        valid = valid && strcmp(slots[1].sl_ptr, "_re_rs") == 0
            && strcmp(slots[2].sl_ptr, "Rust regular-expression search for a compatible ASCII subset.") == 0
            && slots[3].sl_size == 0 && slots[5].sl_func != NULL
            && slots[6].sl_uint64 == (uint64_t)(uintptr_t)Py_MOD_MULTIPLE_INTERPRETERS_NOT_SUPPORTED
            && slots[7].sl_uint64 == (uint64_t)(uintptr_t)Py_MOD_GIL_USED
            && slots[8].sl_func != NULL && slots[9].sl_func != NULL
            && slots[10].sl_ptr == NULL;
    }
    const char *names[] = {"prepare", "search"};
    const char *docs[] = {"Prepare a supported regular expression for searching.",
        "Search an ASCII string with a supported expression."};
    const PyMethodDef *methods = valid ? slots[4].sl_ptr : NULL;
    valid = valid && methods != NULL;
    for (size_t index = 0; valid && index < 2; index++) {
        valid = methods[index].ml_name && strcmp(methods[index].ml_name, names[index]) == 0
            && methods[index].ml_doc && strcmp(methods[index].ml_doc, docs[index]) == 0
            && methods[index].ml_meth != NULL && methods[index].ml_flags == METH_FASTCALL;
    }
    valid = valid && methods[2].ml_name == NULL && methods[2].ml_meth == NULL;
    if (!valid) {
        dlclose(image);
        PyErr_SetString(PyExc_AssertionError, "regex slots disagree with native headers");
        return NULL;
    }
    memcpy(snapshot, slots, sizeof(snapshot));
    PyObject *helper = PyImport_ImportModule("_re_rs");
    if (helper == NULL) {
        dlclose(image);
        return NULL;
    }
    void *token = NULL;
    Py_ssize_t state_size = -1;
    if (PyModule_GetToken(helper, &token) < 0
        || PyModule_GetStateSize(helper, &state_size) < 0
        || PyModule_Exec(helper) < 0) {
        Py_DECREF(helper);
        dlclose(image);
        return NULL;
    }
    valid = token == slots && state_size == 0 && PyModule_GetDef(helper) == NULL
        && !PyErr_Occurred() && memcmp(snapshot, slots, sizeof(snapshot)) == 0;
    Py_DECREF(helper);
    dlclose(image);
    if (!valid) {
        PyErr_SetString(PyExc_AssertionError, "regex module token, state, or immutable slots differ");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"check", check, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_re_immutable_export_abi", NULL, 0, methods
};
PyMODINIT_FUNC PyInit__re_immutable_export_abi(void)
{
    return PyModule_Create(&module);
}
