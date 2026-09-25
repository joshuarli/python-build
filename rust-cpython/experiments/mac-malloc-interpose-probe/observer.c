/* Experiment only: requested-size system-allocator counters per interpreter PID. */
#include <fcntl.h>
#include <limits.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static _Atomic unsigned long long malloc_calls, malloc_bytes;
static _Atomic unsigned long long calloc_calls, calloc_bytes;
static _Atomic unsigned long long realloc_calls, realloc_bytes;
static _Atomic unsigned long long size_65537, size_73729;
static _Atomic int reporting;
static char output_prefix[PATH_MAX];

static void record_size(size_t size) {
    if (size == 65537) atomic_fetch_add_explicit(&size_65537, 1, memory_order_relaxed);
    if (size == 73729) atomic_fetch_add_explicit(&size_73729, 1, memory_order_relaxed);
}

static void *observed_malloc(size_t size) {
    void *p = malloc(size);
    if (p && !atomic_load_explicit(&reporting, memory_order_relaxed)) {
        atomic_fetch_add_explicit(&malloc_calls, 1, memory_order_relaxed);
        atomic_fetch_add_explicit(&malloc_bytes, size, memory_order_relaxed);
        record_size(size);
    }
    return p;
}

static void *observed_calloc(size_t count, size_t size) {
    void *p = calloc(count, size);
    if (p && count <= SIZE_MAX / (size ? size : 1) &&
        !atomic_load_explicit(&reporting, memory_order_relaxed)) {
        size_t bytes = count * size;
        atomic_fetch_add_explicit(&calloc_calls, 1, memory_order_relaxed);
        atomic_fetch_add_explicit(&calloc_bytes, bytes, memory_order_relaxed);
    }
    return p;
}

static void *observed_realloc(void *old, size_t size) {
    void *p = realloc(old, size);
    if (p && !atomic_load_explicit(&reporting, memory_order_relaxed)) {
        atomic_fetch_add_explicit(&realloc_calls, 1, memory_order_relaxed);
        atomic_fetch_add_explicit(&realloc_bytes, size, memory_order_relaxed);
    }
    return p;
}

__attribute__((used, section("__DATA,__interpose")))
static const struct { const void *replacement, *replacee; } interposers[] = {
    {(const void *)observed_malloc, (const void *)malloc},
    {(const void *)observed_calloc, (const void *)calloc},
    {(const void *)observed_realloc, (const void *)realloc},
};

__attribute__((constructor)) static void observer_init(void) {
    const char *prefix = getenv("PYTHON_BUILD_MALLOC_OBSERVER_PREFIX");
    if (prefix && strlen(prefix) < sizeof(output_prefix) - 32)
        strcpy(output_prefix, prefix);
}

__attribute__((destructor)) static void observer_finish(void) {
    if (!output_prefix[0]) return;
    atomic_store_explicit(&reporting, 1, memory_order_relaxed);
    char path[PATH_MAX], line[512];
    int path_len = snprintf(path, sizeof(path), "%s.%ld.json", output_prefix, (long)getpid());
    if (path_len <= 0 || (size_t)path_len >= sizeof(path)) return;
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return;
    int line_len = snprintf(line, sizeof(line),
        "{\"pid\":%ld,\"ppid\":%ld,\"malloc_calls\":%llu,\"malloc_bytes\":%llu,"
        "\"calloc_calls\":%llu,\"calloc_bytes\":%llu,\"realloc_calls\":%llu,"
        "\"realloc_bytes\":%llu,\"size_65537\":%llu,\"size_73729\":%llu}\n",
        (long)getpid(), (long)getppid(),
        atomic_load(&malloc_calls), atomic_load(&malloc_bytes),
        atomic_load(&calloc_calls), atomic_load(&calloc_bytes),
        atomic_load(&realloc_calls), atomic_load(&realloc_bytes),
        atomic_load(&size_65537), atomic_load(&size_73729));
    if (line_len > 0 && (size_t)line_len < sizeof(line))
        (void)write(fd, line, (size_t)line_len);
    close(fd);
}
