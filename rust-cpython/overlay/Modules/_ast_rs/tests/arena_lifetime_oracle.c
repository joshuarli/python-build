#include <Python.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Only allocations made during a controlled compile are recorded. Delegation
   preserves the installed MEM allocator, including zero-size and realloc rules.
   The embedding fixture creates no threads and runs with the GIL held. */
#define CHUNK_BYTES 8224
#define POINTER_CAPACITY 4096
static PyMemAllocatorEx original;
static void *pointers[POINTER_CAPACITY];
static size_t allocated, live, audits, callbacks, violations;
static int active, overflowed, deny_audit, deny_callback;
static PyObject *register_code, *callback_error;
static const char *expected_filename;
static int interactive_filename;

static void forget(void *p) {
    if (!p) return;
    for (size_t i = 0; i < POINTER_CAPACITY; i++) {
        if (pointers[i] == p) { pointers[i] = NULL; live--; return; }
    }
}
static void remember(void *p, size_t n) {
    if (!active || !p || n != CHUNK_BYTES) return;
    for (size_t i = 0; i < POINTER_CAPACITY; i++) {
        if (!pointers[i]) { pointers[i] = p; allocated++; live++; return; }
    }
    overflowed = 1;
}
static void *tracked_malloc(void *ctx, size_t n) {
    (void)ctx;
    void *p = original.malloc(original.ctx, n); remember(p, n); return p;
}
static void *tracked_calloc(void *ctx, size_t n, size_t size) {
    (void)ctx;
    void *p = original.calloc(original.ctx, n, size);
    if (!size || n <= SIZE_MAX / size) remember(p, n * size);
    return p;
}
static void *tracked_realloc(void *ctx, void *p, size_t n) {
    (void)ctx;
    void *q = original.realloc(original.ctx, p, n);
    if (q) { forget(p); remember(q, n); }
    return q;
}
static void tracked_free(void *ctx, void *p) {
    (void)ctx; forget(p); original.free(original.ctx, p);
}
/* Traceback rendering can execute unrelated imports while a case is active.
   Only this case's code object is a checkpoint or an injectable failure. */
static int controlled_code(PyObject *args, Py_ssize_t count) {
    if (!PyTuple_Check(args) || PyTuple_GET_SIZE(args) != count
            || !PyCode_Check(PyTuple_GET_ITEM(args, 0))) return 0;
    PyObject *name = ((PyCodeObject *)PyTuple_GET_ITEM(args, 0))->co_filename;
    const char *bytes = PyUnicode_AsUTF8(name);
    if (!bytes) return -1;
    return interactive_filename
        ? strncmp(bytes, expected_filename, strlen(expected_filename)) == 0
        : strcmp(bytes, expected_filename) == 0;
}
static int audit_hook(const char *event, PyObject *args, void *ctx) {
    (void)ctx;
    if (!active || strcmp(event, "exec")) return 0;
    int matched = controlled_code(args, 1);
    if (matched <= 0) return matched;
    audits++;
    if (!allocated || live || overflowed) violations++;
    if (deny_audit) {
        PyErr_SetString(PyExc_RuntimeError, "controlled exec audit refusal");
        return -1;
    }
    return 0;
}
static PyObject *registration_hook(PyObject *self, PyObject *args) {
    (void)self;
    int matched = active ? controlled_code(args, 3) : 0;
    if (matched < 0) return NULL;
    if (!matched) return PyObject_CallObject(register_code, args);
    callbacks++;
    if (!allocated || live || overflowed) violations++;
    if (deny_callback) {
        PyObject *error = PyObject_CallFunction(PyExc_SyntaxError, "s(siis)",
            "controlled registration refusal", "arena-interactive.py", 1, 1, "sentinel");
        if (!error) return NULL;
        Py_XSETREF(callback_error, Py_NewRef(error));
        PyErr_SetObject(PyExc_SyntaxError, error);
        Py_DECREF(error);
        return NULL;
    }
    return PyObject_CallObject(register_code, args);
}
static PyMethodDef registration_method = {
    "_register_code", registration_hook, METH_VARARGS, NULL
};

