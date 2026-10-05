#ifndef PYSQLITE_RUST_API_H
#define PYSQLITE_RUST_API_H

#include <stddef.h>
#include <stdint.h>
#include "sqlite3.h"

#define PYSQLITE_RUST_API_VERSION 1
#define PYSQLITE_RUST_API_CAPSULE "_sqlite3._RUST_API"

/* The C extension owns these SQLite entry points. Consumers copy the typed
 * table into interpreter-local state without retaining Python references.
 * Both header fields must be checked before reading the function pointers. */
typedef struct {
    uint32_t version;
    size_t size;
    int (*step)(sqlite3_stmt *);
    int (*column_type)(sqlite3_stmt *, int);
    sqlite3_int64 (*column_int64)(sqlite3_stmt *, int);
    double (*column_double)(sqlite3_stmt *, int);
    const unsigned char *(*column_text)(sqlite3_stmt *, int);
    const void *(*column_blob)(sqlite3_stmt *, int);
    int (*column_bytes)(sqlite3_stmt *, int);
    int (*errcode)(sqlite3 *);
} PySqliteRustAPI;

#endif
