#ifndef Py_RUST_SRE_H
#define Py_RUST_SRE_H

#include "Python.h"
#include <stdint.h>

/* No reference is transferred. Hold the pattern and the GIL for the entire
 * use of the borrowed code and source. Unsupported objects return zero;
 * an unexpected failure returns minus one with the exception preserved. */
PyAPI_FUNC(int) _PySRE_BorrowPattern(PyObject *pattern, const uint32_t **code,
                                    Py_ssize_t *length, PyObject **source,
                                    int *flags);

#endif
