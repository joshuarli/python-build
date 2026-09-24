/* Relocatable x86_64 Linux entrypoint for the bundled Pizfix loader.
 *
 * This file has no libc calls or dynamic dependencies. The kernel starts it
 * directly, and it execs the Fil-C loader found beside the resolved binary.
 * argv[0] retains the public invocation path (including a symlink), while
 * /proc/self/exe locates the install for runtime loading. Copy environment
 * pointers verbatim: a POSIX shell drops keys that are not shell identifiers.
 */

typedef unsigned long size_t;

#define PATH_CAP 4096
#define VECTOR_CAP 65536
#ifndef FILC_LOADER_NAME
#error "Fil-C loader name must come from the selected target"
#endif

static char real_path[PATH_CAP];
static char public_path[PATH_CAP];
static char loader_path[PATH_CAP];
static char python_path[PATH_CAP];
static char launcher_env[PATH_CAP + 32];
static char *loader_argv[VECTOR_CAP];
static char *loader_env[VECTOR_CAP];

static long
syscall3(long number, long a, long b, long c)
{
    long result;
    __asm__ volatile("syscall" : "=a"(result)
                     : "a"(number), "D"(a), "S"(b), "d"(c)
                     : "rcx", "r11", "memory");
    return result;
}

static __attribute__((noreturn)) void
die(void)
{
    static const char message[] = "Fil-C launcher could not start its bundled loader\n";
    syscall3(1, 2, (long)message, sizeof(message) - 1);
    syscall3(60, 127, 0, 0);
    __builtin_unreachable();
}

static size_t
length(const char *string)
{
    size_t n = 0;
    while (string[n] != 0)
        n++;
    return n;
}

static void
append(char *destination, size_t *used, size_t capacity, const char *source)
{
    size_t n = length(source);
    if (*used + n >= capacity)
        die();
    for (size_t i = 0; i < n; i++)
        destination[*used + i] = source[i];
    *used += n;
    destination[*used] = 0;
}

static size_t
read_path(const char *name, char *buffer)
{
    long n = syscall3(89, (long)name, (long)buffer, PATH_CAP - 1);
    if (n <= 0 || n >= PATH_CAP - 1)
        die();
    buffer[n] = 0;
    return (size_t)n;
}

__attribute__((noreturn)) void
filc_start(long *stack)
{
    long argc = stack[0];
    char **argv = (char **)(stack + 1);
    char **env = argv + argc + 1;
    if (argc < 1 || argc >= VECTOR_CAP - 3)
        die();

    size_t real_length = read_path("/proc/self/exe", real_path);
    size_t slash = real_length;
    while (slash > 0 && real_path[slash] != '/')
        slash--;
    if (slash < 4 || real_path[slash - 4] != '/' ||
        real_path[slash - 3] != 'b' || real_path[slash - 2] != 'i' ||
        real_path[slash - 1] != 'n')
        die();
    size_t root_length = slash - 4;
    if (root_length + sizeof("/lib/" FILC_LOADER_NAME) >= PATH_CAP)
        die();
    for (size_t i = 0; i < root_length; i++) {
        loader_path[i] = real_path[i];
        python_path[i] = real_path[i];
    }
    size_t loader_length = root_length;
    size_t python_length = root_length;
    append(loader_path, &loader_length, PATH_CAP, "/lib/" FILC_LOADER_NAME);
    append(python_path, &python_length, PATH_CAP, "/bin/python3.14.real");

    size_t public_length = 0;
    if (argv[0][0] == '/') {
        append(public_path, &public_length, PATH_CAP, argv[0]);
    } else {
        int has_slash = 0;
        for (const char *p = argv[0]; *p; p++)
            has_slash |= *p == '/';
        if (has_slash) {
            public_length = read_path("/proc/self/cwd", public_path);
            append(public_path, &public_length, PATH_CAP, "/");
            append(public_path, &public_length, PATH_CAP, argv[0]);
        } else {
            append(public_path, &public_length, PATH_CAP, real_path);
        }
    }

    size_t env_length = 0;
    append(launcher_env, &env_length, sizeof(launcher_env), "PYTHONEXECUTABLE=");
    append(launcher_env, &env_length, sizeof(launcher_env), public_path);

    loader_argv[0] = loader_path;
    loader_argv[1] = python_path;
    for (long i = 1; i < argc; i++)
        loader_argv[i + 1] = argv[i];
    loader_argv[argc + 1] = 0;

    size_t count = 0;
    for (char **item = env; *item; item++) {
        const char *key = "PYTHONEXECUTABLE=";
        size_t i = 0;
        while (key[i] && (*item)[i] == key[i])
            i++;
        if (key[i] == 0)
            continue;
        if (count >= VECTOR_CAP - 2)
            die();
        loader_env[count++] = *item;
    }
    loader_env[count++] = launcher_env;
    loader_env[count] = 0;
    syscall3(59, (long)loader_path, (long)loader_argv, (long)loader_env);
    die();
}

__asm__(".global _start\n"
        "_start:\n"
        "mov %rsp, %rdi\n"
        "and $-16, %rsp\n"
        "call filc_start\n");
