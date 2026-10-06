#include <Python.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define INPUT_CHARS 131072
/* Inject only the fresh backing allocation of a realized width upgrade.
   Input strings and public snapshots are created outside allocator callbacks. */
static PyMemAllocatorEx original;
static int fail_next, failed, large_mallocs, other_large;
static size_t requested;
static void *fault_malloc(void *ctx, size_t n) {
    (void)ctx;
    if (n >= INPUT_CHARS) {
        large_mallocs++; requested = n;
        if (fail_next) { fail_next = 0; failed = 1; return NULL; }
    }
    return original.malloc(original.ctx, n);
}
static void *fault_calloc(void *ctx, size_t n, size_t size) {
    (void)ctx;
    if (size && n > SIZE_MAX / size) other_large++;
    else if (n * size >= INPUT_CHARS) other_large++;
    return original.calloc(original.ctx, n, size);
}
static void *fault_realloc(void *ctx, void *p, size_t n) {
    (void)ctx;
    if (n >= INPUT_CHARS) other_large++;
    return original.realloc(original.ctx, p, n);
}
static void fault_free(void *ctx, void *p) {
    (void)ctx; original.free(original.ctx, p);
}
static void install(int refuse) {
    fail_next = refuse; failed = large_mallocs = other_large = 0; requested = 0;
    PyMemAllocatorEx hook = {NULL, fault_malloc, fault_calloc, fault_realloc, fault_free};
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &hook);
}
static int discard(PyObject *p) {
    if (!p) return 0;
    Py_DECREF(p); return 1;
}
static int upgrade_case(const char *name, PyObject *stream, PyObject *input,
                        PyObject *expected, Py_ssize_t position, int target_kind) {
    if (!discard(PyObject_CallMethod(stream, "seek", "n", position))) return 0;
    PyObject *before = PyObject_CallMethod(stream, "getvalue", NULL);
    PyObject *state = PyObject_CallMethod(stream, "__getstate__", NULL);
    if (!before || !state) { Py_XDECREF(before); Py_XDECREF(state); return 0; }
    install(1);
    PyObject *result = PyObject_CallMethod(stream, "write", "O", input);
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
    int error = !result && PyErr_ExceptionMatches(PyExc_MemoryError) && failed
        && large_mallocs == 1 && other_large == 0;
    PyErr_Clear(); Py_XDECREF(result);
    PyObject *after = PyObject_CallMethod(stream, "getvalue", NULL);
    PyObject *after_state = PyObject_CallMethod(stream, "__getstate__", NULL);
    PyObject *cursor = PyObject_CallMethod(stream, "tell", NULL);
    int unchanged = after && after_state && cursor
        && PyObject_RichCompareBool(after, before, Py_EQ) == 1
        && PyObject_RichCompareBool(after_state, state, Py_EQ) == 1
        && PyLong_AsSsize_t(cursor) == position;
    Py_XDECREF(after); Py_XDECREF(after_state); Py_XDECREF(cursor);
    Py_DECREF(before); Py_DECREF(state);
    install(0);
    result = PyObject_CallMethod(stream, "write", "O", input);
    PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
    int recovered = result && PyLong_AsSsize_t(result) == 1 && large_mallocs == 1
        && other_large == 0 && requested == (INPUT_CHARS + 2) * (size_t)target_kind;
    Py_XDECREF(result);
    after = PyObject_CallMethod(stream, "getvalue", NULL);
    cursor = PyObject_CallMethod(stream, "tell", NULL);
    recovered &= after && cursor && PyObject_RichCompareBool(after, expected, Py_EQ) == 1
        && PyLong_AsSsize_t(cursor) == position + 1;
    Py_XDECREF(after); Py_XDECREF(cursor);
    printf("CASE %s memory_error=%d unchanged=%d recovered=%d request=%zu %s\n",
           name, error, unchanged, recovered, requested,
           error && unchanged && recovered ? "PASS" : "FAIL");
    return error && unchanged && recovered && !PyErr_Occurred();
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
    static char ascii[INPUT_CHARS];
    static Py_UCS2 bmp_value[INPUT_CHARS];
    static Py_UCS4 astral_value[INPUT_CHARS];
    memset(ascii, 'a', sizeof(ascii));
    for (Py_ssize_t i = 0; i < INPUT_CHARS; i++) bmp_value[i] = astral_value[i] = 'a';
    bmp_value[INPUT_CHARS / 2] = astral_value[INPUT_CHARS / 2] = 0x1234;
    astral_value[INPUT_CHARS / 2 + 7] = 0x1f600;
    PyObject *initial = PyUnicode_FromStringAndSize(ascii, INPUT_CHARS);
    PyObject *bmp_input = PyUnicode_FromOrdinal(0x1234);
    PyObject *astral_input = PyUnicode_FromOrdinal(0x1f600);
    PyObject *bmp = PyUnicode_FromKindAndData(PyUnicode_2BYTE_KIND, bmp_value, INPUT_CHARS);
    PyObject *astral = PyUnicode_FromKindAndData(PyUnicode_4BYTE_KIND, astral_value, INPUT_CHARS);
    PyObject *module = PyImport_ImportModule("io");
    PyObject *type = module ? PyObject_GetAttrString(module, "StringIO") : NULL;
    PyObject *stream = type ? PyObject_CallNoArgs(type) : NULL;
    int okay = initial && bmp_input && astral_input && bmp && astral && stream;
    if (okay) okay = discard(PyObject_CallMethod(stream, "write", "s", "seed"))
        && discard(PyObject_CallMethod(stream, "seek", "n", (Py_ssize_t)0))
        && discard(PyObject_CallMethod(stream, "truncate", NULL))
        && discard(PyObject_CallMethod(stream, "write", "O", initial));
    if (okay) {
        PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &original);
        int first = upgrade_case("ascii_to_bmp", stream, bmp_input, bmp, INPUT_CHARS / 2, 2);
        int second = first ? upgrade_case("bmp_to_astral", stream, astral_input, astral,
                                         INPUT_CHARS / 2 + 7, 4) : 0;
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
        okay &= first && second;
    }
    if (stream && !discard(PyObject_CallMethod(stream, "close", NULL))) okay = 0;
    Py_XDECREF(stream); Py_XDECREF(type); Py_XDECREF(module);
    Py_XDECREF(initial); Py_XDECREF(bmp_input); Py_XDECREF(astral_input);
    Py_XDECREF(bmp); Py_XDECREF(astral);
    if (PyErr_Occurred()) { PyErr_Print(); okay = 0; }
    if (Py_FinalizeEx() < 0) okay = 0;
    puts(okay ? "PASS" : "FAIL");
    return okay ? 0 : 1;
}
