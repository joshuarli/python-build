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

static unsigned long long malloc_calls, malloc_bytes;
static unsigned long long calloc_calls, calloc_bytes;
static unsigned long long realloc_calls, realloc_bytes;
static unsigned long long size_65537, size_73729;
/* One phase per PID: 0 before begin, 1 while active, 2 after end. */
static int phase_state;
static atomic_flag counter_lock = ATOMIC_FLAG_INIT;
static char output_prefix[PATH_MAX];

static void lock_counters(void) {
    while (atomic_flag_test_and_set_explicit(&counter_lock, memory_order_acquire)) {}
}

static void unlock_counters(void) {
    atomic_flag_clear_explicit(&counter_lock, memory_order_release);
}

/* Call only after interpreter startup and before the measured workload. */
__attribute__((visibility("default"))) int malloc_observer_phase_begin(void) {
    lock_counters();
    int accepted = phase_state == 0;
    if (accepted) phase_state = 1;
    unlock_counters();
    return accepted;
}

/* Successful allocator returns after this call are outside the phase. */
__attribute__((visibility("default"))) int malloc_observer_phase_end(void) {
    lock_counters();
    int accepted = phase_state == 1;
    if (accepted) phase_state = 2;
    unlock_counters();
    return accepted;
}

static void record_size(size_t size) {
    if (size == 65537) size_65537++;
    if (size == 73729) size_73729++;
}

static void *observed_malloc(size_t size) {
    void *p = malloc(size);
    lock_counters();
    if (p && phase_state == 1) {
        malloc_calls++;
        malloc_bytes += size;
        record_size(size);
    }
    unlock_counters();
    return p;
}

static void *observed_calloc(size_t count, size_t size) {
    void *p = calloc(count, size);
    lock_counters();
    if (p && count <= SIZE_MAX / (size ? size : 1) && phase_state == 1) {
        size_t bytes = count * size;
        calloc_calls++;
        calloc_bytes += bytes;
    }
    unlock_counters();
    return p;
}

static void *observed_realloc(void *old, size_t size) {
    void *p = realloc(old, size);
    lock_counters();
    if (p && phase_state == 1) {
        realloc_calls++;
        realloc_bytes += size;
    }
    unlock_counters();
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
    lock_counters();
    int final_phase_state = phase_state;
    if (phase_state == 1) phase_state = 2;
    unsigned long long final_malloc_calls = malloc_calls, final_malloc_bytes = malloc_bytes;
    unsigned long long final_calloc_calls = calloc_calls, final_calloc_bytes = calloc_bytes;
    unsigned long long final_realloc_calls = realloc_calls, final_realloc_bytes = realloc_bytes;
    unsigned long long final_size_65537 = size_65537, final_size_73729 = size_73729;
    unlock_counters();
    char path[PATH_MAX], line[512];
    int path_len = snprintf(path, sizeof(path), "%s.%ld.json", output_prefix, (long)getpid());
    if (path_len <= 0 || (size_t)path_len >= sizeof(path)) return;
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return;
    int line_len = snprintf(line, sizeof(line),
        "{\"pid\":%ld,\"ppid\":%ld,\"phase_state\":%d,\"malloc_calls\":%llu,\"malloc_bytes\":%llu,"
        "\"calloc_calls\":%llu,\"calloc_bytes\":%llu,\"realloc_calls\":%llu,"
        "\"realloc_bytes\":%llu,\"size_65537\":%llu,\"size_73729\":%llu}\n",
        (long)getpid(), (long)getppid(), final_phase_state,
        final_malloc_calls, final_malloc_bytes,
        final_calloc_calls, final_calloc_bytes,
        final_realloc_calls, final_realloc_bytes,
        final_size_65537, final_size_73729);
    if (line_len > 0 && (size_t)line_len < sizeof(line))
        (void)write(fd, line, (size_t)line_len);
    close(fd);
}
