#define Py_BUILD_CORE
#include <Python.h>
#include "internal/pycore_pyarena.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Observe the existing MEM allocator without allocating bookkeeping or calling
   Python in its callbacks. This fixture is single-threaded with the GIL held. */
static PyMemAllocatorEx original;
static void *records[128];
static size_t live, large_allocations, largest_request;
static int overflowed, destroyed;
static void remember(void *p, size_t n) {
    if (!p) return;
    for (size_t i = 0; i < 128; i++) {
        if (!records[i]) {
            records[i] = p; live++;
            if (n >= 8192) {
                large_allocations++;
                if (n > largest_request) largest_request = n;
            }
            return;
        }
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
    (void)ctx; void *p = original.malloc(original.ctx, n); remember(p, n); return p;
}
static void *tracked_calloc(void *ctx, size_t n, size_t size) {
    (void)ctx; void *p = original.calloc(original.ctx, n, size);
    if (!size || n <= SIZE_MAX / size) remember(p, n * size);
    return p;
}
static void *tracked_realloc(void *ctx, void *p, size_t n) {
    (void)ctx; void *q = original.realloc(original.ctx, p, n);
    if (q) { forget(p); remember(q, n); }
    return q;
}
static void tracked_free(void *ctx, void *p) {
    (void)ctx; forget(p); original.free(original.ctx, p);
}
/* Registered objects retain their original lifetime until full arena free. */
static void sentinel_dealloc(PyObject *self) {
    destroyed++; Py_TYPE(self)->tp_free(self);
}
static PyTypeObject Sentinel_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "arena_test.LayoutSentinel", .tp_basicsize = sizeof(PyObject),
    .tp_dealloc = sentinel_dealloc, .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
};
static int check_arena(void) {
    PyArena *arena = _PyArena_New();
    if (!arena) return 0;
    int default_okay = large_allocations == 1 && largest_request <= 8192;
    printf("DEFAULT allocations=%zu request=%zu %s\n", large_allocations,
           largest_request, default_okay ? "PASS" : "FAIL");
    size_t before = large_allocations;
    unsigned char *full = _PyArena_Malloc(arena, 8192);
    int fits = full && ((uintptr_t)full % 8) == 0 && large_allocations == before;
    if (full) memset(full, 0x53, 8192);
    unsigned char *oneoff = _PyArena_Malloc(arena, 9000);
    int big = oneoff && ((uintptr_t)oneoff % 8) == 0 && large_allocations == before + 1;
    if (oneoff) memset(oneoff, 0x79, 9000);
    fits &= full && full[0] == 0x53 && full[8191] == 0x53;
    big &= oneoff && oneoff[0] == 0x79 && oneoff[8999] == 0x79;
    PyObject *sentinel = PyObject_CallNoArgs((PyObject *)&Sentinel_Type);
    int owned = sentinel != NULL;
    if (sentinel && _PyArena_AddPyObject(arena, sentinel) < 0) {
        Py_DECREF(sentinel); owned = 0;
    }
    owned &= destroyed == 0;
    _PyArena_Free(arena);
    owned &= destroyed == 1;
    int cleaned = !live && !overflowed && !PyErr_Occurred();
    printf("CASE fit=%d oneoff=%d ownership=%d live=%zu overflow=%d %s\n", fits,
           big, owned, live, overflowed, fits && big && owned && cleaned ? "PASS" : "FAIL");
    return default_okay && fits && big && owned && cleaned;
}
int main(int argc, char **argv) {
    if (argc != 2 || sizeof(void *) != 8 || sizeof(size_t) != 8) return 2;
    PyConfig config; PyConfig_InitPythonConfig(&config);
    config.use_environment = 0; config.user_site_directory = 0;
    config.site_import = 1; config.safe_path = 1;
    PyStatus status = PyConfig_SetBytesString(&config, &config.home, argv[1]);
    if (!PyStatus_Exception(status)) status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) return 2;
    int okay = PyType_Ready(&Sentinel_Type) == 0;
    if (okay) {
        PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &original);
        PyMemAllocatorEx tracked = {NULL, tracked_malloc, tracked_calloc, tracked_realloc, tracked_free};
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &tracked);
        okay = check_arena();
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
    }
    if (PyErr_Occurred()) { PyErr_Print(); okay = 0; }
    if (Py_FinalizeEx() < 0) okay = 0;
    puts(okay ? "PASS" : "FAIL");
    return okay ? 0 : 1;
}
