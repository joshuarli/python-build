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
        PyErr_SetString(PyExc_AssertionError, "zlib image was not already loaded");
        return NULL;
    }
    PySlot *(*export_slots)(void) = (PySlot *(*)(void))dlsym(image, "PyModExport__zlib_rs");
    if (export_slots == NULL || dlsym(image, "PyInit__zlib_rs") != NULL) {
        dlclose(image);
        PyErr_SetString(PyExc_AssertionError, "zlib loader export contract differs");
        return NULL;
    }
    PySlot *slots = export_slots();
    PyObject *helper = PyImport_ImportModule("_zlib_rs");
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
    const uint16_t ids[] = {Py_mod_abi, Py_mod_name, Py_mod_doc, Py_mod_methods,
        Py_mod_exec, Py_mod_multiple_interpreters, Py_mod_state_clear,
        Py_mod_state_free, 0};
    Py_ssize_t state_size = -1;
    if (PyModule_GetStateSize(helper, &state_size) < 0) {
        Py_DECREF(helper); dlclose(image); return NULL;
    }
    int valid = state_size == 0 && slots != NULL && slots == export_slots()
        && PyModule_GetDef(helper) == NULL && token == slots;
    Py_DECREF(helper);
    for (size_t index = 0; valid && index < sizeof(ids)/sizeof(ids[0]); index++) {
        valid = slots[index].sl_id == ids[index] && slots[index].sl_reserved == 0;
        const uint16_t flags = index == 3 ? PySlot_INTPTR | PySlot_STATIC
            : index < 4 ? PySlot_INTPTR : 0;
        valid = valid && slots[index].sl_flags == flags;
    }
    if (valid) {
        PyABIInfo *abi = slots[0].sl_ptr;
        valid = abi && abi->abiinfo_major_version == 1 && abi->abiinfo_minor_version == 0
            && abi->flags == PyABIInfo_GIL && abi->build_version == 0x031000a0
            && abi->abi_version == 0x031000a0
            && (PY_VERSION_HEX & 0xffff0000) == (abi->abi_version & 0xffff0000);
        valid = valid && strcmp(slots[1].sl_ptr, "_zlib_rs") == 0
            && strcmp(slots[2].sl_ptr, "Rust DEFLATE codecs for zlib.") == 0
            && slots[4].sl_func != NULL && slots[5].sl_uint64 == 2
            && slots[6].sl_func != NULL && slots[7].sl_func != NULL
            && slots[8].sl_ptr == NULL;
    }
    const char *names[] = {"compress_once", "decompress_once", "compressor", "compress", "flush", "compressor_copy", "decompressor", "decompress", "eof", "unused_data", "unconsumed_tail", "decompressor_flush", "decompressor_copy"};
    PyMethodDef *methods = valid ? slots[3].sl_ptr : NULL;
    valid = valid && methods != NULL;
    for (size_t index = 0; valid && index < sizeof(names)/sizeof(names[0]); index++) {
        valid = methods[index].ml_name && strcmp(methods[index].ml_name, names[index]) == 0
            && methods[index].ml_meth != NULL && methods[index].ml_flags == METH_FASTCALL
            && methods[index].ml_doc != NULL;
        PyObject *loaded = valid ? PyImport_ImportModule("_zlib_rs") : NULL;
        PyObject *method = loaded ? PyObject_GetAttrString(loaded, names[index]) : NULL;
        valid = valid && method && PyCFunction_CheckExact(method)
            && PyCFunction_GetSelf(method) == loaded
            && PyCFunction_GetFlags(method) == METH_FASTCALL
            && PyCFunction_GetFunction(method) == methods[index].ml_meth;
        Py_XDECREF(method); Py_XDECREF(loaded);
    }
    valid = valid && methods[13].ml_name == NULL && methods[13].ml_meth == NULL;
    dlclose(image);
    if (!valid) {
        PyErr_SetString(PyExc_AssertionError, "zlib slots disagree with native headers");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"check", check, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};
static int exec_module(PyObject *module) { return 0; }
static PyModuleDef_Slot slots[] = {
    {Py_mod_exec, exec_module},
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
    {0, NULL}
};
static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_zlib_slot_export_abi", NULL, 0, methods, slots
};
PyMODINIT_FUNC PyInit__zlib_slot_export_abi(void)
{
    return PyModuleDef_Init(&module);
}
