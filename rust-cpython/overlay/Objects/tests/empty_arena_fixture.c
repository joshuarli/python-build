#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

/* Run in a fresh, single-threaded interpreter.  Arena callbacks delegate
 * unchanged and perform no Python allocation or callback while installed. */
#define MAX_ARENAS 128
#define BLOCK_COUNT 24000
#define BLOCK_SIZE 416
struct record { void *address; size_t size; int released; };
static struct record records[MAX_ARENAS];
static size_t count;
static int active;
static const char *fault;
static PyObjectArenaAllocator previous;

static void *observe_alloc(void *ctx, size_t size)
{
    PyObjectArenaAllocator *a = ctx;
    void *p = a->alloc(a->ctx, size);
    if (p != NULL) {
        if (count == MAX_ARENAS) fault = "arena ledger exhausted";
        else records[count++] = (struct record){p, size, 0};
    }
    return p;
}
static void observe_free(void *ctx, void *p, size_t size)
{
    for (size_t i = 0; i < count; i++) {
        if (records[i].address == p && !records[i].released) {
            if (records[i].size != size) fault = "arena free size changed";
            records[i].released = 1;
            break;
        }
    }
    PyObjectArenaAllocator *a = ctx;
    a->free(a->ctx, p, size);
}
static int contains(struct record *r, void *p)
{
    uintptr_t start = (uintptr_t)r->address, value = (uintptr_t)p;
    return value >= start && value - start < r->size;
}
static PyObject *exercise(PyObject *self, PyObject *ignored)
{
    if (active) return PyErr_Format(PyExc_RuntimeError, "observer already active");
    void **blocks = PyMem_RawCalloc(BLOCK_COUNT, sizeof(void *));
    if (blocks == NULL) return PyErr_NoMemory();
    active = 1;
    fault = NULL;
    PyObject_GetArenaAllocator(&previous);
    PyObjectArenaAllocator observer = {&previous, observe_alloc, observe_free};
    PyObject_SetArenaAllocator(&observer);
    size_t total_arenas = 0;
    for (int cycle = 0; cycle < 3 && fault == NULL; cycle++) {
        count = 0;
        size_t allocated = 0;
        for (; allocated < BLOCK_COUNT; allocated++) {
            blocks[allocated] = PyObject_Malloc(BLOCK_SIZE);
            if (blocks[allocated] == NULL) { fault = "block allocation failed"; break; }
            memset(blocks[allocated], cycle + 1, BLOCK_SIZE);
        }
        size_t keeper = BLOCK_COUNT;
        struct record *owner = NULL;
        if (count == 0) fault = "no fresh arena observed; requires pymalloc";
        if (count > 0) {
            owner = &records[count - 1];
            for (size_t i = 0; i < allocated; i++) {
                if (contains(owner, blocks[i])) { keeper = i; break; }
            }
            if (keeper == BLOCK_COUNT) fault = "new arena has no observed live block";
        }
        for (size_t i = 0; i < allocated; i++) {
            if (i != keeper) { PyObject_Free(blocks[i]); blocks[i] = NULL; }
        }
        if (keeper != BLOCK_COUNT) {
            if (owner->released) fault = "arena released while a block remains live";
            if (((unsigned char *)blocks[keeper])[0] != cycle + 1)
                fault = "live block contents changed";
            PyObject_Free(blocks[keeper]);
            blocks[keeper] = NULL;
        }
        for (size_t i = 0; i < count; i++) {
            if (!records[i].released) fault = "last wholly empty arena retained";
        }
        total_arenas += count;
    }
    /* Restore before constructing any Python result or exception. */
    PyObject_SetArenaAllocator(&previous);
    active = 0;
    PyMem_RawFree(blocks);
    if (fault != NULL) return PyErr_Format(PyExc_AssertionError, "%s", fault);
    return PyLong_FromSize_t(total_arenas);
}
static PyMethodDef methods[] = {{"exercise", exercise, METH_NOARGS, NULL}, {NULL}};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_empty_arena_fixture", NULL, -1, methods};
PyMODINIT_FUNC PyInit__empty_arena_fixture(void) { return PyModule_Create(&module); }