static FILE *script_file(const char *path, const char *source) {
    int fd = open(path, O_RDWR | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return NULL;
    FILE *fp = fdopen(fd, "w+");
    if (!fp) { close(fd); unlink(path); return NULL; }
    size_t length = strlen(source);
    if (fwrite(source, 1, length, fp) != length || fflush(fp)) {
        fclose(fp); unlink(path); return NULL;
    }
    rewind(fp);
    return fp;
}
static void begin_case(void) {
    allocated = audits = callbacks = violations = 0;
    overflowed = 0; active = 1;
}
static int end_case(const char *name, size_t expected_audits, size_t expected_callbacks) {
    active = 0;
    int okay = allocated > 0 && live == 0 && !overflowed && !violations
        && audits == expected_audits && callbacks == expected_callbacks;
    printf("CASE %s allocated=%zu live=%zu audits=%zu callbacks=%zu violations=%zu overflow=%d %s\n",
           name, allocated, live, audits, callbacks, violations, overflowed,
           okay ? "PASS" : "FAIL");
    return okay;
}
static int object_case(const char *name, const char *source, const char *path,
                       PyObject *globals, PyObject *error_type, int refuse) {
    FILE *fp = path ? script_file(path, source) : NULL;
    if (path && !fp) return 0;
    deny_audit = refuse;
    expected_filename = path ? path : "<string>"; interactive_filename = 0;
    begin_case();
    PyObject *result = path
        ? PyRun_FileExFlags(fp, path, Py_file_input, globals, globals, 1, NULL)
        : PyRun_StringFlags(source, Py_file_input, globals, globals, NULL);
    int okay = end_case(name, error_type == PyExc_SyntaxError ? 0 : 1, 0);
    deny_audit = 0;
    if (path && unlink(path)) okay = 0;
    if (error_type) {
        okay &= result == NULL && PyErr_ExceptionMatches(error_type);
        PyErr_Clear();
    } else {
        okay &= result != NULL && !PyErr_Occurred();
        PyObject *value = PyDict_GetItemString(globals, "observed");
        okay &= value && PyLong_Check(value) && PyLong_AsLong(value) == 42;
    }
    Py_XDECREF(result);
    return okay;
}
static int interactive_case(const char *path, int refuse) {
    const char *source = "observed = 42\n";
    FILE *fp = script_file(path, source);
    if (!fp) return 0;
    deny_callback = refuse;
    expected_filename = "arena-interactive.py"; interactive_filename = 1;
    begin_case();
    int result = PyRun_InteractiveOneFlags(fp, "arena-interactive.py", NULL);
    int okay = end_case(refuse ? "interactive_callback_error" : "interactive", refuse ? 0 : 1, 1);
    deny_callback = 0;
    if (fclose(fp) || unlink(path)) okay = 0;
    okay &= result == (refuse ? -1 : 0) && !PyErr_Occurred();
    if (refuse) {
        PyObject *text = callback_error ? PyObject_GetAttrString(callback_error, "text") : NULL;
        const char *bytes = text ? PyUnicode_AsUTF8(text) : NULL;
        okay &= bytes && strcmp(bytes, source) == 0;
        Py_XDECREF(text); Py_CLEAR(callback_error);
        if (PyErr_Occurred()) { PyErr_Clear(); okay = 0; }
    } else {
        PyObject *module = PyImport_AddModule("__main__");
        PyObject *value = module ? PyDict_GetItemString(PyModule_GetDict(module), "observed") : NULL;
        okay &= value && PyLong_Check(value) && PyLong_AsLong(value) == 42;
    }
    return okay;
}

int main(int argc, char **argv) {
    if (argc != 3 || sizeof(void *) != 8 || sizeof(size_t) != 8) return 2;
    PyConfig config; PyConfig_InitPythonConfig(&config);
    config.use_environment = 0; config.user_site_directory = 0;
    config.site_import = 1; config.safe_path = 1;
    PyStatus status = PyConfig_SetBytesString(&config, &config.home, argv[1]);
    if (!PyStatus_Exception(status)) status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) return 2;
    PyObject *linecache = PyImport_ImportModule("linecache");
    PyObject *globals = PyDict_New();
    PyObject *hook = PyCFunction_New(&registration_method, NULL);
    int okay = linecache && globals && hook;
    if (okay) register_code = PyObject_GetAttrString(linecache, "_register_code");
    okay &= register_code != NULL;
    if (okay) okay = PyDict_SetItemString(globals, "__builtins__", PyEval_GetBuiltins()) == 0
        && PyObject_SetAttrString(linecache, "_register_code", hook) == 0;
    if (okay) okay = PySys_AddAuditHook(audit_hook, NULL) == 0;
    if (okay) {
        PyMem_GetAllocator(PYMEM_DOMAIN_MEM, &original);
        PyMemAllocatorEx tracked = {NULL, tracked_malloc, tracked_calloc, tracked_realloc, tracked_free};
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &tracked);
        int cases[8];
        cases[0] = object_case("file", "observed = 42\n", argv[2], globals, NULL, 0);
        cases[1] = object_case("string", "observed = 42\n", NULL, globals, NULL, 0);
        cases[2] = interactive_case(argv[2], 0);
        cases[3] = object_case("parse_error", "if:\n", argv[2], globals, PyExc_SyntaxError, 0);
        cases[4] = object_case("runtime_error", "raise ValueError('controlled')\n", NULL, globals, PyExc_ValueError, 0);
        cases[5] = object_case("audit_error", "observed = 0\n", NULL, globals, PyExc_RuntimeError, 1);
        cases[6] = interactive_case(argv[2], 1);
        cases[7] = object_case("recovery", "observed = 42\n", NULL, globals, NULL, 0);
        active = 0;
        PyMem_SetAllocator(PYMEM_DOMAIN_MEM, &original);
        for (size_t i = 0; i < 8; i++) okay &= cases[i];
    }
    active = 0;
    if (linecache && register_code && PyObject_SetAttrString(linecache, "_register_code", register_code) < 0) okay = 0;
    Py_XDECREF(register_code); Py_XDECREF(hook); Py_XDECREF(linecache);
    Py_XDECREF(globals); Py_XDECREF(callback_error);
    if (PyErr_Occurred()) { PyErr_Print(); okay = 0; }
    if (Py_FinalizeEx() < 0) okay = 0;
    puts(okay ? "PASS" : "FAIL");
    return okay ? 0 : 1;
}
