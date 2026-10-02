#include "Python.h"
#include <stdint.h>
#include "socketmodule.h"

/* Preserve values, never addresses: ABI slot records may be relocated when
 * two initializers share an image. Unknown pointer contracts fail explicitly. */
static PyObject *
module_contract(PyObject *self, PyObject *module)
{
    PyModuleDef *def = PyModule_GetDef(module);
    if (def == NULL) {
        return NULL;
    }
    PyObject *methods = PyList_New(0);
    PyObject *slots = PyList_New(0);
    PyObject *result = NULL;
    if (methods == NULL || slots == NULL) {
        goto done;
    }
    for (PyMethodDef *method = def->m_methods;
         method != NULL && method->ml_name != NULL; method++) {
        PyObject *entry = Py_BuildValue("(sis)", method->ml_name,
                                        method->ml_flags,
                                        method->ml_doc == NULL ? "" : method->ml_doc);
        if (entry == NULL) {
            goto done;
        }
        int added = PyList_Append(methods, entry);
        Py_DECREF(entry);
        if (added < 0) {
            goto done;
        }
    }
    for (PyModuleDef_Slot *slot = def->m_slots;
         slot != NULL && slot->slot != 0; slot++) {
        PyObject *value = NULL;
        /* Older stable-ABI modules retain legacy IDs in their definition.
         * Decode both spellings while recording the original slot identifier. */
        switch (slot->slot) {
            case 2:
            case Py_mod_exec:
                value = PyBool_FromLong(slot->value != NULL);
                break;
            case 3:
            case Py_mod_multiple_interpreters:
            case 4:
            case Py_mod_gil:
                value = PyLong_FromLong((intptr_t)slot->value);
                break;
            case Py_mod_abi: {
                const PyABIInfo *abi = slot->value;
                if (abi == NULL) {
                    PyErr_SetString(PyExc_ValueError, "NULL module ABI record");
                    goto done;
                }
                value = Py_BuildValue("(iiIII)",
                                     abi->abiinfo_major_version,
                                     abi->abiinfo_minor_version,
                                     (unsigned int)abi->flags,
                                     (unsigned int)abi->build_version,
                                     (unsigned int)abi->abi_version);
                break;
            }
            default:
                PyErr_Format(PyExc_ValueError, "unhandled module slot %d", slot->slot);
                goto done;
        }
        if (value == NULL) {
            goto done;
        }
        PyObject *entry = Py_BuildValue("(iO)", slot->slot, value);
        Py_DECREF(value);
        if (entry == NULL) {
            goto done;
        }
        int added = PyList_Append(slots, entry);
        Py_DECREF(entry);
        if (added < 0) {
            goto done;
        }
    }
    result = Py_BuildValue("{s:s,s:n,s:O,s:O,s:O,s:O,s:O,s:O}",
                          "name", def->m_name, "size", def->m_size,
                          "methods", methods, "slots", slots,
                          "has_traverse", def->m_traverse ? Py_True : Py_False,
                          "has_clear", def->m_clear ? Py_True : Py_False,
                          "has_free", def->m_free ? Py_True : Py_False,
                          "has_slots", def->m_slots ? Py_True : Py_False);
done:
    Py_XDECREF(methods);
    Py_XDECREF(slots);
    return result;
}

static PyObject *
socket_contract(PyObject *self, PyObject *module)
{
    PyObject *capsule = PyObject_GetAttrString(module, PySocket_CAPI_NAME);
    if (capsule == NULL) {
        return NULL;
    }
    PySocketModule_APIObject *api = PyCapsule_GetPointer(capsule, PySocket_CAPSULE_NAME);
    if (api == NULL) {
        Py_DECREF(capsule);
        return NULL;
    }
    /* Returned objects own their references; capsule storage remains original. */
    PyObject *result = Py_BuildValue("{s:O,s:O,s:O}",
                                    "type", (PyObject *)api->Sock_Type,
                                    "error", api->error,
                                    "timeout", api->timeout_error);
    Py_DECREF(capsule);
    return result;
}

static PyMethodDef methods[] = {
    {"module_contract", module_contract, METH_O, NULL},
    {"socket_contract", socket_contract, METH_O, NULL},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef definition = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_socket_image_fixture",
    .m_size = 0,
    .m_methods = methods,
};

PyMODINIT_FUNC
PyInit__socket_image_fixture(void)
{
    return PyModule_Create(&definition);
}
