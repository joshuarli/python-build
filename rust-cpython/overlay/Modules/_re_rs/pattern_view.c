#include "Python.h"
#include "sre.h"
#include <stdint.h>

/* This private state projection follows the configured interpreter's _sre
 * definition. PatternObject itself comes from that interpreter's sre.h. */
typedef struct {
    PyTypeObject *Pattern_Type;
    PyTypeObject *Match_Type;
    PyTypeObject *Scanner_Type;
    PyTypeObject *Template_Type;
    PyObject *compile_template;
} SREModuleState;

PyMODINIT_FUNC PyInit__sre(void);

/* The initializer returns the static definition, not an imported module, and
 * never executes its slots. An existing Pattern has already initialized that
 * definition; repeated PyModuleDef_Init calls leave its index and type intact.
 * The pattern and GIL must remain live throughout use of these borrowed views. */
int
re_rs_borrow_pattern(PyObject *pattern, const uint32_t **code,
                     Py_ssize_t *length, PyObject **source, int *flags)
{
    PyObject *definition = PyInit__sre();
    if (definition == NULL) {
        return -1;
    }
    if (!Py_IS_TYPE(definition, &PyModuleDef_Type)) {
        PyErr_SetString(PyExc_RuntimeError, "unexpected _sre module definition");
        return -1;
    }
    PyModuleDef *def = (PyModuleDef *)definition;
    if (def->m_size != sizeof(SREModuleState)) {
        PyErr_SetString(PyExc_RuntimeError, "unexpected _sre module state size");
        return -1;
    }
    PyObject *module = PyType_GetModuleByDef(Py_TYPE(pattern), def);
    if (module == NULL) {
        if (PyErr_ExceptionMatches(PyExc_TypeError)) {
            PyErr_Clear();
            return 0;
        }
        return -1;
    }
    SREModuleState *state = (SREModuleState *)PyModule_GetState(module);
    if (state == NULL) {
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_RuntimeError, "missing _sre module state");
        }
        return -1;
    }
    if (!Py_IS_TYPE(pattern, state->Pattern_Type)) {
        return 0;
    }
    PatternObject *self = (PatternObject *)pattern;
    if (!PyUnicode_CheckExact(self->pattern) ||
        !PyUnicode_IS_ASCII(self->pattern)) {
        return 0;
    }
    _Static_assert(sizeof(SRE_CODE) == sizeof(uint32_t), "SRE code word width");
    *code = self->code;
    *length = self->codesize;
    *source = self->pattern;
    *flags = self->flags;
    return 1;
}
