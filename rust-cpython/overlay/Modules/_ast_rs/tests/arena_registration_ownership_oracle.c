#define Py_BUILD_CORE
#include <Python.h>
#include "internal/pycore_object.h"
#include "internal/pycore_pyarena.h"
#include <stdio.h>

/* Heap immortality does not grant the generic arena a process-lifetime owner. */
static int destroyed;
static void sentinel_dealloc(PyObject *self) {
    destroyed++; Py_TYPE(self)->tp_free(self);
}
static PyTypeObject Sentinel_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "arena_test.RegistrationSentinel", .tp_basicsize = sizeof(PyObject),
    .tp_dealloc = sentinel_dealloc, .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
};
static PyMemAllocatorEx original;
static int refuse, attempts;
static size_t largest;
static void observed(size_t n) { attempts++; if (n > largest) largest = n; }
static void *fault_malloc(void *ctx, size_t n) {
    (void)ctx; observed(n);
    return refuse ? NULL : original.malloc(original.ctx, n);
}
static void *fault_calloc(void *ctx, size_t n, size_t size) {
    (void)ctx; observed(n && size ? 1 : 0);
    return refuse ? NULL : original.calloc(original.ctx, n, size);
}
static void *fault_realloc(void *ctx, void *p, size_t n) {
    (void)ctx; observed(n);
    return refuse ? NULL : original.realloc(original.ctx, p, n);
}
static void fault_free(void *ctx, void *p) {
    (void)ctx; original.free(original.ctx, p);
}
static void install(int deny) {
    refuse = deny; attempts = 0; largest = 0;
    PyMemAllocatorEx hook = {NULL, fault_malloc, fault_calloc, fault_realloc, fault_free};
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &hook);
}
static int static_and_mortal(void) {
    PyArena *arena = _PyArena_New();
    PyObject *mortal = PyObject_CallNoArgs((PyObject *)&Sentinel_Type);
    if (!arena || !mortal) { if (arena) _PyArena_Free(arena); Py_XDECREF(mortal); return 0; }
    int start = destroyed;
    install(1);
    PyObject *owned = Py_NewRef(Py_None);
    int result = _PyArena_AddPyObject(arena, owned);
    int static_okay = result == 0 && attempts == 0 && !PyErr_Occurred();
    if (result < 0) Py_DECREF(owned);
    PyErr_Clear();
    result = _PyArena_AddPyObject(arena, mortal);
    int mortal_okay = result < 0 && PyErr_ExceptionMatches(PyExc_MemoryError)
        && Py_REFCNT(mortal) == 1 && destroyed == start;
    PyErr_Clear();
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
    _PyArena_Free(arena);
    if (result < 0) Py_DECREF(mortal);
    mortal_okay &= destroyed == start + 1;
    printf("CASE static_no_alloc=%d mortal_oom_owned=%d %s\n", static_okay,
           mortal_okay, static_okay && mortal_okay ? "PASS" : "FAIL");
    return static_okay && mortal_okay;
}
static int heap_immortal(void) {
    PyObject *heap = PyObject_CallNoArgs((PyObject *)&Sentinel_Type);
    PyArena *arena = heap ? _PyArena_New() : NULL;
    if (!heap || !arena) { Py_XDECREF(heap); return 0; }
    int start = destroyed;
    _Py_SetImmortal(heap);
    int okay = _Py_IsImmortal(heap) && !_Py_IsStaticImmortal(heap);
    install(0);
    for (size_t i = 0; i < 8192; i++) {
        PyObject *owned = Py_NewRef(heap);
        if (_PyArena_AddPyObject(arena, owned) < 0) {
            Py_DECREF(owned); okay = 0; break;
        }
    }
    size_t request = largest;
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
    _PyArena_Free(arena);
    okay &= destroyed == start && request > 1024;
    /* The creator retains its logical reference. Restore mortality only after
       all arena entries are gone, then release that one remaining reference. */
    _Py_SetMortal(heap, 1);
    Py_DECREF(heap);
    okay &= destroyed == start + 1;
    printf("CASE heap_immortal_request=%zu destroyed_once=%d %s\n", request,
           destroyed == start + 1, okay ? "PASS" : "FAIL");
    return okay;
}
static int null_boundary(void) {
    PyArena *arena = _PyArena_New();
    if (!arena) return 0;
    int result = _PyArena_AddPyObject(arena, NULL);
    int okay = result < 0 && PyErr_ExceptionMatches(PyExc_SystemError);
    PyErr_Clear(); _PyArena_Free(arena);
    printf("CASE null_system_error %s\n", okay ? "PASS" : "FAIL");
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
    int okay = PyType_Ready(&Sentinel_Type) == 0;
    if (okay) {
        PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &original);
        int first = static_and_mortal();
        int second = heap_immortal();
        int third = null_boundary();
        okay &= first && second && third;
    }
    if (PyErr_Occurred()) { PyErr_Print(); okay = 0; }
    if (Py_FinalizeEx() < 0) okay = 0;
    puts(okay ? "PASS" : "FAIL");
    return okay ? 0 : 1;
}
