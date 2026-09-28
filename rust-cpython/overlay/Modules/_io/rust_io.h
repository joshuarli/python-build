#ifndef PY_RUST_IO_H
#define PY_RUST_IO_H

#include <stddef.h>

/* The caller owns all buffers and keeps them live for the duration of a call. */
Py_ssize_t _PyRust_io_buffer_transfer(void *dst, Py_ssize_t dst_len,
                                      const void *src, Py_ssize_t src_len);
Py_ssize_t _PyRust_io_line_length(const void *data, Py_ssize_t len);
int _PyRust_io_text_newline_flags(const void *data, int kind, Py_ssize_t len);
Py_ssize_t _PyRust_io_translate_newlines(const void *src, void *dst, int kind,
                                         Py_ssize_t len, int *seen);

#endif
