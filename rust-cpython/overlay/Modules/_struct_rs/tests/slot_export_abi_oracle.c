#include <Python.h>
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
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
        PyErr_SetString(PyExc_AssertionError, "struct image was not already loaded");
        return NULL;
    }
    PySlot *(*export_slots)(void) = (PySlot *(*)(void))dlsym(image, "PyModExport__struct_rs");
    if (export_slots == NULL || dlsym(image, "PyInit__struct_rs") != NULL) {
        dlclose(image);
        PyErr_SetString(PyExc_AssertionError, "struct loader export contract differs");
        return NULL;
    }
    PySlot *slots = export_slots();
    PyObject *helper = PyImport_ImportModule("_struct_rs");
    if (helper == NULL) {
        dlclose(image);
        return NULL;
    }
    void *token = NULL;
    if (PyModule_GetToken(helper, &token) < 0) {
        Py_DECREF(helper);
        dlclose(image);
        return NULL;
    }
    Py_ssize_t state_size = -1;
    int state_size_ok = PyModule_GetStateSize(helper, &state_size) == 0;
    const uint16_t ids[] = {Py_mod_abi, Py_mod_name, Py_mod_doc, Py_mod_methods,
        Py_mod_exec, Py_mod_multiple_interpreters, Py_mod_state_clear,
        Py_mod_state_free, 0};
    int valid = slots != NULL && slots == export_slots()
        && PyModule_GetDef(helper) == NULL && state_size_ok && state_size == 0
        && token == slots && PyErr_Occurred() == NULL;
    for (size_t index = 0; valid && index < sizeof(ids)/sizeof(ids[0]); index++) {
        const uint16_t flags = index == 3 ? PySlot_INTPTR | PySlot_STATIC
            : index < 4 ? PySlot_INTPTR : 0;
        valid = slots[index].sl_id == ids[index] && slots[index].sl_reserved == 0
            && slots[index].sl_flags == flags;
    }
    PyABIInfo *abi = valid ? slots[0].sl_ptr : NULL;
    if (valid) {
        valid = abi && abi->abiinfo_major_version == 1 && abi->abiinfo_minor_version == 0
            && abi->flags == PyABIInfo_GIL && abi->build_version == PY_VERSION_HEX
            && abi->abi_version == PY_VERSION_HEX;
        valid = valid && strcmp(slots[1].sl_ptr, "_struct_rs") == 0
            && strcmp(slots[2].sl_ptr,
                      "Rust implementation of standard binary record packing") == 0
            && slots[4].sl_func != NULL
            && slots[5].sl_uint64 == (uint64_t)(uintptr_t)Py_MOD_MULTIPLE_INTERPRETERS_SUPPORTED
            && slots[6].sl_func != NULL && slots[7].sl_func != NULL
            && slots[8].sl_ptr == NULL;
    }
    const char *names[] = {"pack", "unpack", "unpack_from"};
    const char *docs[] = {"Pack supported standard binary records",
        "Unpack supported standard binary records",
        "Unpack a standard binary record at an offset"};
    PyMethodDef *methods = valid ? slots[3].sl_ptr : NULL;
    valid = valid && methods != NULL;
    for (size_t index = 0; valid && index < sizeof(names)/sizeof(names[0]); index++) {
        valid = methods[index].ml_name && strcmp(methods[index].ml_name, names[index]) == 0
            && methods[index].ml_meth != NULL && methods[index].ml_flags == METH_FASTCALL
            && methods[index].ml_doc && strcmp(methods[index].ml_doc, docs[index]) == 0;
        PyObject *method = valid ? PyObject_GetAttrString(helper, names[index]) : NULL;
        if (method == NULL) valid = 0;
        else {
            valid = PyCFunction_GetFlags(method) == METH_FASTCALL
                && PyCFunction_GetSelf(method) == helper
                && PyCFunction_GetFunction(method) == methods[index].ml_meth;
            Py_DECREF(method);
        }
    }
    valid = valid && methods[3].ml_name == NULL && methods[3].ml_meth == NULL;
    if (valid) {
        PySlot saved_slots[9];
        PyMethodDef saved_methods[4];
        PyABIInfo saved_abi;
        memcpy(saved_slots, slots, sizeof(saved_slots));
        memcpy(saved_methods, methods, sizeof(saved_methods));
        memcpy(&saved_abi, abi, sizeof(saved_abi));
        PyObject *pack = PyObject_GetAttrString(helper, "pack");
        PyObject *format = PyUnicode_FromString("<I");
        PyObject *values = Py_BuildValue("(i)", 17);
        if (pack == NULL || format == NULL || values == NULL) valid = 0;
        for (int repeat = 0; valid && repeat < 16; repeat++) {
            PyObject *result = PyObject_CallFunctionObjArgs(pack, format, values, NULL);
            if (result == NULL) valid = 0;
            else {
                valid = PyBytes_CheckExact(result) && PyBytes_GET_SIZE(result) == 4
                    && memcmp(PyBytes_AS_STRING(result), "\x11\0\0\0", 4) == 0;
                Py_DECREF(result);
            }
        }
        Py_XDECREF(pack);
        Py_XDECREF(format);
        Py_XDECREF(values);
        valid = valid && slots == export_slots()
            && memcmp(saved_slots, slots, sizeof(saved_slots)) == 0
            && memcmp(saved_methods, methods, sizeof(saved_methods)) == 0
            && memcmp(&saved_abi, abi, sizeof(saved_abi)) == 0;
    }
    Py_DECREF(helper);
    dlclose(image);
    if (!valid) {
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_AssertionError, "struct slots disagree with native headers or mutate");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"check", check, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_struct_slot_export_abi", NULL, 0, methods
};
PyMODINIT_FUNC PyInit__struct_slot_export_abi(void)
{
    return PyModule_Create(&module);
}
