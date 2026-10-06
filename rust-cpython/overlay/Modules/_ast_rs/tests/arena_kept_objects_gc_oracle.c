#define Py_BUILD_CORE
#include <Python.h>
#include "internal/pycore_pyarena.h"
#include <stdio.h>
#include <string.h>

/* The cycle is reachable only through the arena's retained object list.
   A borrowed C pointer is never used after registration transfers ownership. */
typedef struct {
    PyObject_HEAD
    PyObject *cycle;
} Sentinel;
static int destroyed;
static int sentinel_traverse(Sentinel *self, visitproc visit, void *arg) {
    Py_VISIT(self->cycle);
    return 0;
}
static int sentinel_clear(Sentinel *self) {
    Py_CLEAR(self->cycle);
    return 0;
}
static void sentinel_dealloc(Sentinel *self) {
    PyObject_GC_UnTrack(self);
    destroyed++;
    sentinel_clear(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}
static PyTypeObject Sentinel_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "arena_test.Sentinel",
    .tp_basicsize = sizeof(Sentinel),
    .tp_dealloc = (destructor)sentinel_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = (traverseproc)sentinel_traverse,
    .tp_clear = (inquiry)sentinel_clear,
    .tp_free = PyObject_GC_Del,
};

/* This hook delegates the current MEM allocator without changing its context.
   Fixed C bookkeeping observes only the one controlled default chunk. */
static PyMemAllocatorEx original;
static void *chunk;
static int allocations, frees, duplicate, fail_chunk;
static void *tracked_malloc(void *ctx, size_t size) {
    (void)ctx;
    if (size == 8224 && fail_chunk) return NULL;
    void *p = original.malloc(original.ctx, size);
    if (p && size == 8224) {
        if (chunk) duplicate = 1;
        chunk = p; allocations++;
    }
    return p;
}
static void *tracked_calloc(void *ctx, size_t n, size_t size) {
    (void)ctx; return original.calloc(original.ctx, n, size);
}
static void *tracked_realloc(void *ctx, void *p, size_t size) {
    (void)ctx; return original.realloc(original.ctx, p, size);
}
static void tracked_free(void *ctx, void *p) {
    (void)ctx;
    if (p && p == chunk) { frees++; chunk = NULL; }
    original.free(original.ctx, p);
}
static void reset_counts(void) {
    allocations = frees = duplicate = 0;
}
static int kept_cycle_case(void) {
    PyArena *arena = _PyArena_New();
    if (!arena) return 0;
    void *storage = _PyArena_Malloc(arena, 128);
    Sentinel *sentinel = storage ? PyObject_GC_New(Sentinel, &Sentinel_Type) : NULL;
    if (!sentinel) { _PyArena_Free(arena); return 0; }
    memset(storage, 0x35, 128);
    sentinel->cycle = Py_NewRef((PyObject *)sentinel);
    PyObject_GC_Track(sentinel);
    if (_PyArena_AddPyObject(arena, (PyObject *)sentinel) < 0) {
        Py_DECREF(sentinel); _PyArena_Free(arena); return 0;
    }
    PyObject *objects = _PyArena_FreeAndKeepObjects(arena);
    int okay = allocations == 1 && frees == 1 && !chunk && !duplicate;
    if (PyGC_Collect() < 0) okay = 0;
    okay &= destroyed == 0;
    Py_DECREF(objects);
    if (PyGC_Collect() < 0) okay = 0;
    okay &= destroyed == 1;
    if (PyGC_Collect() < 0) okay = 0;
    okay &= destroyed == 1;
    printf("CASE kept_cycle allocations=%d frees=%d destroyed=%d %s\n",
           allocations, frees, destroyed, okay ? "PASS" : "FAIL");
    return okay;
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
    PyObject *globals = PyDict_New();
    int okay = globals && PyType_Ready(&Sentinel_Type) == 0;
    if (okay) okay = PyDict_SetItemString(globals, "__builtins__", PyEval_GetBuiltins()) == 0;
    if (okay) {
        PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &original);
        PyMemAllocatorEx tracked = {NULL, tracked_malloc, tracked_calloc, tracked_realloc, tracked_free};
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &tracked);
        reset_counts(); fail_chunk = 1;
        PyArena *failed = _PyArena_New();
        int oom_okay = failed == NULL && PyErr_ExceptionMatches(PyExc_MemoryError)
            && allocations == 0 && frees == 0;
        fail_chunk = 0;
        PyErr_Clear();
        if (failed) _PyArena_Free(failed);
        printf("CASE arena_oom %s\n", oom_okay ? "PASS" : "FAIL");
        reset_counts();
        PyObject *result = PyRun_StringFlags("return 'compiler-only error / sentinel'\n",
            Py_file_input, globals, globals, NULL);
        int compile_okay = result == NULL && PyErr_ExceptionMatches(PyExc_SyntaxError)
            && allocations == 1 && frees == 1 && !chunk && !duplicate;
        PyErr_Clear(); Py_XDECREF(result);
        printf("CASE compile_error %s\n", compile_okay ? "PASS" : "FAIL");
        reset_counts();
        int cycle_okay = kept_cycle_case();
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
        okay &= oom_okay && compile_okay && cycle_okay;
    }
    Py_XDECREF(globals);
    if (PyErr_Occurred()) { PyErr_Print(); okay = 0; }
    if (Py_FinalizeEx() < 0) okay = 0;
    puts(okay ? "PASS" : "FAIL");
    return okay ? 0 : 1;
}
