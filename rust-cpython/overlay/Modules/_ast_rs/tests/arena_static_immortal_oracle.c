#define Py_BUILD_CORE
#include <Python.h>
#include "internal/pycore_pyarena.h"
#include <stdint.h>
#include <stdio.h>

/* Observe only allocations after construction, excluding the AST block.
   The delegate preserves the installed allocator's behavior and context. */
static PyMemAllocatorEx original;
static void *records[128];
static size_t live, largest_request;
static int overflowed, destroyed;
static size_t slot_for(void *p) {
    if (p) for (size_t i = 0; i < 128; i++) if (records[i] == p) return i;
    return 128;
}
static void remember(void *p) {
    if (!p) return;
    for (size_t i = 0; i < 128; i++) {
        if (!records[i]) { records[i] = p; live++; return; }
    }
    overflowed = 1;
}
static void requested(size_t n) { if (n > largest_request) largest_request = n; }
static void *tracked_malloc(void *ctx, size_t n) {
    (void)ctx; requested(n);
    void *p = original.malloc(original.ctx, n); remember(p); return p;
}
static void *tracked_calloc(void *ctx, size_t n, size_t size) {
    (void)ctx;
    if (!size || n <= SIZE_MAX / size) requested(n * size);
    else overflowed = 1;
    void *p = original.calloc(original.ctx, n, size); remember(p); return p;
}
static void *tracked_realloc(void *ctx, void *p, size_t n) {
    (void)ctx; requested(n);
    size_t slot = slot_for(p);
    void *q = original.realloc(original.ctx, p, n);
    if (q) {
        if (slot < 128) records[slot] = q;
        else remember(q);
    }
    return q;
}
static void tracked_free(void *ctx, void *p) {
    (void)ctx; size_t slot = slot_for(p);
    if (slot < 128) { records[slot] = NULL; live--; }
    original.free(original.ctx, p);
}
static void sentinel_dealloc(PyObject *self) {
    destroyed++; Py_TYPE(self)->tp_free(self);
}
static PyTypeObject Sentinel_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "arena_test.MortalSentinel", .tp_basicsize = sizeof(PyObject),
    .tp_dealloc = sentinel_dealloc, .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
};
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
    PyObject *sentinel = okay ? PyObject_CallNoArgs((PyObject *)&Sentinel_Type) : NULL;
    PyArena *arena = sentinel ? _PyArena_New() : NULL;
    okay &= sentinel && arena && _Py_IsImmortal(Py_None) && _Py_IsStaticImmortal(Py_None);
    if (okay) {
        PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &original);
        PyMemAllocatorEx tracked = {NULL, tracked_malloc, tracked_calloc, tracked_realloc, tracked_free};
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &tracked);
        int added = 1;
        for (size_t i = 0; i < 8192; i++) {
            PyObject *owned = Py_NewRef(Py_None);
            if (_PyArena_AddPyObject(arena, owned) < 0) {
                Py_DECREF(owned); added = 0; break;
            }
        }
        if (_PyArena_AddPyObject(arena, sentinel) < 0) added = 0;
        else sentinel = NULL;
        int held = destroyed == 0;
        _PyArena_Free(arena); arena = NULL;
        int released = destroyed == 1 && !live && !overflowed;
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
        int small = largest_request <= 1024;
        printf("ALLOCATION request=%zu limit=1024 %s\n", largest_request, small ? "PASS" : "FAIL");
        printf("CASE added=%d held=%d destroyed=%d live=%zu overflow=%d %s\n",
               added, held, destroyed, live, overflowed,
               added && held && released ? "PASS" : "FAIL");
        okay &= small && added && held && released && !PyErr_Occurred();
    }
    if (arena) _PyArena_Free(arena);
    Py_XDECREF(sentinel);
    if (PyErr_Occurred()) { PyErr_Print(); okay = 0; }
    if (Py_FinalizeEx() < 0) okay = 0;
    puts(okay ? "PASS" : "FAIL");
    return okay ? 0 : 1;
}
