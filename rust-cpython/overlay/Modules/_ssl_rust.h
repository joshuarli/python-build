#ifndef Py_SSL_RUST_H
#define Py_SSL_RUST_H

#include <stdint.h>
#include <openssl/ssl.h>

/* OpenSSL's socket and error handling remains in _ssl; Rust owns each TLS
 * operation step and the decision to retry for socket readiness. */
typedef struct {
    SSL_CTX *(*new_context)(const SSL_METHOD *);
    uint64_t (*set_options)(SSL_CTX *, uint64_t);
    long (*set_mode)(SSL_CTX *, long);
    int (*handshake)(SSL *);
    int (*read)(SSL *, void *, size_t, size_t *);
    int (*write)(SSL *, const void *, size_t, size_t *);
    int (*ssl_error)(const SSL *, int);
    int (*os_error)(void);
    int want_read;
    int want_write;
} _PySSL_RustCallbacks;

enum _PySSL_RustOperation {
    PY_SSL_RUST_HANDSHAKE = 0,
    PY_SSL_RUST_READ = 1,
    PY_SSL_RUST_WRITE = 2,
};

enum _PySSL_RustWait {
    PY_SSL_RUST_NO_WAIT = 0,
    PY_SSL_RUST_WAIT_READ = 1,
    PY_SSL_RUST_WAIT_WRITE = 2,
};

typedef struct {
    int result;
    size_t count;
    int ssl_error;
    int os_error;
    int wait_for;
} _PySSL_RustStep;

typedef struct _PySSL_RustAPI {
    SSL_CTX *(*create_context)(const SSL_METHOD *, const _PySSL_RustCallbacks *);
    void (*apply_context_options)(SSL_CTX *, uint64_t,
                                  const _PySSL_RustCallbacks *);
    void (*enable_context_mode)(SSL_CTX *, long,
                                const _PySSL_RustCallbacks *);
    _PySSL_RustStep (*step)(SSL *, int, void *, size_t,
                           const _PySSL_RustCallbacks *);
} _PySSL_RustAPI;

#endif
