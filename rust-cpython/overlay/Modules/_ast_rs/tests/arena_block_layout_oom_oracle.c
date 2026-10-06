#define Py_BUILD_CORE
#include <Python.h>
#include "internal/pycore_pyarena.h"
#include <stdio.h>
#include <string.h>

/* Record only allocations made under this delegate and inject one malloc
   failure. Bookkeeping uses fixed C storage and never calls Python. */
static PyMemAllocatorEx original;
static void *records[128];
static size_t live, attempts, fail_at;
static int overflowed;
static void remember(void *p) {
    if (!p) return;
    for (size_t i = 0; i < 128; i++) {
        if (!records[i]) { records[i] = p; live++; return; }
    }
    overflowed = 1;
}
static void forget(void *p) {
    if (!p) return;
    for (size_t i = 0; i < 128; i++) {
        if (records[i] == p) { records[i] = NULL; live--; return; }
    }
}
static void *tracked_malloc(void *ctx, size_t n) {
    (void)ctx;
    attempts++;
    if (fail_at && attempts == fail_at) return NULL;
    void *p = original.malloc(original.ctx, n); remember(p); return p;
}
static void *tracked_calloc(void *ctx, size_t n, size_t size) {
    (void)ctx; void *p = original.calloc(original.ctx, n, size); remember(p); return p;
}
static void *tracked_realloc(void *ctx, void *p, size_t n) {
    (void)ctx; void *q = original.realloc(original.ctx, p, n);
    if (q) { forget(p); remember(q); }
    return q;
}
static void tracked_free(void *ctx, void *p) {
    (void)ctx; forget(p); original.free(original.ctx, p);
}
static int constructor_cases(void) {
    attempts = fail_at = 0;
    PyArena *control = _PyArena_New();
    if (!control) return 0;
    size_t count = attempts;
    _PyArena_Free(control);
    if (live || overflowed || !count || count > 8) return 0;
    int okay = 1;
    for (size_t n = 1; n <= count; n++) {
        attempts = 0; fail_at = n;
        PyArena *arena = _PyArena_New();
        int failed = !arena && PyErr_ExceptionMatches(PyExc_MemoryError);
        fail_at = 0;
        PyErr_Clear();
        if (arena) _PyArena_Free(arena);
        int cleaned = !live && !overflowed;
        printf("CASE constructor_%zu memory_error=%d live=%zu %s\n", n, failed,
               live, failed && cleaned ? "PASS" : "FAIL");
        okay &= failed && cleaned;
        if (!cleaned) return 0;
    }
    return okay;
}
static int growth_cases(void) {
    PyArena *control = _PyArena_New();
    if (!control) return 0;
    unsigned char *full = _PyArena_Malloc(control, 8192);
    if (!full) { _PyArena_Free(control); return 0; }
    memset(full, 0x51, 8192);
    attempts = 0;
    void *big = _PyArena_Malloc(control, 9000);
    int allocated = big != NULL;
    size_t count = attempts;
    _PyArena_Free(control);
    if (!allocated || live || overflowed || !count || count > 8) return 0;
    int okay = 1;
    for (size_t n = 1; n <= count; n++) {
        PyArena *arena = _PyArena_New();
        if (!arena) return 0;
        full = _PyArena_Malloc(arena, 8192);
        if (!full) { _PyArena_Free(arena); return 0; }
        memset(full, 0x51, 8192);
        attempts = 0; fail_at = n;
        big = _PyArena_Malloc(arena, 9000);
        int failed = !big && PyErr_ExceptionMatches(PyExc_MemoryError);
        fail_at = 0;
        PyErr_Clear();
        int intact = full[0] == 0x51 && full[8191] == 0x51;
        _PyArena_Free(arena);
        int cleaned = !live && !overflowed;
        printf("CASE growth_%zu memory_error=%d intact=%d live=%zu %s\n", n,
               failed, intact, live, failed && intact && cleaned ? "PASS" : "FAIL");
        okay &= failed && intact && cleaned;
        if (!cleaned) return 0;
    }
    return okay;
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    PyConfig config; PyConfig_InitPythonConfig(&config);
    config.use_environment = 0; config.user_site_directory = 0;
    config.site_import = 1; config.safe_path = 1;
    PyStatus status = PyConfig_SetBytesString(&config, &config.home, argv[1]);
    if (!PyStatus_Exception(status)) status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) return 2;
    PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &original);
    PyMemAllocatorEx tracked = {NULL, tracked_malloc, tracked_calloc, tracked_realloc, tracked_free};
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &tracked);
    int constructor = constructor_cases();
    int growth = !live ? growth_cases() : 0;
    fail_at = 0;
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
    int okay = constructor && growth && !live && !overflowed;
    if (PyErr_Occurred()) { PyErr_Print(); okay = 0; }
    if (Py_FinalizeEx() < 0) okay = 0;
    puts(okay ? "PASS" : "FAIL");
    return okay ? 0 : 1;
}
