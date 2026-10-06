#include <Python.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* Punctuation excludes automatic string interning in the GIL-enabled build.
   The observer borrows constants; adding a fixture reference would hide an
   arena's premature release. */
#define MARKER "compiler arena sentinel / not interned : retained object"
#define SUCCESS_SOURCE "retained = '" MARKER "'; observed = 42\n"
#define RUNTIME_SOURCE "retained = '" MARKER "'; raise ValueError('controlled')\n"
static size_t audits, callbacks, checks, violations;
static Py_ssize_t minimum_refs;
static int active, deny_audit, deny_callback, interactive_filename;
static const char *expected_filename;
static PyObject *register_code, *callback_error;

/* Traceback imports are unrelated to the controlled code checkpoint. */
static PyCodeObject *controlled_code(PyObject *args, Py_ssize_t count) {
    if (!PyTuple_Check(args) || PyTuple_GET_SIZE(args) != count
            || !PyCode_Check(PyTuple_GET_ITEM(args, 0))) return NULL;
    PyCodeObject *code = (PyCodeObject *)PyTuple_GET_ITEM(args, 0);
    const char *name = PyUnicode_AsUTF8(code->co_filename);
    if (!name) return NULL;
    int matches = interactive_filename
        ? strncmp(name, expected_filename, strlen(expected_filename)) == 0
        : strcmp(name, expected_filename) == 0;
    return matches ? code : NULL;
}
static int inspect_constant(PyCodeObject *code) {
    PyObject *value = NULL;
    for (Py_ssize_t i = 0; i < PyTuple_GET_SIZE(code->co_consts); i++) {
        PyObject *item = PyTuple_GET_ITEM(code->co_consts, i);
        if (PyUnicode_CheckExact(item) && PyUnicode_CompareWithASCIIString(item, MARKER) == 0) {
            value = item; break;
        }
        if (PyErr_Occurred()) return -1;
    }
    checks++;
    if (!value) { violations++; return 0; }
    Py_ssize_t refs = Py_REFCNT(value);
    if (refs < minimum_refs) minimum_refs = refs;
    if (refs < 2) violations++;
    /* A C-owned arena object list must remain a GC root across callbacks. */
    if (PyGC_Collect() < 0 || PyErr_Occurred()) return -1;
    if (Py_REFCNT(value) < 2) violations++;
    return 0;
}
static int audit_hook(const char *event, PyObject *args, void *ctx) {
    (void)ctx;
    if (!active || strcmp(event, "exec")) return 0;
    PyCodeObject *code = controlled_code(args, 1);
    if (!code) return PyErr_Occurred() ? -1 : 0;
    audits++;
    if (inspect_constant(code) < 0) return -1;
    if (deny_audit) {
        PyErr_SetString(PyExc_RuntimeError, "controlled exec audit refusal");
        return -1;
    }
    return 0;
}
static PyObject *registration_hook(PyObject *self, PyObject *args) {
    (void)self;
    PyCodeObject *code = active ? controlled_code(args, 3) : NULL;
    if (!code) {
        if (PyErr_Occurred()) return NULL;
        return PyObject_CallObject(register_code, args);
    }
    callbacks++;
    if (inspect_constant(code) < 0) return NULL;
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
    audits = callbacks = checks = violations = 0;
    minimum_refs = PY_SSIZE_T_MAX; active = 1;
}
static int end_case(const char *name, size_t expected_audits, size_t expected_callbacks) {
    active = 0;
    int okay = !violations && audits == expected_audits && callbacks == expected_callbacks
        && checks == expected_audits + expected_callbacks;
    printf("CASE %s audits=%zu callbacks=%zu checks=%zu minimum_refs=%zd violations=%zu %s\n",
           name, audits, callbacks, checks, checks ? minimum_refs : 0, violations,
           okay ? "PASS" : "FAIL");
    return okay;
}
static int global_only(PyObject *globals) {
    PyObject *value = PyDict_GetItemString(globals, "retained");
    int okay = value && PyUnicode_CheckExact(value)
        && PyUnicode_CompareWithASCIIString(value, MARKER) == 0 && Py_REFCNT(value) == 1;
    printf("POST global_refs=%zd %s\n", value ? Py_REFCNT(value) : 0, okay ? "PASS" : "FAIL");
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
    okay &= global_only(globals);
    return okay;
}
static int interactive_case(const char *path, int refuse) {
    const char *source = SUCCESS_SOURCE;
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
    }
    PyObject *module = PyImport_AddModule("__main__");
    PyObject *globals = module ? PyModule_GetDict(module) : NULL;
    okay &= globals && global_only(globals);
    if (!refuse) {
        PyObject *value = globals ? PyDict_GetItemString(globals, "observed") : NULL;
        okay &= value && PyLong_Check(value) && PyLong_AsLong(value) == 42;
    }
    return okay;
}

int main(int argc, char **argv) {
#ifdef Py_GIL_DISABLED
    return 2;
#endif
    if (argc != 3) return 2;
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
        int cases[8];
        cases[0] = object_case("file", SUCCESS_SOURCE, argv[2], globals, NULL, 0);
        cases[1] = object_case("string", SUCCESS_SOURCE, NULL, globals, NULL, 0);
        cases[2] = interactive_case(argv[2], 0);
        cases[3] = object_case("parse_error", "if:\n", argv[2], globals, PyExc_SyntaxError, 0);
        cases[4] = object_case("runtime_error", RUNTIME_SOURCE, NULL, globals, PyExc_ValueError, 0);
        cases[5] = object_case("audit_error", SUCCESS_SOURCE, NULL, globals, PyExc_RuntimeError, 1);
        cases[6] = interactive_case(argv[2], 1);
        cases[7] = object_case("recovery", SUCCESS_SOURCE, NULL, globals, NULL, 0);
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
