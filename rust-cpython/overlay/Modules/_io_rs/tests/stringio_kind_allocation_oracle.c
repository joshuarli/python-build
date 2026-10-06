#include <Python.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define INPUT_CHARS 131072
/* These source-derived layouts prove that a kind field fills existing padding.
   They are never used to access an actual StringIO object's private storage. */
#define PREFIX_FIELDS PyObject_HEAD void *buf; Py_ssize_t pos, string_size; size_t buf_size;
#define TAIL_FIELDS void *writer; char flags[4]; PyObject *decoder, *readnl, *writenl, *dict, *weak; void *module;
typedef struct { PREFIX_FIELDS int state; TAIL_FIELDS } OriginalLayout;
typedef struct { PREFIX_FIELDS int state, kind; TAIL_FIELDS } KindLayout;
_Static_assert(sizeof(OriginalLayout) == sizeof(KindLayout), "kind changes object size");
_Static_assert(offsetof(OriginalLayout, writer) == offsetof(KindLayout, writer), "kind moves writer");

/* Fixed C bookkeeping delegates the current MEM allocator. No allocator
   callback calls Python or allocates bookkeeping storage. */
static PyMemAllocatorEx original;
static void *records[128];
static size_t live, largest_request;
static int overflowed;
static size_t slot_for(void *p) {
    if (p) for (size_t i = 0; i < 128; i++) if (records[i] == p) return i;
    return 128;
}
static void requested(size_t n) { if (n > largest_request) largest_request = n; }
static void remember(void *p) {
    if (!p) return;
    for (size_t i = 0; i < 128; i++) {
        if (!records[i]) { records[i] = p; live++; return; }
    }
    overflowed = 1;
}
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
static int discard_call(PyObject *result) {
    if (!result) return 0;
    Py_DECREF(result); return 1;
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
    static char ascii[INPUT_CHARS]; memset(ascii, 'a', sizeof(ascii));
    PyObject *input = PyUnicode_FromStringAndSize(ascii, INPUT_CHARS);
    PyObject *module = PyImport_ImportModule("io");
    PyObject *type = module ? PyObject_GetAttrString(module, "StringIO") : NULL;
    PyObject *stream = type ? PyObject_CallNoArgs(type) : NULL;
    PyObject *weak = stream ? PyWeakref_NewRef(stream, NULL) : NULL;
    int okay = input && type && stream && weak && PyType_Check(type)
        && ((PyTypeObject *)type)->tp_basicsize == sizeof(OriginalLayout);
    /* Empty seek/truncate does not realize the writer; first give it content. */
    if (okay) okay = discard_call(PyObject_CallMethod(stream, "write", "s", "seed"))
        && discard_call(PyObject_CallMethod(stream, "seek", "n", (Py_ssize_t)0))
        && discard_call(PyObject_CallMethod(stream, "truncate", NULL));
    PyObject *value = NULL;
    if (okay) {
        PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &original);
        PyMemAllocatorEx tracked = {NULL, tracked_malloc, tracked_calloc, tracked_realloc, tracked_free};
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &tracked);
        PyObject *written = PyObject_CallMethod(stream, "write", "O", input);
        int wrote = written && PyLong_AsSsize_t(written) == INPUT_CHARS;
        Py_XDECREF(written);
        size_t write_request = largest_request;
        PyObject *position = PyObject_CallMethod(stream, "tell", NULL);
        int cursor = position && PyLong_AsSsize_t(position) == INPUT_CHARS;
        Py_XDECREF(position);
        value = PyObject_CallMethod(stream, "getvalue", NULL);
        int output = value && PyObject_RichCompareBool(value, input, Py_EQ) == 1;
        int closed = discard_call(PyObject_CallMethod(stream, "close", NULL));
        Py_CLEAR(stream);
        PyObject *remaining = NULL;
        int dead = PyWeakref_GetRef(weak, &remaining) == 0;
        Py_XDECREF(remaining);
        int owned = value && PyObject_RichCompareBool(value, input, Py_EQ) == 1;
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
        int allocation = write_request > 0 && write_request <= 2 * INPUT_CHARS;
        printf("ALLOCATION requested=%zu limit=%d %s\n", write_request,
               2 * INPUT_CHARS, allocation ? "PASS" : "FAIL");
        printf("CASE wrote=%d cursor=%d output=%d closed=%d dead=%d owned=%d live=%zu overflow=%d\n",
               wrote, cursor, output, closed, dead, owned, live, overflowed);
        okay &= allocation && wrote && cursor && output && closed && dead && owned
            && !live && !overflowed && !PyErr_Occurred();
    }
    Py_XDECREF(stream); Py_XDECREF(value); Py_XDECREF(weak);
    Py_XDECREF(type); Py_XDECREF(module); Py_XDECREF(input);
    if (PyErr_Occurred()) { PyErr_Print(); okay = 0; }
    if (Py_FinalizeEx() < 0) okay = 0;
    puts(okay ? "PASS" : "FAIL");
    return okay ? 0 : 1;
}
