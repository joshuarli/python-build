typedef unsigned long tool_size;
typedef unsigned int tool_u32;
typedef unsigned short tool_u16;
typedef unsigned char tool_byte;
typedef long tool_offset;
enum search_status { SEARCH_OK = 0, SEARCH_BUSY = 1, SEARCH_INVALID = 2, SEARCH_NOT_FOUND = 3 };
typedef enum search_status search_status;
struct search_context;
struct search_cursor;
typedef int (*search_visit_fn)(const void *, tool_size, void *);
typedef void (*search_release_fn)(void *, tool_size);

enum search_query_class_000 {
    SEARCH_QUERY_000_PRIMARY = 1,
    SEARCH_QUERY_000_SECONDARY = 2,
    SEARCH_QUERY_000_ARCHIVED = 4
};
typedef struct search_query_000 {
    tool_u32 id_000;
    tool_u16 revision_000;
    unsigned int flags_000 : 5;
    unsigned int state_000 : 3;
    const char *name_000;
    const tool_byte *payload_000;
    tool_size payload_length_000;
    struct search_query_000 *next_000;
    void *extension_000[3];
} search_query_000;
typedef union search_ranking_value_000 {
    long signed_value_000;
    unsigned long unsigned_value_000;
    double decimal_value_000;
    const void *pointer_value_000;
} search_ranking_value_000;
typedef int (*search_token_callback_000)(
    struct search_context *, const search_query_000 *, void *);
extern search_status search_token_open_000(
    struct search_context **context, const char *path_000, tool_u32 options_000);
extern search_status search_token_close_000(struct search_context *context);
extern int search_ranking_visit_000(
    struct search_context *context, search_token_callback_000 callback, void *userdata);
extern tool_size search_ranking_count_000(const struct search_context *context);
extern const search_query_000 *search_ranking_find_000(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_000(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_001 {
    SEARCH_QUERY_001_PRIMARY = 1,
    SEARCH_QUERY_001_SECONDARY = 2,
    SEARCH_QUERY_001_ARCHIVED = 4
};
typedef struct search_query_001 {
    tool_u32 id_001;
    tool_u16 revision_001;
    unsigned int flags_001 : 5;
    unsigned int state_001 : 3;
    const char *name_001;
    const tool_byte *payload_001;
    tool_size payload_length_001;
    struct search_query_001 *next_001;
    void *extension_001[3];
} search_query_001;
typedef union search_ranking_value_001 {
    long signed_value_001;
    unsigned long unsigned_value_001;
    double decimal_value_001;
    const void *pointer_value_001;
} search_ranking_value_001;
typedef int (*search_token_callback_001)(
    struct search_context *, const search_query_001 *, void *);
extern search_status search_token_open_001(
    struct search_context **context, const char *path_001, tool_u32 options_001);
extern search_status search_token_close_001(struct search_context *context);
extern int search_ranking_visit_001(
    struct search_context *context, search_token_callback_001 callback, void *userdata);
extern tool_size search_ranking_count_001(const struct search_context *context);
extern const search_query_001 *search_ranking_find_001(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_001(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_002 {
    SEARCH_QUERY_002_PRIMARY = 1,
    SEARCH_QUERY_002_SECONDARY = 2,
    SEARCH_QUERY_002_ARCHIVED = 4
};
typedef struct search_query_002 {
    tool_u32 id_002;
    tool_u16 revision_002;
    unsigned int flags_002 : 5;
    unsigned int state_002 : 3;
    const char *name_002;
    const tool_byte *payload_002;
    tool_size payload_length_002;
    struct search_query_002 *next_002;
    void *extension_002[3];
} search_query_002;
typedef union search_ranking_value_002 {
    long signed_value_002;
    unsigned long unsigned_value_002;
    double decimal_value_002;
    const void *pointer_value_002;
} search_ranking_value_002;
typedef int (*search_token_callback_002)(
    struct search_context *, const search_query_002 *, void *);
extern search_status search_token_open_002(
    struct search_context **context, const char *path_002, tool_u32 options_002);
extern search_status search_token_close_002(struct search_context *context);
extern int search_ranking_visit_002(
    struct search_context *context, search_token_callback_002 callback, void *userdata);
extern tool_size search_ranking_count_002(const struct search_context *context);
extern const search_query_002 *search_ranking_find_002(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_002(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_003 {
    SEARCH_QUERY_003_PRIMARY = 1,
    SEARCH_QUERY_003_SECONDARY = 2,
    SEARCH_QUERY_003_ARCHIVED = 4
};
typedef struct search_query_003 {
    tool_u32 id_003;
    tool_u16 revision_003;
    unsigned int flags_003 : 5;
    unsigned int state_003 : 3;
    const char *name_003;
    const tool_byte *payload_003;
    tool_size payload_length_003;
    struct search_query_003 *next_003;
    void *extension_003[3];
} search_query_003;
typedef union search_ranking_value_003 {
    long signed_value_003;
    unsigned long unsigned_value_003;
    double decimal_value_003;
    const void *pointer_value_003;
} search_ranking_value_003;
typedef int (*search_token_callback_003)(
    struct search_context *, const search_query_003 *, void *);
extern search_status search_token_open_003(
    struct search_context **context, const char *path_003, tool_u32 options_003);
extern search_status search_token_close_003(struct search_context *context);
extern int search_ranking_visit_003(
    struct search_context *context, search_token_callback_003 callback, void *userdata);
extern tool_size search_ranking_count_003(const struct search_context *context);
extern const search_query_003 *search_ranking_find_003(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_003(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_004 {
    SEARCH_QUERY_004_PRIMARY = 1,
    SEARCH_QUERY_004_SECONDARY = 2,
    SEARCH_QUERY_004_ARCHIVED = 4
};
typedef struct search_query_004 {
    tool_u32 id_004;
    tool_u16 revision_004;
    unsigned int flags_004 : 5;
    unsigned int state_004 : 3;
    const char *name_004;
    const tool_byte *payload_004;
    tool_size payload_length_004;
    struct search_query_004 *next_004;
    void *extension_004[3];
} search_query_004;
typedef union search_ranking_value_004 {
    long signed_value_004;
    unsigned long unsigned_value_004;
    double decimal_value_004;
    const void *pointer_value_004;
} search_ranking_value_004;
typedef int (*search_token_callback_004)(
    struct search_context *, const search_query_004 *, void *);
extern search_status search_token_open_004(
    struct search_context **context, const char *path_004, tool_u32 options_004);
extern search_status search_token_close_004(struct search_context *context);
extern int search_ranking_visit_004(
    struct search_context *context, search_token_callback_004 callback, void *userdata);
extern tool_size search_ranking_count_004(const struct search_context *context);
extern const search_query_004 *search_ranking_find_004(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_004(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_005 {
    SEARCH_QUERY_005_PRIMARY = 1,
    SEARCH_QUERY_005_SECONDARY = 2,
    SEARCH_QUERY_005_ARCHIVED = 4
};
typedef struct search_query_005 {
    tool_u32 id_005;
    tool_u16 revision_005;
    unsigned int flags_005 : 5;
    unsigned int state_005 : 3;
    const char *name_005;
    const tool_byte *payload_005;
    tool_size payload_length_005;
    struct search_query_005 *next_005;
    void *extension_005[3];
} search_query_005;
typedef union search_ranking_value_005 {
    long signed_value_005;
    unsigned long unsigned_value_005;
    double decimal_value_005;
    const void *pointer_value_005;
} search_ranking_value_005;
typedef int (*search_token_callback_005)(
    struct search_context *, const search_query_005 *, void *);
extern search_status search_token_open_005(
    struct search_context **context, const char *path_005, tool_u32 options_005);
extern search_status search_token_close_005(struct search_context *context);
extern int search_ranking_visit_005(
    struct search_context *context, search_token_callback_005 callback, void *userdata);
extern tool_size search_ranking_count_005(const struct search_context *context);
extern const search_query_005 *search_ranking_find_005(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_005(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_006 {
    SEARCH_QUERY_006_PRIMARY = 1,
    SEARCH_QUERY_006_SECONDARY = 2,
    SEARCH_QUERY_006_ARCHIVED = 4
};
typedef struct search_query_006 {
    tool_u32 id_006;
    tool_u16 revision_006;
    unsigned int flags_006 : 5;
    unsigned int state_006 : 3;
    const char *name_006;
    const tool_byte *payload_006;
    tool_size payload_length_006;
    struct search_query_006 *next_006;
    void *extension_006[3];
} search_query_006;
typedef union search_ranking_value_006 {
    long signed_value_006;
    unsigned long unsigned_value_006;
    double decimal_value_006;
    const void *pointer_value_006;
} search_ranking_value_006;
typedef int (*search_token_callback_006)(
    struct search_context *, const search_query_006 *, void *);
extern search_status search_token_open_006(
    struct search_context **context, const char *path_006, tool_u32 options_006);
extern search_status search_token_close_006(struct search_context *context);
extern int search_ranking_visit_006(
    struct search_context *context, search_token_callback_006 callback, void *userdata);
extern tool_size search_ranking_count_006(const struct search_context *context);
extern const search_query_006 *search_ranking_find_006(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_006(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_007 {
    SEARCH_QUERY_007_PRIMARY = 1,
    SEARCH_QUERY_007_SECONDARY = 2,
    SEARCH_QUERY_007_ARCHIVED = 4
};
typedef struct search_query_007 {
    tool_u32 id_007;
    tool_u16 revision_007;
    unsigned int flags_007 : 5;
    unsigned int state_007 : 3;
    const char *name_007;
    const tool_byte *payload_007;
    tool_size payload_length_007;
    struct search_query_007 *next_007;
    void *extension_007[3];
} search_query_007;
typedef union search_ranking_value_007 {
    long signed_value_007;
    unsigned long unsigned_value_007;
    double decimal_value_007;
    const void *pointer_value_007;
} search_ranking_value_007;
typedef int (*search_token_callback_007)(
    struct search_context *, const search_query_007 *, void *);
extern search_status search_token_open_007(
    struct search_context **context, const char *path_007, tool_u32 options_007);
extern search_status search_token_close_007(struct search_context *context);
extern int search_ranking_visit_007(
    struct search_context *context, search_token_callback_007 callback, void *userdata);
extern tool_size search_ranking_count_007(const struct search_context *context);
extern const search_query_007 *search_ranking_find_007(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_007(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_008 {
    SEARCH_QUERY_008_PRIMARY = 1,
    SEARCH_QUERY_008_SECONDARY = 2,
    SEARCH_QUERY_008_ARCHIVED = 4
};
typedef struct search_query_008 {
    tool_u32 id_008;
    tool_u16 revision_008;
    unsigned int flags_008 : 5;
    unsigned int state_008 : 3;
    const char *name_008;
    const tool_byte *payload_008;
    tool_size payload_length_008;
    struct search_query_008 *next_008;
    void *extension_008[3];
} search_query_008;
typedef union search_ranking_value_008 {
    long signed_value_008;
    unsigned long unsigned_value_008;
    double decimal_value_008;
    const void *pointer_value_008;
} search_ranking_value_008;
typedef int (*search_token_callback_008)(
    struct search_context *, const search_query_008 *, void *);
extern search_status search_token_open_008(
    struct search_context **context, const char *path_008, tool_u32 options_008);
extern search_status search_token_close_008(struct search_context *context);
extern int search_ranking_visit_008(
    struct search_context *context, search_token_callback_008 callback, void *userdata);
extern tool_size search_ranking_count_008(const struct search_context *context);
extern const search_query_008 *search_ranking_find_008(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_008(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_009 {
    SEARCH_QUERY_009_PRIMARY = 1,
    SEARCH_QUERY_009_SECONDARY = 2,
    SEARCH_QUERY_009_ARCHIVED = 4
};
typedef struct search_query_009 {
    tool_u32 id_009;
    tool_u16 revision_009;
    unsigned int flags_009 : 5;
    unsigned int state_009 : 3;
    const char *name_009;
    const tool_byte *payload_009;
    tool_size payload_length_009;
    struct search_query_009 *next_009;
    void *extension_009[3];
} search_query_009;
typedef union search_ranking_value_009 {
    long signed_value_009;
    unsigned long unsigned_value_009;
    double decimal_value_009;
    const void *pointer_value_009;
} search_ranking_value_009;
typedef int (*search_token_callback_009)(
    struct search_context *, const search_query_009 *, void *);
extern search_status search_token_open_009(
    struct search_context **context, const char *path_009, tool_u32 options_009);
extern search_status search_token_close_009(struct search_context *context);
extern int search_ranking_visit_009(
    struct search_context *context, search_token_callback_009 callback, void *userdata);
extern tool_size search_ranking_count_009(const struct search_context *context);
extern const search_query_009 *search_ranking_find_009(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_009(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_010 {
    SEARCH_QUERY_010_PRIMARY = 1,
    SEARCH_QUERY_010_SECONDARY = 2,
    SEARCH_QUERY_010_ARCHIVED = 4
};
typedef struct search_query_010 {
    tool_u32 id_010;
    tool_u16 revision_010;
    unsigned int flags_010 : 5;
    unsigned int state_010 : 3;
    const char *name_010;
    const tool_byte *payload_010;
    tool_size payload_length_010;
    struct search_query_010 *next_010;
    void *extension_010[3];
} search_query_010;
typedef union search_ranking_value_010 {
    long signed_value_010;
    unsigned long unsigned_value_010;
    double decimal_value_010;
    const void *pointer_value_010;
} search_ranking_value_010;
typedef int (*search_token_callback_010)(
    struct search_context *, const search_query_010 *, void *);
extern search_status search_token_open_010(
    struct search_context **context, const char *path_010, tool_u32 options_010);
extern search_status search_token_close_010(struct search_context *context);
extern int search_ranking_visit_010(
    struct search_context *context, search_token_callback_010 callback, void *userdata);
extern tool_size search_ranking_count_010(const struct search_context *context);
extern const search_query_010 *search_ranking_find_010(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_010(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_011 {
    SEARCH_QUERY_011_PRIMARY = 1,
    SEARCH_QUERY_011_SECONDARY = 2,
    SEARCH_QUERY_011_ARCHIVED = 4
};
typedef struct search_query_011 {
    tool_u32 id_011;
    tool_u16 revision_011;
    unsigned int flags_011 : 5;
    unsigned int state_011 : 3;
    const char *name_011;
    const tool_byte *payload_011;
    tool_size payload_length_011;
    struct search_query_011 *next_011;
    void *extension_011[3];
} search_query_011;
typedef union search_ranking_value_011 {
    long signed_value_011;
    unsigned long unsigned_value_011;
    double decimal_value_011;
    const void *pointer_value_011;
} search_ranking_value_011;
typedef int (*search_token_callback_011)(
    struct search_context *, const search_query_011 *, void *);
extern search_status search_token_open_011(
    struct search_context **context, const char *path_011, tool_u32 options_011);
extern search_status search_token_close_011(struct search_context *context);
extern int search_ranking_visit_011(
    struct search_context *context, search_token_callback_011 callback, void *userdata);
extern tool_size search_ranking_count_011(const struct search_context *context);
extern const search_query_011 *search_ranking_find_011(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_011(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_012 {
    SEARCH_QUERY_012_PRIMARY = 1,
    SEARCH_QUERY_012_SECONDARY = 2,
    SEARCH_QUERY_012_ARCHIVED = 4
};
typedef struct search_query_012 {
    tool_u32 id_012;
    tool_u16 revision_012;
    unsigned int flags_012 : 5;
    unsigned int state_012 : 3;
    const char *name_012;
    const tool_byte *payload_012;
    tool_size payload_length_012;
    struct search_query_012 *next_012;
    void *extension_012[3];
} search_query_012;
typedef union search_ranking_value_012 {
    long signed_value_012;
    unsigned long unsigned_value_012;
    double decimal_value_012;
    const void *pointer_value_012;
} search_ranking_value_012;
typedef int (*search_token_callback_012)(
    struct search_context *, const search_query_012 *, void *);
extern search_status search_token_open_012(
    struct search_context **context, const char *path_012, tool_u32 options_012);
extern search_status search_token_close_012(struct search_context *context);
extern int search_ranking_visit_012(
    struct search_context *context, search_token_callback_012 callback, void *userdata);
extern tool_size search_ranking_count_012(const struct search_context *context);
extern const search_query_012 *search_ranking_find_012(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_012(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_013 {
    SEARCH_QUERY_013_PRIMARY = 1,
    SEARCH_QUERY_013_SECONDARY = 2,
    SEARCH_QUERY_013_ARCHIVED = 4
};
typedef struct search_query_013 {
    tool_u32 id_013;
    tool_u16 revision_013;
    unsigned int flags_013 : 5;
    unsigned int state_013 : 3;
    const char *name_013;
    const tool_byte *payload_013;
    tool_size payload_length_013;
    struct search_query_013 *next_013;
    void *extension_013[3];
} search_query_013;
typedef union search_ranking_value_013 {
    long signed_value_013;
    unsigned long unsigned_value_013;
    double decimal_value_013;
    const void *pointer_value_013;
} search_ranking_value_013;
typedef int (*search_token_callback_013)(
    struct search_context *, const search_query_013 *, void *);
extern search_status search_token_open_013(
    struct search_context **context, const char *path_013, tool_u32 options_013);
extern search_status search_token_close_013(struct search_context *context);
extern int search_ranking_visit_013(
    struct search_context *context, search_token_callback_013 callback, void *userdata);
extern tool_size search_ranking_count_013(const struct search_context *context);
extern const search_query_013 *search_ranking_find_013(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_013(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_014 {
    SEARCH_QUERY_014_PRIMARY = 1,
    SEARCH_QUERY_014_SECONDARY = 2,
    SEARCH_QUERY_014_ARCHIVED = 4
};
typedef struct search_query_014 {
    tool_u32 id_014;
    tool_u16 revision_014;
    unsigned int flags_014 : 5;
    unsigned int state_014 : 3;
    const char *name_014;
    const tool_byte *payload_014;
    tool_size payload_length_014;
    struct search_query_014 *next_014;
    void *extension_014[3];
} search_query_014;
typedef union search_ranking_value_014 {
    long signed_value_014;
    unsigned long unsigned_value_014;
    double decimal_value_014;
    const void *pointer_value_014;
} search_ranking_value_014;
typedef int (*search_token_callback_014)(
    struct search_context *, const search_query_014 *, void *);
extern search_status search_token_open_014(
    struct search_context **context, const char *path_014, tool_u32 options_014);
extern search_status search_token_close_014(struct search_context *context);
extern int search_ranking_visit_014(
    struct search_context *context, search_token_callback_014 callback, void *userdata);
extern tool_size search_ranking_count_014(const struct search_context *context);
extern const search_query_014 *search_ranking_find_014(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_014(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_015 {
    SEARCH_QUERY_015_PRIMARY = 1,
    SEARCH_QUERY_015_SECONDARY = 2,
    SEARCH_QUERY_015_ARCHIVED = 4
};
typedef struct search_query_015 {
    tool_u32 id_015;
    tool_u16 revision_015;
    unsigned int flags_015 : 5;
    unsigned int state_015 : 3;
    const char *name_015;
    const tool_byte *payload_015;
    tool_size payload_length_015;
    struct search_query_015 *next_015;
    void *extension_015[3];
} search_query_015;
typedef union search_ranking_value_015 {
    long signed_value_015;
    unsigned long unsigned_value_015;
    double decimal_value_015;
    const void *pointer_value_015;
} search_ranking_value_015;
typedef int (*search_token_callback_015)(
    struct search_context *, const search_query_015 *, void *);
extern search_status search_token_open_015(
    struct search_context **context, const char *path_015, tool_u32 options_015);
extern search_status search_token_close_015(struct search_context *context);
extern int search_ranking_visit_015(
    struct search_context *context, search_token_callback_015 callback, void *userdata);
extern tool_size search_ranking_count_015(const struct search_context *context);
extern const search_query_015 *search_ranking_find_015(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_015(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_016 {
    SEARCH_QUERY_016_PRIMARY = 1,
    SEARCH_QUERY_016_SECONDARY = 2,
    SEARCH_QUERY_016_ARCHIVED = 4
};
typedef struct search_query_016 {
    tool_u32 id_016;
    tool_u16 revision_016;
    unsigned int flags_016 : 5;
    unsigned int state_016 : 3;
    const char *name_016;
    const tool_byte *payload_016;
    tool_size payload_length_016;
    struct search_query_016 *next_016;
    void *extension_016[3];
} search_query_016;
typedef union search_ranking_value_016 {
    long signed_value_016;
    unsigned long unsigned_value_016;
    double decimal_value_016;
    const void *pointer_value_016;
} search_ranking_value_016;
typedef int (*search_token_callback_016)(
    struct search_context *, const search_query_016 *, void *);
extern search_status search_token_open_016(
    struct search_context **context, const char *path_016, tool_u32 options_016);
extern search_status search_token_close_016(struct search_context *context);
extern int search_ranking_visit_016(
    struct search_context *context, search_token_callback_016 callback, void *userdata);
extern tool_size search_ranking_count_016(const struct search_context *context);
extern const search_query_016 *search_ranking_find_016(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_016(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_017 {
    SEARCH_QUERY_017_PRIMARY = 1,
    SEARCH_QUERY_017_SECONDARY = 2,
    SEARCH_QUERY_017_ARCHIVED = 4
};
typedef struct search_query_017 {
    tool_u32 id_017;
    tool_u16 revision_017;
    unsigned int flags_017 : 5;
    unsigned int state_017 : 3;
    const char *name_017;
    const tool_byte *payload_017;
    tool_size payload_length_017;
    struct search_query_017 *next_017;
    void *extension_017[3];
} search_query_017;
typedef union search_ranking_value_017 {
    long signed_value_017;
    unsigned long unsigned_value_017;
    double decimal_value_017;
    const void *pointer_value_017;
} search_ranking_value_017;
typedef int (*search_token_callback_017)(
    struct search_context *, const search_query_017 *, void *);
extern search_status search_token_open_017(
    struct search_context **context, const char *path_017, tool_u32 options_017);
extern search_status search_token_close_017(struct search_context *context);
extern int search_ranking_visit_017(
    struct search_context *context, search_token_callback_017 callback, void *userdata);
extern tool_size search_ranking_count_017(const struct search_context *context);
extern const search_query_017 *search_ranking_find_017(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_017(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_018 {
    SEARCH_QUERY_018_PRIMARY = 1,
    SEARCH_QUERY_018_SECONDARY = 2,
    SEARCH_QUERY_018_ARCHIVED = 4
};
typedef struct search_query_018 {
    tool_u32 id_018;
    tool_u16 revision_018;
    unsigned int flags_018 : 5;
    unsigned int state_018 : 3;
    const char *name_018;
    const tool_byte *payload_018;
    tool_size payload_length_018;
    struct search_query_018 *next_018;
    void *extension_018[3];
} search_query_018;
typedef union search_ranking_value_018 {
    long signed_value_018;
    unsigned long unsigned_value_018;
    double decimal_value_018;
    const void *pointer_value_018;
} search_ranking_value_018;
typedef int (*search_token_callback_018)(
    struct search_context *, const search_query_018 *, void *);
extern search_status search_token_open_018(
    struct search_context **context, const char *path_018, tool_u32 options_018);
extern search_status search_token_close_018(struct search_context *context);
extern int search_ranking_visit_018(
    struct search_context *context, search_token_callback_018 callback, void *userdata);
extern tool_size search_ranking_count_018(const struct search_context *context);
extern const search_query_018 *search_ranking_find_018(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_018(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_019 {
    SEARCH_QUERY_019_PRIMARY = 1,
    SEARCH_QUERY_019_SECONDARY = 2,
    SEARCH_QUERY_019_ARCHIVED = 4
};
typedef struct search_query_019 {
    tool_u32 id_019;
    tool_u16 revision_019;
    unsigned int flags_019 : 5;
    unsigned int state_019 : 3;
    const char *name_019;
    const tool_byte *payload_019;
    tool_size payload_length_019;
    struct search_query_019 *next_019;
    void *extension_019[3];
} search_query_019;
typedef union search_ranking_value_019 {
    long signed_value_019;
    unsigned long unsigned_value_019;
    double decimal_value_019;
    const void *pointer_value_019;
} search_ranking_value_019;
typedef int (*search_token_callback_019)(
    struct search_context *, const search_query_019 *, void *);
extern search_status search_token_open_019(
    struct search_context **context, const char *path_019, tool_u32 options_019);
extern search_status search_token_close_019(struct search_context *context);
extern int search_ranking_visit_019(
    struct search_context *context, search_token_callback_019 callback, void *userdata);
extern tool_size search_ranking_count_019(const struct search_context *context);
extern const search_query_019 *search_ranking_find_019(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_019(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_020 {
    SEARCH_QUERY_020_PRIMARY = 1,
    SEARCH_QUERY_020_SECONDARY = 2,
    SEARCH_QUERY_020_ARCHIVED = 4
};
typedef struct search_query_020 {
    tool_u32 id_020;
    tool_u16 revision_020;
    unsigned int flags_020 : 5;
    unsigned int state_020 : 3;
    const char *name_020;
    const tool_byte *payload_020;
    tool_size payload_length_020;
    struct search_query_020 *next_020;
    void *extension_020[3];
} search_query_020;
typedef union search_ranking_value_020 {
    long signed_value_020;
    unsigned long unsigned_value_020;
    double decimal_value_020;
    const void *pointer_value_020;
} search_ranking_value_020;
typedef int (*search_token_callback_020)(
    struct search_context *, const search_query_020 *, void *);
extern search_status search_token_open_020(
    struct search_context **context, const char *path_020, tool_u32 options_020);
extern search_status search_token_close_020(struct search_context *context);
extern int search_ranking_visit_020(
    struct search_context *context, search_token_callback_020 callback, void *userdata);
extern tool_size search_ranking_count_020(const struct search_context *context);
extern const search_query_020 *search_ranking_find_020(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_020(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_021 {
    SEARCH_QUERY_021_PRIMARY = 1,
    SEARCH_QUERY_021_SECONDARY = 2,
    SEARCH_QUERY_021_ARCHIVED = 4
};
typedef struct search_query_021 {
    tool_u32 id_021;
    tool_u16 revision_021;
    unsigned int flags_021 : 5;
    unsigned int state_021 : 3;
    const char *name_021;
    const tool_byte *payload_021;
    tool_size payload_length_021;
    struct search_query_021 *next_021;
    void *extension_021[3];
} search_query_021;
typedef union search_ranking_value_021 {
    long signed_value_021;
    unsigned long unsigned_value_021;
    double decimal_value_021;
    const void *pointer_value_021;
} search_ranking_value_021;
typedef int (*search_token_callback_021)(
    struct search_context *, const search_query_021 *, void *);
extern search_status search_token_open_021(
    struct search_context **context, const char *path_021, tool_u32 options_021);
extern search_status search_token_close_021(struct search_context *context);
extern int search_ranking_visit_021(
    struct search_context *context, search_token_callback_021 callback, void *userdata);
extern tool_size search_ranking_count_021(const struct search_context *context);
extern const search_query_021 *search_ranking_find_021(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_021(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_022 {
    SEARCH_QUERY_022_PRIMARY = 1,
    SEARCH_QUERY_022_SECONDARY = 2,
    SEARCH_QUERY_022_ARCHIVED = 4
};
typedef struct search_query_022 {
    tool_u32 id_022;
    tool_u16 revision_022;
    unsigned int flags_022 : 5;
    unsigned int state_022 : 3;
    const char *name_022;
    const tool_byte *payload_022;
    tool_size payload_length_022;
    struct search_query_022 *next_022;
    void *extension_022[3];
} search_query_022;
typedef union search_ranking_value_022 {
    long signed_value_022;
    unsigned long unsigned_value_022;
    double decimal_value_022;
    const void *pointer_value_022;
} search_ranking_value_022;
typedef int (*search_token_callback_022)(
    struct search_context *, const search_query_022 *, void *);
extern search_status search_token_open_022(
    struct search_context **context, const char *path_022, tool_u32 options_022);
extern search_status search_token_close_022(struct search_context *context);
extern int search_ranking_visit_022(
    struct search_context *context, search_token_callback_022 callback, void *userdata);
extern tool_size search_ranking_count_022(const struct search_context *context);
extern const search_query_022 *search_ranking_find_022(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_022(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_023 {
    SEARCH_QUERY_023_PRIMARY = 1,
    SEARCH_QUERY_023_SECONDARY = 2,
    SEARCH_QUERY_023_ARCHIVED = 4
};
typedef struct search_query_023 {
    tool_u32 id_023;
    tool_u16 revision_023;
    unsigned int flags_023 : 5;
    unsigned int state_023 : 3;
    const char *name_023;
    const tool_byte *payload_023;
    tool_size payload_length_023;
    struct search_query_023 *next_023;
    void *extension_023[3];
} search_query_023;
typedef union search_ranking_value_023 {
    long signed_value_023;
    unsigned long unsigned_value_023;
    double decimal_value_023;
    const void *pointer_value_023;
} search_ranking_value_023;
typedef int (*search_token_callback_023)(
    struct search_context *, const search_query_023 *, void *);
extern search_status search_token_open_023(
    struct search_context **context, const char *path_023, tool_u32 options_023);
extern search_status search_token_close_023(struct search_context *context);
extern int search_ranking_visit_023(
    struct search_context *context, search_token_callback_023 callback, void *userdata);
extern tool_size search_ranking_count_023(const struct search_context *context);
extern const search_query_023 *search_ranking_find_023(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_023(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_024 {
    SEARCH_QUERY_024_PRIMARY = 1,
    SEARCH_QUERY_024_SECONDARY = 2,
    SEARCH_QUERY_024_ARCHIVED = 4
};
typedef struct search_query_024 {
    tool_u32 id_024;
    tool_u16 revision_024;
    unsigned int flags_024 : 5;
    unsigned int state_024 : 3;
    const char *name_024;
    const tool_byte *payload_024;
    tool_size payload_length_024;
    struct search_query_024 *next_024;
    void *extension_024[3];
} search_query_024;
typedef union search_ranking_value_024 {
    long signed_value_024;
    unsigned long unsigned_value_024;
    double decimal_value_024;
    const void *pointer_value_024;
} search_ranking_value_024;
typedef int (*search_token_callback_024)(
    struct search_context *, const search_query_024 *, void *);
extern search_status search_token_open_024(
    struct search_context **context, const char *path_024, tool_u32 options_024);
extern search_status search_token_close_024(struct search_context *context);
extern int search_ranking_visit_024(
    struct search_context *context, search_token_callback_024 callback, void *userdata);
extern tool_size search_ranking_count_024(const struct search_context *context);
extern const search_query_024 *search_ranking_find_024(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_024(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_025 {
    SEARCH_QUERY_025_PRIMARY = 1,
    SEARCH_QUERY_025_SECONDARY = 2,
    SEARCH_QUERY_025_ARCHIVED = 4
};
typedef struct search_query_025 {
    tool_u32 id_025;
    tool_u16 revision_025;
    unsigned int flags_025 : 5;
    unsigned int state_025 : 3;
    const char *name_025;
    const tool_byte *payload_025;
    tool_size payload_length_025;
    struct search_query_025 *next_025;
    void *extension_025[3];
} search_query_025;
typedef union search_ranking_value_025 {
    long signed_value_025;
    unsigned long unsigned_value_025;
    double decimal_value_025;
    const void *pointer_value_025;
} search_ranking_value_025;
typedef int (*search_token_callback_025)(
    struct search_context *, const search_query_025 *, void *);
extern search_status search_token_open_025(
    struct search_context **context, const char *path_025, tool_u32 options_025);
extern search_status search_token_close_025(struct search_context *context);
extern int search_ranking_visit_025(
    struct search_context *context, search_token_callback_025 callback, void *userdata);
extern tool_size search_ranking_count_025(const struct search_context *context);
extern const search_query_025 *search_ranking_find_025(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_025(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_026 {
    SEARCH_QUERY_026_PRIMARY = 1,
    SEARCH_QUERY_026_SECONDARY = 2,
    SEARCH_QUERY_026_ARCHIVED = 4
};
typedef struct search_query_026 {
    tool_u32 id_026;
    tool_u16 revision_026;
    unsigned int flags_026 : 5;
    unsigned int state_026 : 3;
    const char *name_026;
    const tool_byte *payload_026;
    tool_size payload_length_026;
    struct search_query_026 *next_026;
    void *extension_026[3];
} search_query_026;
typedef union search_ranking_value_026 {
    long signed_value_026;
    unsigned long unsigned_value_026;
    double decimal_value_026;
    const void *pointer_value_026;
} search_ranking_value_026;
typedef int (*search_token_callback_026)(
    struct search_context *, const search_query_026 *, void *);
extern search_status search_token_open_026(
    struct search_context **context, const char *path_026, tool_u32 options_026);
extern search_status search_token_close_026(struct search_context *context);
extern int search_ranking_visit_026(
    struct search_context *context, search_token_callback_026 callback, void *userdata);
extern tool_size search_ranking_count_026(const struct search_context *context);
extern const search_query_026 *search_ranking_find_026(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_026(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_027 {
    SEARCH_QUERY_027_PRIMARY = 1,
    SEARCH_QUERY_027_SECONDARY = 2,
    SEARCH_QUERY_027_ARCHIVED = 4
};
typedef struct search_query_027 {
    tool_u32 id_027;
    tool_u16 revision_027;
    unsigned int flags_027 : 5;
    unsigned int state_027 : 3;
    const char *name_027;
    const tool_byte *payload_027;
    tool_size payload_length_027;
    struct search_query_027 *next_027;
    void *extension_027[3];
} search_query_027;
typedef union search_ranking_value_027 {
    long signed_value_027;
    unsigned long unsigned_value_027;
    double decimal_value_027;
    const void *pointer_value_027;
} search_ranking_value_027;
typedef int (*search_token_callback_027)(
    struct search_context *, const search_query_027 *, void *);
extern search_status search_token_open_027(
    struct search_context **context, const char *path_027, tool_u32 options_027);
extern search_status search_token_close_027(struct search_context *context);
extern int search_ranking_visit_027(
    struct search_context *context, search_token_callback_027 callback, void *userdata);
extern tool_size search_ranking_count_027(const struct search_context *context);
extern const search_query_027 *search_ranking_find_027(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_027(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_028 {
    SEARCH_QUERY_028_PRIMARY = 1,
    SEARCH_QUERY_028_SECONDARY = 2,
    SEARCH_QUERY_028_ARCHIVED = 4
};
typedef struct search_query_028 {
    tool_u32 id_028;
    tool_u16 revision_028;
    unsigned int flags_028 : 5;
    unsigned int state_028 : 3;
    const char *name_028;
    const tool_byte *payload_028;
    tool_size payload_length_028;
    struct search_query_028 *next_028;
    void *extension_028[3];
} search_query_028;
typedef union search_ranking_value_028 {
    long signed_value_028;
    unsigned long unsigned_value_028;
    double decimal_value_028;
    const void *pointer_value_028;
} search_ranking_value_028;
typedef int (*search_token_callback_028)(
    struct search_context *, const search_query_028 *, void *);
extern search_status search_token_open_028(
    struct search_context **context, const char *path_028, tool_u32 options_028);
extern search_status search_token_close_028(struct search_context *context);
extern int search_ranking_visit_028(
    struct search_context *context, search_token_callback_028 callback, void *userdata);
extern tool_size search_ranking_count_028(const struct search_context *context);
extern const search_query_028 *search_ranking_find_028(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_028(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_029 {
    SEARCH_QUERY_029_PRIMARY = 1,
    SEARCH_QUERY_029_SECONDARY = 2,
    SEARCH_QUERY_029_ARCHIVED = 4
};
typedef struct search_query_029 {
    tool_u32 id_029;
    tool_u16 revision_029;
    unsigned int flags_029 : 5;
    unsigned int state_029 : 3;
    const char *name_029;
    const tool_byte *payload_029;
    tool_size payload_length_029;
    struct search_query_029 *next_029;
    void *extension_029[3];
} search_query_029;
typedef union search_ranking_value_029 {
    long signed_value_029;
    unsigned long unsigned_value_029;
    double decimal_value_029;
    const void *pointer_value_029;
} search_ranking_value_029;
typedef int (*search_token_callback_029)(
    struct search_context *, const search_query_029 *, void *);
extern search_status search_token_open_029(
    struct search_context **context, const char *path_029, tool_u32 options_029);
extern search_status search_token_close_029(struct search_context *context);
extern int search_ranking_visit_029(
    struct search_context *context, search_token_callback_029 callback, void *userdata);
extern tool_size search_ranking_count_029(const struct search_context *context);
extern const search_query_029 *search_ranking_find_029(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_029(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_030 {
    SEARCH_QUERY_030_PRIMARY = 1,
    SEARCH_QUERY_030_SECONDARY = 2,
    SEARCH_QUERY_030_ARCHIVED = 4
};
typedef struct search_query_030 {
    tool_u32 id_030;
    tool_u16 revision_030;
    unsigned int flags_030 : 5;
    unsigned int state_030 : 3;
    const char *name_030;
    const tool_byte *payload_030;
    tool_size payload_length_030;
    struct search_query_030 *next_030;
    void *extension_030[3];
} search_query_030;
typedef union search_ranking_value_030 {
    long signed_value_030;
    unsigned long unsigned_value_030;
    double decimal_value_030;
    const void *pointer_value_030;
} search_ranking_value_030;
typedef int (*search_token_callback_030)(
    struct search_context *, const search_query_030 *, void *);
extern search_status search_token_open_030(
    struct search_context **context, const char *path_030, tool_u32 options_030);
extern search_status search_token_close_030(struct search_context *context);
extern int search_ranking_visit_030(
    struct search_context *context, search_token_callback_030 callback, void *userdata);
extern tool_size search_ranking_count_030(const struct search_context *context);
extern const search_query_030 *search_ranking_find_030(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_030(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_031 {
    SEARCH_QUERY_031_PRIMARY = 1,
    SEARCH_QUERY_031_SECONDARY = 2,
    SEARCH_QUERY_031_ARCHIVED = 4
};
typedef struct search_query_031 {
    tool_u32 id_031;
    tool_u16 revision_031;
    unsigned int flags_031 : 5;
    unsigned int state_031 : 3;
    const char *name_031;
    const tool_byte *payload_031;
    tool_size payload_length_031;
    struct search_query_031 *next_031;
    void *extension_031[3];
} search_query_031;
typedef union search_ranking_value_031 {
    long signed_value_031;
    unsigned long unsigned_value_031;
    double decimal_value_031;
    const void *pointer_value_031;
} search_ranking_value_031;
typedef int (*search_token_callback_031)(
    struct search_context *, const search_query_031 *, void *);
extern search_status search_token_open_031(
    struct search_context **context, const char *path_031, tool_u32 options_031);
extern search_status search_token_close_031(struct search_context *context);
extern int search_ranking_visit_031(
    struct search_context *context, search_token_callback_031 callback, void *userdata);
extern tool_size search_ranking_count_031(const struct search_context *context);
extern const search_query_031 *search_ranking_find_031(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_031(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_032 {
    SEARCH_QUERY_032_PRIMARY = 1,
    SEARCH_QUERY_032_SECONDARY = 2,
    SEARCH_QUERY_032_ARCHIVED = 4
};
typedef struct search_query_032 {
    tool_u32 id_032;
    tool_u16 revision_032;
    unsigned int flags_032 : 5;
    unsigned int state_032 : 3;
    const char *name_032;
    const tool_byte *payload_032;
    tool_size payload_length_032;
    struct search_query_032 *next_032;
    void *extension_032[3];
} search_query_032;
typedef union search_ranking_value_032 {
    long signed_value_032;
    unsigned long unsigned_value_032;
    double decimal_value_032;
    const void *pointer_value_032;
} search_ranking_value_032;
typedef int (*search_token_callback_032)(
    struct search_context *, const search_query_032 *, void *);
extern search_status search_token_open_032(
    struct search_context **context, const char *path_032, tool_u32 options_032);
extern search_status search_token_close_032(struct search_context *context);
extern int search_ranking_visit_032(
    struct search_context *context, search_token_callback_032 callback, void *userdata);
extern tool_size search_ranking_count_032(const struct search_context *context);
extern const search_query_032 *search_ranking_find_032(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_032(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_033 {
    SEARCH_QUERY_033_PRIMARY = 1,
    SEARCH_QUERY_033_SECONDARY = 2,
    SEARCH_QUERY_033_ARCHIVED = 4
};
typedef struct search_query_033 {
    tool_u32 id_033;
    tool_u16 revision_033;
    unsigned int flags_033 : 5;
    unsigned int state_033 : 3;
    const char *name_033;
    const tool_byte *payload_033;
    tool_size payload_length_033;
    struct search_query_033 *next_033;
    void *extension_033[3];
} search_query_033;
typedef union search_ranking_value_033 {
    long signed_value_033;
    unsigned long unsigned_value_033;
    double decimal_value_033;
    const void *pointer_value_033;
} search_ranking_value_033;
typedef int (*search_token_callback_033)(
    struct search_context *, const search_query_033 *, void *);
extern search_status search_token_open_033(
    struct search_context **context, const char *path_033, tool_u32 options_033);
extern search_status search_token_close_033(struct search_context *context);
extern int search_ranking_visit_033(
    struct search_context *context, search_token_callback_033 callback, void *userdata);
extern tool_size search_ranking_count_033(const struct search_context *context);
extern const search_query_033 *search_ranking_find_033(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_033(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_034 {
    SEARCH_QUERY_034_PRIMARY = 1,
    SEARCH_QUERY_034_SECONDARY = 2,
    SEARCH_QUERY_034_ARCHIVED = 4
};
typedef struct search_query_034 {
    tool_u32 id_034;
    tool_u16 revision_034;
    unsigned int flags_034 : 5;
    unsigned int state_034 : 3;
    const char *name_034;
    const tool_byte *payload_034;
    tool_size payload_length_034;
    struct search_query_034 *next_034;
    void *extension_034[3];
} search_query_034;
typedef union search_ranking_value_034 {
    long signed_value_034;
    unsigned long unsigned_value_034;
    double decimal_value_034;
    const void *pointer_value_034;
} search_ranking_value_034;
typedef int (*search_token_callback_034)(
    struct search_context *, const search_query_034 *, void *);
extern search_status search_token_open_034(
    struct search_context **context, const char *path_034, tool_u32 options_034);
extern search_status search_token_close_034(struct search_context *context);
extern int search_ranking_visit_034(
    struct search_context *context, search_token_callback_034 callback, void *userdata);
extern tool_size search_ranking_count_034(const struct search_context *context);
extern const search_query_034 *search_ranking_find_034(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_034(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_035 {
    SEARCH_QUERY_035_PRIMARY = 1,
    SEARCH_QUERY_035_SECONDARY = 2,
    SEARCH_QUERY_035_ARCHIVED = 4
};
typedef struct search_query_035 {
    tool_u32 id_035;
    tool_u16 revision_035;
    unsigned int flags_035 : 5;
    unsigned int state_035 : 3;
    const char *name_035;
    const tool_byte *payload_035;
    tool_size payload_length_035;
    struct search_query_035 *next_035;
    void *extension_035[3];
} search_query_035;
typedef union search_ranking_value_035 {
    long signed_value_035;
    unsigned long unsigned_value_035;
    double decimal_value_035;
    const void *pointer_value_035;
} search_ranking_value_035;
typedef int (*search_token_callback_035)(
    struct search_context *, const search_query_035 *, void *);
extern search_status search_token_open_035(
    struct search_context **context, const char *path_035, tool_u32 options_035);
extern search_status search_token_close_035(struct search_context *context);
extern int search_ranking_visit_035(
    struct search_context *context, search_token_callback_035 callback, void *userdata);
extern tool_size search_ranking_count_035(const struct search_context *context);
extern const search_query_035 *search_ranking_find_035(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_035(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_036 {
    SEARCH_QUERY_036_PRIMARY = 1,
    SEARCH_QUERY_036_SECONDARY = 2,
    SEARCH_QUERY_036_ARCHIVED = 4
};
typedef struct search_query_036 {
    tool_u32 id_036;
    tool_u16 revision_036;
    unsigned int flags_036 : 5;
    unsigned int state_036 : 3;
    const char *name_036;
    const tool_byte *payload_036;
    tool_size payload_length_036;
    struct search_query_036 *next_036;
    void *extension_036[3];
} search_query_036;
typedef union search_ranking_value_036 {
    long signed_value_036;
    unsigned long unsigned_value_036;
    double decimal_value_036;
    const void *pointer_value_036;
} search_ranking_value_036;
typedef int (*search_token_callback_036)(
    struct search_context *, const search_query_036 *, void *);
extern search_status search_token_open_036(
    struct search_context **context, const char *path_036, tool_u32 options_036);
extern search_status search_token_close_036(struct search_context *context);
extern int search_ranking_visit_036(
    struct search_context *context, search_token_callback_036 callback, void *userdata);
extern tool_size search_ranking_count_036(const struct search_context *context);
extern const search_query_036 *search_ranking_find_036(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_036(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_037 {
    SEARCH_QUERY_037_PRIMARY = 1,
    SEARCH_QUERY_037_SECONDARY = 2,
    SEARCH_QUERY_037_ARCHIVED = 4
};
typedef struct search_query_037 {
    tool_u32 id_037;
    tool_u16 revision_037;
    unsigned int flags_037 : 5;
    unsigned int state_037 : 3;
    const char *name_037;
    const tool_byte *payload_037;
    tool_size payload_length_037;
    struct search_query_037 *next_037;
    void *extension_037[3];
} search_query_037;
typedef union search_ranking_value_037 {
    long signed_value_037;
    unsigned long unsigned_value_037;
    double decimal_value_037;
    const void *pointer_value_037;
} search_ranking_value_037;
typedef int (*search_token_callback_037)(
    struct search_context *, const search_query_037 *, void *);
extern search_status search_token_open_037(
    struct search_context **context, const char *path_037, tool_u32 options_037);
extern search_status search_token_close_037(struct search_context *context);
extern int search_ranking_visit_037(
    struct search_context *context, search_token_callback_037 callback, void *userdata);
extern tool_size search_ranking_count_037(const struct search_context *context);
extern const search_query_037 *search_ranking_find_037(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_037(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_038 {
    SEARCH_QUERY_038_PRIMARY = 1,
    SEARCH_QUERY_038_SECONDARY = 2,
    SEARCH_QUERY_038_ARCHIVED = 4
};
typedef struct search_query_038 {
    tool_u32 id_038;
    tool_u16 revision_038;
    unsigned int flags_038 : 5;
    unsigned int state_038 : 3;
    const char *name_038;
    const tool_byte *payload_038;
    tool_size payload_length_038;
    struct search_query_038 *next_038;
    void *extension_038[3];
} search_query_038;
typedef union search_ranking_value_038 {
    long signed_value_038;
    unsigned long unsigned_value_038;
    double decimal_value_038;
    const void *pointer_value_038;
} search_ranking_value_038;
typedef int (*search_token_callback_038)(
    struct search_context *, const search_query_038 *, void *);
extern search_status search_token_open_038(
    struct search_context **context, const char *path_038, tool_u32 options_038);
extern search_status search_token_close_038(struct search_context *context);
extern int search_ranking_visit_038(
    struct search_context *context, search_token_callback_038 callback, void *userdata);
extern tool_size search_ranking_count_038(const struct search_context *context);
extern const search_query_038 *search_ranking_find_038(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_038(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_039 {
    SEARCH_QUERY_039_PRIMARY = 1,
    SEARCH_QUERY_039_SECONDARY = 2,
    SEARCH_QUERY_039_ARCHIVED = 4
};
typedef struct search_query_039 {
    tool_u32 id_039;
    tool_u16 revision_039;
    unsigned int flags_039 : 5;
    unsigned int state_039 : 3;
    const char *name_039;
    const tool_byte *payload_039;
    tool_size payload_length_039;
    struct search_query_039 *next_039;
    void *extension_039[3];
} search_query_039;
typedef union search_ranking_value_039 {
    long signed_value_039;
    unsigned long unsigned_value_039;
    double decimal_value_039;
    const void *pointer_value_039;
} search_ranking_value_039;
typedef int (*search_token_callback_039)(
    struct search_context *, const search_query_039 *, void *);
extern search_status search_token_open_039(
    struct search_context **context, const char *path_039, tool_u32 options_039);
extern search_status search_token_close_039(struct search_context *context);
extern int search_ranking_visit_039(
    struct search_context *context, search_token_callback_039 callback, void *userdata);
extern tool_size search_ranking_count_039(const struct search_context *context);
extern const search_query_039 *search_ranking_find_039(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_039(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_040 {
    SEARCH_QUERY_040_PRIMARY = 1,
    SEARCH_QUERY_040_SECONDARY = 2,
    SEARCH_QUERY_040_ARCHIVED = 4
};
typedef struct search_query_040 {
    tool_u32 id_040;
    tool_u16 revision_040;
    unsigned int flags_040 : 5;
    unsigned int state_040 : 3;
    const char *name_040;
    const tool_byte *payload_040;
    tool_size payload_length_040;
    struct search_query_040 *next_040;
    void *extension_040[3];
} search_query_040;
typedef union search_ranking_value_040 {
    long signed_value_040;
    unsigned long unsigned_value_040;
    double decimal_value_040;
    const void *pointer_value_040;
} search_ranking_value_040;
typedef int (*search_token_callback_040)(
    struct search_context *, const search_query_040 *, void *);
extern search_status search_token_open_040(
    struct search_context **context, const char *path_040, tool_u32 options_040);
extern search_status search_token_close_040(struct search_context *context);
extern int search_ranking_visit_040(
    struct search_context *context, search_token_callback_040 callback, void *userdata);
extern tool_size search_ranking_count_040(const struct search_context *context);
extern const search_query_040 *search_ranking_find_040(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_040(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_041 {
    SEARCH_QUERY_041_PRIMARY = 1,
    SEARCH_QUERY_041_SECONDARY = 2,
    SEARCH_QUERY_041_ARCHIVED = 4
};
typedef struct search_query_041 {
    tool_u32 id_041;
    tool_u16 revision_041;
    unsigned int flags_041 : 5;
    unsigned int state_041 : 3;
    const char *name_041;
    const tool_byte *payload_041;
    tool_size payload_length_041;
    struct search_query_041 *next_041;
    void *extension_041[3];
} search_query_041;
typedef union search_ranking_value_041 {
    long signed_value_041;
    unsigned long unsigned_value_041;
    double decimal_value_041;
    const void *pointer_value_041;
} search_ranking_value_041;
typedef int (*search_token_callback_041)(
    struct search_context *, const search_query_041 *, void *);
extern search_status search_token_open_041(
    struct search_context **context, const char *path_041, tool_u32 options_041);
extern search_status search_token_close_041(struct search_context *context);
extern int search_ranking_visit_041(
    struct search_context *context, search_token_callback_041 callback, void *userdata);
extern tool_size search_ranking_count_041(const struct search_context *context);
extern const search_query_041 *search_ranking_find_041(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_041(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_042 {
    SEARCH_QUERY_042_PRIMARY = 1,
    SEARCH_QUERY_042_SECONDARY = 2,
    SEARCH_QUERY_042_ARCHIVED = 4
};
typedef struct search_query_042 {
    tool_u32 id_042;
    tool_u16 revision_042;
    unsigned int flags_042 : 5;
    unsigned int state_042 : 3;
    const char *name_042;
    const tool_byte *payload_042;
    tool_size payload_length_042;
    struct search_query_042 *next_042;
    void *extension_042[3];
} search_query_042;
typedef union search_ranking_value_042 {
    long signed_value_042;
    unsigned long unsigned_value_042;
    double decimal_value_042;
    const void *pointer_value_042;
} search_ranking_value_042;
typedef int (*search_token_callback_042)(
    struct search_context *, const search_query_042 *, void *);
extern search_status search_token_open_042(
    struct search_context **context, const char *path_042, tool_u32 options_042);
extern search_status search_token_close_042(struct search_context *context);
extern int search_ranking_visit_042(
    struct search_context *context, search_token_callback_042 callback, void *userdata);
extern tool_size search_ranking_count_042(const struct search_context *context);
extern const search_query_042 *search_ranking_find_042(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_042(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_043 {
    SEARCH_QUERY_043_PRIMARY = 1,
    SEARCH_QUERY_043_SECONDARY = 2,
    SEARCH_QUERY_043_ARCHIVED = 4
};
typedef struct search_query_043 {
    tool_u32 id_043;
    tool_u16 revision_043;
    unsigned int flags_043 : 5;
    unsigned int state_043 : 3;
    const char *name_043;
    const tool_byte *payload_043;
    tool_size payload_length_043;
    struct search_query_043 *next_043;
    void *extension_043[3];
} search_query_043;
typedef union search_ranking_value_043 {
    long signed_value_043;
    unsigned long unsigned_value_043;
    double decimal_value_043;
    const void *pointer_value_043;
} search_ranking_value_043;
typedef int (*search_token_callback_043)(
    struct search_context *, const search_query_043 *, void *);
extern search_status search_token_open_043(
    struct search_context **context, const char *path_043, tool_u32 options_043);
extern search_status search_token_close_043(struct search_context *context);
extern int search_ranking_visit_043(
    struct search_context *context, search_token_callback_043 callback, void *userdata);
extern tool_size search_ranking_count_043(const struct search_context *context);
extern const search_query_043 *search_ranking_find_043(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_043(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_044 {
    SEARCH_QUERY_044_PRIMARY = 1,
    SEARCH_QUERY_044_SECONDARY = 2,
    SEARCH_QUERY_044_ARCHIVED = 4
};
typedef struct search_query_044 {
    tool_u32 id_044;
    tool_u16 revision_044;
    unsigned int flags_044 : 5;
    unsigned int state_044 : 3;
    const char *name_044;
    const tool_byte *payload_044;
    tool_size payload_length_044;
    struct search_query_044 *next_044;
    void *extension_044[3];
} search_query_044;
typedef union search_ranking_value_044 {
    long signed_value_044;
    unsigned long unsigned_value_044;
    double decimal_value_044;
    const void *pointer_value_044;
} search_ranking_value_044;
typedef int (*search_token_callback_044)(
    struct search_context *, const search_query_044 *, void *);
extern search_status search_token_open_044(
    struct search_context **context, const char *path_044, tool_u32 options_044);
extern search_status search_token_close_044(struct search_context *context);
extern int search_ranking_visit_044(
    struct search_context *context, search_token_callback_044 callback, void *userdata);
extern tool_size search_ranking_count_044(const struct search_context *context);
extern const search_query_044 *search_ranking_find_044(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_044(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_045 {
    SEARCH_QUERY_045_PRIMARY = 1,
    SEARCH_QUERY_045_SECONDARY = 2,
    SEARCH_QUERY_045_ARCHIVED = 4
};
typedef struct search_query_045 {
    tool_u32 id_045;
    tool_u16 revision_045;
    unsigned int flags_045 : 5;
    unsigned int state_045 : 3;
    const char *name_045;
    const tool_byte *payload_045;
    tool_size payload_length_045;
    struct search_query_045 *next_045;
    void *extension_045[3];
} search_query_045;
typedef union search_ranking_value_045 {
    long signed_value_045;
    unsigned long unsigned_value_045;
    double decimal_value_045;
    const void *pointer_value_045;
} search_ranking_value_045;
typedef int (*search_token_callback_045)(
    struct search_context *, const search_query_045 *, void *);
extern search_status search_token_open_045(
    struct search_context **context, const char *path_045, tool_u32 options_045);
extern search_status search_token_close_045(struct search_context *context);
extern int search_ranking_visit_045(
    struct search_context *context, search_token_callback_045 callback, void *userdata);
extern tool_size search_ranking_count_045(const struct search_context *context);
extern const search_query_045 *search_ranking_find_045(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_045(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_046 {
    SEARCH_QUERY_046_PRIMARY = 1,
    SEARCH_QUERY_046_SECONDARY = 2,
    SEARCH_QUERY_046_ARCHIVED = 4
};
typedef struct search_query_046 {
    tool_u32 id_046;
    tool_u16 revision_046;
    unsigned int flags_046 : 5;
    unsigned int state_046 : 3;
    const char *name_046;
    const tool_byte *payload_046;
    tool_size payload_length_046;
    struct search_query_046 *next_046;
    void *extension_046[3];
} search_query_046;
typedef union search_ranking_value_046 {
    long signed_value_046;
    unsigned long unsigned_value_046;
    double decimal_value_046;
    const void *pointer_value_046;
} search_ranking_value_046;
typedef int (*search_token_callback_046)(
    struct search_context *, const search_query_046 *, void *);
extern search_status search_token_open_046(
    struct search_context **context, const char *path_046, tool_u32 options_046);
extern search_status search_token_close_046(struct search_context *context);
extern int search_ranking_visit_046(
    struct search_context *context, search_token_callback_046 callback, void *userdata);
extern tool_size search_ranking_count_046(const struct search_context *context);
extern const search_query_046 *search_ranking_find_046(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_046(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_047 {
    SEARCH_QUERY_047_PRIMARY = 1,
    SEARCH_QUERY_047_SECONDARY = 2,
    SEARCH_QUERY_047_ARCHIVED = 4
};
typedef struct search_query_047 {
    tool_u32 id_047;
    tool_u16 revision_047;
    unsigned int flags_047 : 5;
    unsigned int state_047 : 3;
    const char *name_047;
    const tool_byte *payload_047;
    tool_size payload_length_047;
    struct search_query_047 *next_047;
    void *extension_047[3];
} search_query_047;
typedef union search_ranking_value_047 {
    long signed_value_047;
    unsigned long unsigned_value_047;
    double decimal_value_047;
    const void *pointer_value_047;
} search_ranking_value_047;
typedef int (*search_token_callback_047)(
    struct search_context *, const search_query_047 *, void *);
extern search_status search_token_open_047(
    struct search_context **context, const char *path_047, tool_u32 options_047);
extern search_status search_token_close_047(struct search_context *context);
extern int search_ranking_visit_047(
    struct search_context *context, search_token_callback_047 callback, void *userdata);
extern tool_size search_ranking_count_047(const struct search_context *context);
extern const search_query_047 *search_ranking_find_047(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_047(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_048 {
    SEARCH_QUERY_048_PRIMARY = 1,
    SEARCH_QUERY_048_SECONDARY = 2,
    SEARCH_QUERY_048_ARCHIVED = 4
};
typedef struct search_query_048 {
    tool_u32 id_048;
    tool_u16 revision_048;
    unsigned int flags_048 : 5;
    unsigned int state_048 : 3;
    const char *name_048;
    const tool_byte *payload_048;
    tool_size payload_length_048;
    struct search_query_048 *next_048;
    void *extension_048[3];
} search_query_048;
typedef union search_ranking_value_048 {
    long signed_value_048;
    unsigned long unsigned_value_048;
    double decimal_value_048;
    const void *pointer_value_048;
} search_ranking_value_048;
typedef int (*search_token_callback_048)(
    struct search_context *, const search_query_048 *, void *);
extern search_status search_token_open_048(
    struct search_context **context, const char *path_048, tool_u32 options_048);
extern search_status search_token_close_048(struct search_context *context);
extern int search_ranking_visit_048(
    struct search_context *context, search_token_callback_048 callback, void *userdata);
extern tool_size search_ranking_count_048(const struct search_context *context);
extern const search_query_048 *search_ranking_find_048(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_048(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_049 {
    SEARCH_QUERY_049_PRIMARY = 1,
    SEARCH_QUERY_049_SECONDARY = 2,
    SEARCH_QUERY_049_ARCHIVED = 4
};
typedef struct search_query_049 {
    tool_u32 id_049;
    tool_u16 revision_049;
    unsigned int flags_049 : 5;
    unsigned int state_049 : 3;
    const char *name_049;
    const tool_byte *payload_049;
    tool_size payload_length_049;
    struct search_query_049 *next_049;
    void *extension_049[3];
} search_query_049;
typedef union search_ranking_value_049 {
    long signed_value_049;
    unsigned long unsigned_value_049;
    double decimal_value_049;
    const void *pointer_value_049;
} search_ranking_value_049;
typedef int (*search_token_callback_049)(
    struct search_context *, const search_query_049 *, void *);
extern search_status search_token_open_049(
    struct search_context **context, const char *path_049, tool_u32 options_049);
extern search_status search_token_close_049(struct search_context *context);
extern int search_ranking_visit_049(
    struct search_context *context, search_token_callback_049 callback, void *userdata);
extern tool_size search_ranking_count_049(const struct search_context *context);
extern const search_query_049 *search_ranking_find_049(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_049(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_050 {
    SEARCH_QUERY_050_PRIMARY = 1,
    SEARCH_QUERY_050_SECONDARY = 2,
    SEARCH_QUERY_050_ARCHIVED = 4
};
typedef struct search_query_050 {
    tool_u32 id_050;
    tool_u16 revision_050;
    unsigned int flags_050 : 5;
    unsigned int state_050 : 3;
    const char *name_050;
    const tool_byte *payload_050;
    tool_size payload_length_050;
    struct search_query_050 *next_050;
    void *extension_050[3];
} search_query_050;
typedef union search_ranking_value_050 {
    long signed_value_050;
    unsigned long unsigned_value_050;
    double decimal_value_050;
    const void *pointer_value_050;
} search_ranking_value_050;
typedef int (*search_token_callback_050)(
    struct search_context *, const search_query_050 *, void *);
extern search_status search_token_open_050(
    struct search_context **context, const char *path_050, tool_u32 options_050);
extern search_status search_token_close_050(struct search_context *context);
extern int search_ranking_visit_050(
    struct search_context *context, search_token_callback_050 callback, void *userdata);
extern tool_size search_ranking_count_050(const struct search_context *context);
extern const search_query_050 *search_ranking_find_050(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_050(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_051 {
    SEARCH_QUERY_051_PRIMARY = 1,
    SEARCH_QUERY_051_SECONDARY = 2,
    SEARCH_QUERY_051_ARCHIVED = 4
};
typedef struct search_query_051 {
    tool_u32 id_051;
    tool_u16 revision_051;
    unsigned int flags_051 : 5;
    unsigned int state_051 : 3;
    const char *name_051;
    const tool_byte *payload_051;
    tool_size payload_length_051;
    struct search_query_051 *next_051;
    void *extension_051[3];
} search_query_051;
typedef union search_ranking_value_051 {
    long signed_value_051;
    unsigned long unsigned_value_051;
    double decimal_value_051;
    const void *pointer_value_051;
} search_ranking_value_051;
typedef int (*search_token_callback_051)(
    struct search_context *, const search_query_051 *, void *);
extern search_status search_token_open_051(
    struct search_context **context, const char *path_051, tool_u32 options_051);
extern search_status search_token_close_051(struct search_context *context);
extern int search_ranking_visit_051(
    struct search_context *context, search_token_callback_051 callback, void *userdata);
extern tool_size search_ranking_count_051(const struct search_context *context);
extern const search_query_051 *search_ranking_find_051(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_051(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_052 {
    SEARCH_QUERY_052_PRIMARY = 1,
    SEARCH_QUERY_052_SECONDARY = 2,
    SEARCH_QUERY_052_ARCHIVED = 4
};
typedef struct search_query_052 {
    tool_u32 id_052;
    tool_u16 revision_052;
    unsigned int flags_052 : 5;
    unsigned int state_052 : 3;
    const char *name_052;
    const tool_byte *payload_052;
    tool_size payload_length_052;
    struct search_query_052 *next_052;
    void *extension_052[3];
} search_query_052;
typedef union search_ranking_value_052 {
    long signed_value_052;
    unsigned long unsigned_value_052;
    double decimal_value_052;
    const void *pointer_value_052;
} search_ranking_value_052;
typedef int (*search_token_callback_052)(
    struct search_context *, const search_query_052 *, void *);
extern search_status search_token_open_052(
    struct search_context **context, const char *path_052, tool_u32 options_052);
extern search_status search_token_close_052(struct search_context *context);
extern int search_ranking_visit_052(
    struct search_context *context, search_token_callback_052 callback, void *userdata);
extern tool_size search_ranking_count_052(const struct search_context *context);
extern const search_query_052 *search_ranking_find_052(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_052(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_053 {
    SEARCH_QUERY_053_PRIMARY = 1,
    SEARCH_QUERY_053_SECONDARY = 2,
    SEARCH_QUERY_053_ARCHIVED = 4
};
typedef struct search_query_053 {
    tool_u32 id_053;
    tool_u16 revision_053;
    unsigned int flags_053 : 5;
    unsigned int state_053 : 3;
    const char *name_053;
    const tool_byte *payload_053;
    tool_size payload_length_053;
    struct search_query_053 *next_053;
    void *extension_053[3];
} search_query_053;
typedef union search_ranking_value_053 {
    long signed_value_053;
    unsigned long unsigned_value_053;
    double decimal_value_053;
    const void *pointer_value_053;
} search_ranking_value_053;
typedef int (*search_token_callback_053)(
    struct search_context *, const search_query_053 *, void *);
extern search_status search_token_open_053(
    struct search_context **context, const char *path_053, tool_u32 options_053);
extern search_status search_token_close_053(struct search_context *context);
extern int search_ranking_visit_053(
    struct search_context *context, search_token_callback_053 callback, void *userdata);
extern tool_size search_ranking_count_053(const struct search_context *context);
extern const search_query_053 *search_ranking_find_053(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_053(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_054 {
    SEARCH_QUERY_054_PRIMARY = 1,
    SEARCH_QUERY_054_SECONDARY = 2,
    SEARCH_QUERY_054_ARCHIVED = 4
};
typedef struct search_query_054 {
    tool_u32 id_054;
    tool_u16 revision_054;
    unsigned int flags_054 : 5;
    unsigned int state_054 : 3;
    const char *name_054;
    const tool_byte *payload_054;
    tool_size payload_length_054;
    struct search_query_054 *next_054;
    void *extension_054[3];
} search_query_054;
typedef union search_ranking_value_054 {
    long signed_value_054;
    unsigned long unsigned_value_054;
    double decimal_value_054;
    const void *pointer_value_054;
} search_ranking_value_054;
typedef int (*search_token_callback_054)(
    struct search_context *, const search_query_054 *, void *);
extern search_status search_token_open_054(
    struct search_context **context, const char *path_054, tool_u32 options_054);
extern search_status search_token_close_054(struct search_context *context);
extern int search_ranking_visit_054(
    struct search_context *context, search_token_callback_054 callback, void *userdata);
extern tool_size search_ranking_count_054(const struct search_context *context);
extern const search_query_054 *search_ranking_find_054(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_054(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_055 {
    SEARCH_QUERY_055_PRIMARY = 1,
    SEARCH_QUERY_055_SECONDARY = 2,
    SEARCH_QUERY_055_ARCHIVED = 4
};
typedef struct search_query_055 {
    tool_u32 id_055;
    tool_u16 revision_055;
    unsigned int flags_055 : 5;
    unsigned int state_055 : 3;
    const char *name_055;
    const tool_byte *payload_055;
    tool_size payload_length_055;
    struct search_query_055 *next_055;
    void *extension_055[3];
} search_query_055;
typedef union search_ranking_value_055 {
    long signed_value_055;
    unsigned long unsigned_value_055;
    double decimal_value_055;
    const void *pointer_value_055;
} search_ranking_value_055;
typedef int (*search_token_callback_055)(
    struct search_context *, const search_query_055 *, void *);
extern search_status search_token_open_055(
    struct search_context **context, const char *path_055, tool_u32 options_055);
extern search_status search_token_close_055(struct search_context *context);
extern int search_ranking_visit_055(
    struct search_context *context, search_token_callback_055 callback, void *userdata);
extern tool_size search_ranking_count_055(const struct search_context *context);
extern const search_query_055 *search_ranking_find_055(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_055(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_056 {
    SEARCH_QUERY_056_PRIMARY = 1,
    SEARCH_QUERY_056_SECONDARY = 2,
    SEARCH_QUERY_056_ARCHIVED = 4
};
typedef struct search_query_056 {
    tool_u32 id_056;
    tool_u16 revision_056;
    unsigned int flags_056 : 5;
    unsigned int state_056 : 3;
    const char *name_056;
    const tool_byte *payload_056;
    tool_size payload_length_056;
    struct search_query_056 *next_056;
    void *extension_056[3];
} search_query_056;
typedef union search_ranking_value_056 {
    long signed_value_056;
    unsigned long unsigned_value_056;
    double decimal_value_056;
    const void *pointer_value_056;
} search_ranking_value_056;
typedef int (*search_token_callback_056)(
    struct search_context *, const search_query_056 *, void *);
extern search_status search_token_open_056(
    struct search_context **context, const char *path_056, tool_u32 options_056);
extern search_status search_token_close_056(struct search_context *context);
extern int search_ranking_visit_056(
    struct search_context *context, search_token_callback_056 callback, void *userdata);
extern tool_size search_ranking_count_056(const struct search_context *context);
extern const search_query_056 *search_ranking_find_056(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_056(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_057 {
    SEARCH_QUERY_057_PRIMARY = 1,
    SEARCH_QUERY_057_SECONDARY = 2,
    SEARCH_QUERY_057_ARCHIVED = 4
};
typedef struct search_query_057 {
    tool_u32 id_057;
    tool_u16 revision_057;
    unsigned int flags_057 : 5;
    unsigned int state_057 : 3;
    const char *name_057;
    const tool_byte *payload_057;
    tool_size payload_length_057;
    struct search_query_057 *next_057;
    void *extension_057[3];
} search_query_057;
typedef union search_ranking_value_057 {
    long signed_value_057;
    unsigned long unsigned_value_057;
    double decimal_value_057;
    const void *pointer_value_057;
} search_ranking_value_057;
typedef int (*search_token_callback_057)(
    struct search_context *, const search_query_057 *, void *);
extern search_status search_token_open_057(
    struct search_context **context, const char *path_057, tool_u32 options_057);
extern search_status search_token_close_057(struct search_context *context);
extern int search_ranking_visit_057(
    struct search_context *context, search_token_callback_057 callback, void *userdata);
extern tool_size search_ranking_count_057(const struct search_context *context);
extern const search_query_057 *search_ranking_find_057(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_057(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_058 {
    SEARCH_QUERY_058_PRIMARY = 1,
    SEARCH_QUERY_058_SECONDARY = 2,
    SEARCH_QUERY_058_ARCHIVED = 4
};
typedef struct search_query_058 {
    tool_u32 id_058;
    tool_u16 revision_058;
    unsigned int flags_058 : 5;
    unsigned int state_058 : 3;
    const char *name_058;
    const tool_byte *payload_058;
    tool_size payload_length_058;
    struct search_query_058 *next_058;
    void *extension_058[3];
} search_query_058;
typedef union search_ranking_value_058 {
    long signed_value_058;
    unsigned long unsigned_value_058;
    double decimal_value_058;
    const void *pointer_value_058;
} search_ranking_value_058;
typedef int (*search_token_callback_058)(
    struct search_context *, const search_query_058 *, void *);
extern search_status search_token_open_058(
    struct search_context **context, const char *path_058, tool_u32 options_058);
extern search_status search_token_close_058(struct search_context *context);
extern int search_ranking_visit_058(
    struct search_context *context, search_token_callback_058 callback, void *userdata);
extern tool_size search_ranking_count_058(const struct search_context *context);
extern const search_query_058 *search_ranking_find_058(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_058(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_059 {
    SEARCH_QUERY_059_PRIMARY = 1,
    SEARCH_QUERY_059_SECONDARY = 2,
    SEARCH_QUERY_059_ARCHIVED = 4
};
typedef struct search_query_059 {
    tool_u32 id_059;
    tool_u16 revision_059;
    unsigned int flags_059 : 5;
    unsigned int state_059 : 3;
    const char *name_059;
    const tool_byte *payload_059;
    tool_size payload_length_059;
    struct search_query_059 *next_059;
    void *extension_059[3];
} search_query_059;
typedef union search_ranking_value_059 {
    long signed_value_059;
    unsigned long unsigned_value_059;
    double decimal_value_059;
    const void *pointer_value_059;
} search_ranking_value_059;
typedef int (*search_token_callback_059)(
    struct search_context *, const search_query_059 *, void *);
extern search_status search_token_open_059(
    struct search_context **context, const char *path_059, tool_u32 options_059);
extern search_status search_token_close_059(struct search_context *context);
extern int search_ranking_visit_059(
    struct search_context *context, search_token_callback_059 callback, void *userdata);
extern tool_size search_ranking_count_059(const struct search_context *context);
extern const search_query_059 *search_ranking_find_059(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_059(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_060 {
    SEARCH_QUERY_060_PRIMARY = 1,
    SEARCH_QUERY_060_SECONDARY = 2,
    SEARCH_QUERY_060_ARCHIVED = 4
};
typedef struct search_query_060 {
    tool_u32 id_060;
    tool_u16 revision_060;
    unsigned int flags_060 : 5;
    unsigned int state_060 : 3;
    const char *name_060;
    const tool_byte *payload_060;
    tool_size payload_length_060;
    struct search_query_060 *next_060;
    void *extension_060[3];
} search_query_060;
typedef union search_ranking_value_060 {
    long signed_value_060;
    unsigned long unsigned_value_060;
    double decimal_value_060;
    const void *pointer_value_060;
} search_ranking_value_060;
typedef int (*search_token_callback_060)(
    struct search_context *, const search_query_060 *, void *);
extern search_status search_token_open_060(
    struct search_context **context, const char *path_060, tool_u32 options_060);
extern search_status search_token_close_060(struct search_context *context);
extern int search_ranking_visit_060(
    struct search_context *context, search_token_callback_060 callback, void *userdata);
extern tool_size search_ranking_count_060(const struct search_context *context);
extern const search_query_060 *search_ranking_find_060(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_060(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_061 {
    SEARCH_QUERY_061_PRIMARY = 1,
    SEARCH_QUERY_061_SECONDARY = 2,
    SEARCH_QUERY_061_ARCHIVED = 4
};
typedef struct search_query_061 {
    tool_u32 id_061;
    tool_u16 revision_061;
    unsigned int flags_061 : 5;
    unsigned int state_061 : 3;
    const char *name_061;
    const tool_byte *payload_061;
    tool_size payload_length_061;
    struct search_query_061 *next_061;
    void *extension_061[3];
} search_query_061;
typedef union search_ranking_value_061 {
    long signed_value_061;
    unsigned long unsigned_value_061;
    double decimal_value_061;
    const void *pointer_value_061;
} search_ranking_value_061;
typedef int (*search_token_callback_061)(
    struct search_context *, const search_query_061 *, void *);
extern search_status search_token_open_061(
    struct search_context **context, const char *path_061, tool_u32 options_061);
extern search_status search_token_close_061(struct search_context *context);
extern int search_ranking_visit_061(
    struct search_context *context, search_token_callback_061 callback, void *userdata);
extern tool_size search_ranking_count_061(const struct search_context *context);
extern const search_query_061 *search_ranking_find_061(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_061(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_062 {
    SEARCH_QUERY_062_PRIMARY = 1,
    SEARCH_QUERY_062_SECONDARY = 2,
    SEARCH_QUERY_062_ARCHIVED = 4
};
typedef struct search_query_062 {
    tool_u32 id_062;
    tool_u16 revision_062;
    unsigned int flags_062 : 5;
    unsigned int state_062 : 3;
    const char *name_062;
    const tool_byte *payload_062;
    tool_size payload_length_062;
    struct search_query_062 *next_062;
    void *extension_062[3];
} search_query_062;
typedef union search_ranking_value_062 {
    long signed_value_062;
    unsigned long unsigned_value_062;
    double decimal_value_062;
    const void *pointer_value_062;
} search_ranking_value_062;
typedef int (*search_token_callback_062)(
    struct search_context *, const search_query_062 *, void *);
extern search_status search_token_open_062(
    struct search_context **context, const char *path_062, tool_u32 options_062);
extern search_status search_token_close_062(struct search_context *context);
extern int search_ranking_visit_062(
    struct search_context *context, search_token_callback_062 callback, void *userdata);
extern tool_size search_ranking_count_062(const struct search_context *context);
extern const search_query_062 *search_ranking_find_062(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_062(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_063 {
    SEARCH_QUERY_063_PRIMARY = 1,
    SEARCH_QUERY_063_SECONDARY = 2,
    SEARCH_QUERY_063_ARCHIVED = 4
};
typedef struct search_query_063 {
    tool_u32 id_063;
    tool_u16 revision_063;
    unsigned int flags_063 : 5;
    unsigned int state_063 : 3;
    const char *name_063;
    const tool_byte *payload_063;
    tool_size payload_length_063;
    struct search_query_063 *next_063;
    void *extension_063[3];
} search_query_063;
typedef union search_ranking_value_063 {
    long signed_value_063;
    unsigned long unsigned_value_063;
    double decimal_value_063;
    const void *pointer_value_063;
} search_ranking_value_063;
typedef int (*search_token_callback_063)(
    struct search_context *, const search_query_063 *, void *);
extern search_status search_token_open_063(
    struct search_context **context, const char *path_063, tool_u32 options_063);
extern search_status search_token_close_063(struct search_context *context);
extern int search_ranking_visit_063(
    struct search_context *context, search_token_callback_063 callback, void *userdata);
extern tool_size search_ranking_count_063(const struct search_context *context);
extern const search_query_063 *search_ranking_find_063(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_063(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_064 {
    SEARCH_QUERY_064_PRIMARY = 1,
    SEARCH_QUERY_064_SECONDARY = 2,
    SEARCH_QUERY_064_ARCHIVED = 4
};
typedef struct search_query_064 {
    tool_u32 id_064;
    tool_u16 revision_064;
    unsigned int flags_064 : 5;
    unsigned int state_064 : 3;
    const char *name_064;
    const tool_byte *payload_064;
    tool_size payload_length_064;
    struct search_query_064 *next_064;
    void *extension_064[3];
} search_query_064;
typedef union search_ranking_value_064 {
    long signed_value_064;
    unsigned long unsigned_value_064;
    double decimal_value_064;
    const void *pointer_value_064;
} search_ranking_value_064;
typedef int (*search_token_callback_064)(
    struct search_context *, const search_query_064 *, void *);
extern search_status search_token_open_064(
    struct search_context **context, const char *path_064, tool_u32 options_064);
extern search_status search_token_close_064(struct search_context *context);
extern int search_ranking_visit_064(
    struct search_context *context, search_token_callback_064 callback, void *userdata);
extern tool_size search_ranking_count_064(const struct search_context *context);
extern const search_query_064 *search_ranking_find_064(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_064(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_065 {
    SEARCH_QUERY_065_PRIMARY = 1,
    SEARCH_QUERY_065_SECONDARY = 2,
    SEARCH_QUERY_065_ARCHIVED = 4
};
typedef struct search_query_065 {
    tool_u32 id_065;
    tool_u16 revision_065;
    unsigned int flags_065 : 5;
    unsigned int state_065 : 3;
    const char *name_065;
    const tool_byte *payload_065;
    tool_size payload_length_065;
    struct search_query_065 *next_065;
    void *extension_065[3];
} search_query_065;
typedef union search_ranking_value_065 {
    long signed_value_065;
    unsigned long unsigned_value_065;
    double decimal_value_065;
    const void *pointer_value_065;
} search_ranking_value_065;
typedef int (*search_token_callback_065)(
    struct search_context *, const search_query_065 *, void *);
extern search_status search_token_open_065(
    struct search_context **context, const char *path_065, tool_u32 options_065);
extern search_status search_token_close_065(struct search_context *context);
extern int search_ranking_visit_065(
    struct search_context *context, search_token_callback_065 callback, void *userdata);
extern tool_size search_ranking_count_065(const struct search_context *context);
extern const search_query_065 *search_ranking_find_065(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_065(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_066 {
    SEARCH_QUERY_066_PRIMARY = 1,
    SEARCH_QUERY_066_SECONDARY = 2,
    SEARCH_QUERY_066_ARCHIVED = 4
};
typedef struct search_query_066 {
    tool_u32 id_066;
    tool_u16 revision_066;
    unsigned int flags_066 : 5;
    unsigned int state_066 : 3;
    const char *name_066;
    const tool_byte *payload_066;
    tool_size payload_length_066;
    struct search_query_066 *next_066;
    void *extension_066[3];
} search_query_066;
typedef union search_ranking_value_066 {
    long signed_value_066;
    unsigned long unsigned_value_066;
    double decimal_value_066;
    const void *pointer_value_066;
} search_ranking_value_066;
typedef int (*search_token_callback_066)(
    struct search_context *, const search_query_066 *, void *);
extern search_status search_token_open_066(
    struct search_context **context, const char *path_066, tool_u32 options_066);
extern search_status search_token_close_066(struct search_context *context);
extern int search_ranking_visit_066(
    struct search_context *context, search_token_callback_066 callback, void *userdata);
extern tool_size search_ranking_count_066(const struct search_context *context);
extern const search_query_066 *search_ranking_find_066(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_066(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_067 {
    SEARCH_QUERY_067_PRIMARY = 1,
    SEARCH_QUERY_067_SECONDARY = 2,
    SEARCH_QUERY_067_ARCHIVED = 4
};
typedef struct search_query_067 {
    tool_u32 id_067;
    tool_u16 revision_067;
    unsigned int flags_067 : 5;
    unsigned int state_067 : 3;
    const char *name_067;
    const tool_byte *payload_067;
    tool_size payload_length_067;
    struct search_query_067 *next_067;
    void *extension_067[3];
} search_query_067;
typedef union search_ranking_value_067 {
    long signed_value_067;
    unsigned long unsigned_value_067;
    double decimal_value_067;
    const void *pointer_value_067;
} search_ranking_value_067;
typedef int (*search_token_callback_067)(
    struct search_context *, const search_query_067 *, void *);
extern search_status search_token_open_067(
    struct search_context **context, const char *path_067, tool_u32 options_067);
extern search_status search_token_close_067(struct search_context *context);
extern int search_ranking_visit_067(
    struct search_context *context, search_token_callback_067 callback, void *userdata);
extern tool_size search_ranking_count_067(const struct search_context *context);
extern const search_query_067 *search_ranking_find_067(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_067(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_068 {
    SEARCH_QUERY_068_PRIMARY = 1,
    SEARCH_QUERY_068_SECONDARY = 2,
    SEARCH_QUERY_068_ARCHIVED = 4
};
typedef struct search_query_068 {
    tool_u32 id_068;
    tool_u16 revision_068;
    unsigned int flags_068 : 5;
    unsigned int state_068 : 3;
    const char *name_068;
    const tool_byte *payload_068;
    tool_size payload_length_068;
    struct search_query_068 *next_068;
    void *extension_068[3];
} search_query_068;
typedef union search_ranking_value_068 {
    long signed_value_068;
    unsigned long unsigned_value_068;
    double decimal_value_068;
    const void *pointer_value_068;
} search_ranking_value_068;
typedef int (*search_token_callback_068)(
    struct search_context *, const search_query_068 *, void *);
extern search_status search_token_open_068(
    struct search_context **context, const char *path_068, tool_u32 options_068);
extern search_status search_token_close_068(struct search_context *context);
extern int search_ranking_visit_068(
    struct search_context *context, search_token_callback_068 callback, void *userdata);
extern tool_size search_ranking_count_068(const struct search_context *context);
extern const search_query_068 *search_ranking_find_068(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_068(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_069 {
    SEARCH_QUERY_069_PRIMARY = 1,
    SEARCH_QUERY_069_SECONDARY = 2,
    SEARCH_QUERY_069_ARCHIVED = 4
};
typedef struct search_query_069 {
    tool_u32 id_069;
    tool_u16 revision_069;
    unsigned int flags_069 : 5;
    unsigned int state_069 : 3;
    const char *name_069;
    const tool_byte *payload_069;
    tool_size payload_length_069;
    struct search_query_069 *next_069;
    void *extension_069[3];
} search_query_069;
typedef union search_ranking_value_069 {
    long signed_value_069;
    unsigned long unsigned_value_069;
    double decimal_value_069;
    const void *pointer_value_069;
} search_ranking_value_069;
typedef int (*search_token_callback_069)(
    struct search_context *, const search_query_069 *, void *);
extern search_status search_token_open_069(
    struct search_context **context, const char *path_069, tool_u32 options_069);
extern search_status search_token_close_069(struct search_context *context);
extern int search_ranking_visit_069(
    struct search_context *context, search_token_callback_069 callback, void *userdata);
extern tool_size search_ranking_count_069(const struct search_context *context);
extern const search_query_069 *search_ranking_find_069(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_069(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_070 {
    SEARCH_QUERY_070_PRIMARY = 1,
    SEARCH_QUERY_070_SECONDARY = 2,
    SEARCH_QUERY_070_ARCHIVED = 4
};
typedef struct search_query_070 {
    tool_u32 id_070;
    tool_u16 revision_070;
    unsigned int flags_070 : 5;
    unsigned int state_070 : 3;
    const char *name_070;
    const tool_byte *payload_070;
    tool_size payload_length_070;
    struct search_query_070 *next_070;
    void *extension_070[3];
} search_query_070;
typedef union search_ranking_value_070 {
    long signed_value_070;
    unsigned long unsigned_value_070;
    double decimal_value_070;
    const void *pointer_value_070;
} search_ranking_value_070;
typedef int (*search_token_callback_070)(
    struct search_context *, const search_query_070 *, void *);
extern search_status search_token_open_070(
    struct search_context **context, const char *path_070, tool_u32 options_070);
extern search_status search_token_close_070(struct search_context *context);
extern int search_ranking_visit_070(
    struct search_context *context, search_token_callback_070 callback, void *userdata);
extern tool_size search_ranking_count_070(const struct search_context *context);
extern const search_query_070 *search_ranking_find_070(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_070(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_071 {
    SEARCH_QUERY_071_PRIMARY = 1,
    SEARCH_QUERY_071_SECONDARY = 2,
    SEARCH_QUERY_071_ARCHIVED = 4
};
typedef struct search_query_071 {
    tool_u32 id_071;
    tool_u16 revision_071;
    unsigned int flags_071 : 5;
    unsigned int state_071 : 3;
    const char *name_071;
    const tool_byte *payload_071;
    tool_size payload_length_071;
    struct search_query_071 *next_071;
    void *extension_071[3];
} search_query_071;
typedef union search_ranking_value_071 {
    long signed_value_071;
    unsigned long unsigned_value_071;
    double decimal_value_071;
    const void *pointer_value_071;
} search_ranking_value_071;
typedef int (*search_token_callback_071)(
    struct search_context *, const search_query_071 *, void *);
extern search_status search_token_open_071(
    struct search_context **context, const char *path_071, tool_u32 options_071);
extern search_status search_token_close_071(struct search_context *context);
extern int search_ranking_visit_071(
    struct search_context *context, search_token_callback_071 callback, void *userdata);
extern tool_size search_ranking_count_071(const struct search_context *context);
extern const search_query_071 *search_ranking_find_071(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_071(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_072 {
    SEARCH_QUERY_072_PRIMARY = 1,
    SEARCH_QUERY_072_SECONDARY = 2,
    SEARCH_QUERY_072_ARCHIVED = 4
};
typedef struct search_query_072 {
    tool_u32 id_072;
    tool_u16 revision_072;
    unsigned int flags_072 : 5;
    unsigned int state_072 : 3;
    const char *name_072;
    const tool_byte *payload_072;
    tool_size payload_length_072;
    struct search_query_072 *next_072;
    void *extension_072[3];
} search_query_072;
typedef union search_ranking_value_072 {
    long signed_value_072;
    unsigned long unsigned_value_072;
    double decimal_value_072;
    const void *pointer_value_072;
} search_ranking_value_072;
typedef int (*search_token_callback_072)(
    struct search_context *, const search_query_072 *, void *);
extern search_status search_token_open_072(
    struct search_context **context, const char *path_072, tool_u32 options_072);
extern search_status search_token_close_072(struct search_context *context);
extern int search_ranking_visit_072(
    struct search_context *context, search_token_callback_072 callback, void *userdata);
extern tool_size search_ranking_count_072(const struct search_context *context);
extern const search_query_072 *search_ranking_find_072(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_072(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_073 {
    SEARCH_QUERY_073_PRIMARY = 1,
    SEARCH_QUERY_073_SECONDARY = 2,
    SEARCH_QUERY_073_ARCHIVED = 4
};
typedef struct search_query_073 {
    tool_u32 id_073;
    tool_u16 revision_073;
    unsigned int flags_073 : 5;
    unsigned int state_073 : 3;
    const char *name_073;
    const tool_byte *payload_073;
    tool_size payload_length_073;
    struct search_query_073 *next_073;
    void *extension_073[3];
} search_query_073;
typedef union search_ranking_value_073 {
    long signed_value_073;
    unsigned long unsigned_value_073;
    double decimal_value_073;
    const void *pointer_value_073;
} search_ranking_value_073;
typedef int (*search_token_callback_073)(
    struct search_context *, const search_query_073 *, void *);
extern search_status search_token_open_073(
    struct search_context **context, const char *path_073, tool_u32 options_073);
extern search_status search_token_close_073(struct search_context *context);
extern int search_ranking_visit_073(
    struct search_context *context, search_token_callback_073 callback, void *userdata);
extern tool_size search_ranking_count_073(const struct search_context *context);
extern const search_query_073 *search_ranking_find_073(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_073(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_074 {
    SEARCH_QUERY_074_PRIMARY = 1,
    SEARCH_QUERY_074_SECONDARY = 2,
    SEARCH_QUERY_074_ARCHIVED = 4
};
typedef struct search_query_074 {
    tool_u32 id_074;
    tool_u16 revision_074;
    unsigned int flags_074 : 5;
    unsigned int state_074 : 3;
    const char *name_074;
    const tool_byte *payload_074;
    tool_size payload_length_074;
    struct search_query_074 *next_074;
    void *extension_074[3];
} search_query_074;
typedef union search_ranking_value_074 {
    long signed_value_074;
    unsigned long unsigned_value_074;
    double decimal_value_074;
    const void *pointer_value_074;
} search_ranking_value_074;
typedef int (*search_token_callback_074)(
    struct search_context *, const search_query_074 *, void *);
extern search_status search_token_open_074(
    struct search_context **context, const char *path_074, tool_u32 options_074);
extern search_status search_token_close_074(struct search_context *context);
extern int search_ranking_visit_074(
    struct search_context *context, search_token_callback_074 callback, void *userdata);
extern tool_size search_ranking_count_074(const struct search_context *context);
extern const search_query_074 *search_ranking_find_074(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_074(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_075 {
    SEARCH_QUERY_075_PRIMARY = 1,
    SEARCH_QUERY_075_SECONDARY = 2,
    SEARCH_QUERY_075_ARCHIVED = 4
};
typedef struct search_query_075 {
    tool_u32 id_075;
    tool_u16 revision_075;
    unsigned int flags_075 : 5;
    unsigned int state_075 : 3;
    const char *name_075;
    const tool_byte *payload_075;
    tool_size payload_length_075;
    struct search_query_075 *next_075;
    void *extension_075[3];
} search_query_075;
typedef union search_ranking_value_075 {
    long signed_value_075;
    unsigned long unsigned_value_075;
    double decimal_value_075;
    const void *pointer_value_075;
} search_ranking_value_075;
typedef int (*search_token_callback_075)(
    struct search_context *, const search_query_075 *, void *);
extern search_status search_token_open_075(
    struct search_context **context, const char *path_075, tool_u32 options_075);
extern search_status search_token_close_075(struct search_context *context);
extern int search_ranking_visit_075(
    struct search_context *context, search_token_callback_075 callback, void *userdata);
extern tool_size search_ranking_count_075(const struct search_context *context);
extern const search_query_075 *search_ranking_find_075(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_075(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_076 {
    SEARCH_QUERY_076_PRIMARY = 1,
    SEARCH_QUERY_076_SECONDARY = 2,
    SEARCH_QUERY_076_ARCHIVED = 4
};
typedef struct search_query_076 {
    tool_u32 id_076;
    tool_u16 revision_076;
    unsigned int flags_076 : 5;
    unsigned int state_076 : 3;
    const char *name_076;
    const tool_byte *payload_076;
    tool_size payload_length_076;
    struct search_query_076 *next_076;
    void *extension_076[3];
} search_query_076;
typedef union search_ranking_value_076 {
    long signed_value_076;
    unsigned long unsigned_value_076;
    double decimal_value_076;
    const void *pointer_value_076;
} search_ranking_value_076;
typedef int (*search_token_callback_076)(
    struct search_context *, const search_query_076 *, void *);
extern search_status search_token_open_076(
    struct search_context **context, const char *path_076, tool_u32 options_076);
extern search_status search_token_close_076(struct search_context *context);
extern int search_ranking_visit_076(
    struct search_context *context, search_token_callback_076 callback, void *userdata);
extern tool_size search_ranking_count_076(const struct search_context *context);
extern const search_query_076 *search_ranking_find_076(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_076(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_077 {
    SEARCH_QUERY_077_PRIMARY = 1,
    SEARCH_QUERY_077_SECONDARY = 2,
    SEARCH_QUERY_077_ARCHIVED = 4
};
typedef struct search_query_077 {
    tool_u32 id_077;
    tool_u16 revision_077;
    unsigned int flags_077 : 5;
    unsigned int state_077 : 3;
    const char *name_077;
    const tool_byte *payload_077;
    tool_size payload_length_077;
    struct search_query_077 *next_077;
    void *extension_077[3];
} search_query_077;
typedef union search_ranking_value_077 {
    long signed_value_077;
    unsigned long unsigned_value_077;
    double decimal_value_077;
    const void *pointer_value_077;
} search_ranking_value_077;
typedef int (*search_token_callback_077)(
    struct search_context *, const search_query_077 *, void *);
extern search_status search_token_open_077(
    struct search_context **context, const char *path_077, tool_u32 options_077);
extern search_status search_token_close_077(struct search_context *context);
extern int search_ranking_visit_077(
    struct search_context *context, search_token_callback_077 callback, void *userdata);
extern tool_size search_ranking_count_077(const struct search_context *context);
extern const search_query_077 *search_ranking_find_077(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_077(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_078 {
    SEARCH_QUERY_078_PRIMARY = 1,
    SEARCH_QUERY_078_SECONDARY = 2,
    SEARCH_QUERY_078_ARCHIVED = 4
};
typedef struct search_query_078 {
    tool_u32 id_078;
    tool_u16 revision_078;
    unsigned int flags_078 : 5;
    unsigned int state_078 : 3;
    const char *name_078;
    const tool_byte *payload_078;
    tool_size payload_length_078;
    struct search_query_078 *next_078;
    void *extension_078[3];
} search_query_078;
typedef union search_ranking_value_078 {
    long signed_value_078;
    unsigned long unsigned_value_078;
    double decimal_value_078;
    const void *pointer_value_078;
} search_ranking_value_078;
typedef int (*search_token_callback_078)(
    struct search_context *, const search_query_078 *, void *);
extern search_status search_token_open_078(
    struct search_context **context, const char *path_078, tool_u32 options_078);
extern search_status search_token_close_078(struct search_context *context);
extern int search_ranking_visit_078(
    struct search_context *context, search_token_callback_078 callback, void *userdata);
extern tool_size search_ranking_count_078(const struct search_context *context);
extern const search_query_078 *search_ranking_find_078(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_078(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_079 {
    SEARCH_QUERY_079_PRIMARY = 1,
    SEARCH_QUERY_079_SECONDARY = 2,
    SEARCH_QUERY_079_ARCHIVED = 4
};
typedef struct search_query_079 {
    tool_u32 id_079;
    tool_u16 revision_079;
    unsigned int flags_079 : 5;
    unsigned int state_079 : 3;
    const char *name_079;
    const tool_byte *payload_079;
    tool_size payload_length_079;
    struct search_query_079 *next_079;
    void *extension_079[3];
} search_query_079;
typedef union search_ranking_value_079 {
    long signed_value_079;
    unsigned long unsigned_value_079;
    double decimal_value_079;
    const void *pointer_value_079;
} search_ranking_value_079;
typedef int (*search_token_callback_079)(
    struct search_context *, const search_query_079 *, void *);
extern search_status search_token_open_079(
    struct search_context **context, const char *path_079, tool_u32 options_079);
extern search_status search_token_close_079(struct search_context *context);
extern int search_ranking_visit_079(
    struct search_context *context, search_token_callback_079 callback, void *userdata);
extern tool_size search_ranking_count_079(const struct search_context *context);
extern const search_query_079 *search_ranking_find_079(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_079(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_080 {
    SEARCH_QUERY_080_PRIMARY = 1,
    SEARCH_QUERY_080_SECONDARY = 2,
    SEARCH_QUERY_080_ARCHIVED = 4
};
typedef struct search_query_080 {
    tool_u32 id_080;
    tool_u16 revision_080;
    unsigned int flags_080 : 5;
    unsigned int state_080 : 3;
    const char *name_080;
    const tool_byte *payload_080;
    tool_size payload_length_080;
    struct search_query_080 *next_080;
    void *extension_080[3];
} search_query_080;
typedef union search_ranking_value_080 {
    long signed_value_080;
    unsigned long unsigned_value_080;
    double decimal_value_080;
    const void *pointer_value_080;
} search_ranking_value_080;
typedef int (*search_token_callback_080)(
    struct search_context *, const search_query_080 *, void *);
extern search_status search_token_open_080(
    struct search_context **context, const char *path_080, tool_u32 options_080);
extern search_status search_token_close_080(struct search_context *context);
extern int search_ranking_visit_080(
    struct search_context *context, search_token_callback_080 callback, void *userdata);
extern tool_size search_ranking_count_080(const struct search_context *context);
extern const search_query_080 *search_ranking_find_080(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_080(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_081 {
    SEARCH_QUERY_081_PRIMARY = 1,
    SEARCH_QUERY_081_SECONDARY = 2,
    SEARCH_QUERY_081_ARCHIVED = 4
};
typedef struct search_query_081 {
    tool_u32 id_081;
    tool_u16 revision_081;
    unsigned int flags_081 : 5;
    unsigned int state_081 : 3;
    const char *name_081;
    const tool_byte *payload_081;
    tool_size payload_length_081;
    struct search_query_081 *next_081;
    void *extension_081[3];
} search_query_081;
typedef union search_ranking_value_081 {
    long signed_value_081;
    unsigned long unsigned_value_081;
    double decimal_value_081;
    const void *pointer_value_081;
} search_ranking_value_081;
typedef int (*search_token_callback_081)(
    struct search_context *, const search_query_081 *, void *);
extern search_status search_token_open_081(
    struct search_context **context, const char *path_081, tool_u32 options_081);
extern search_status search_token_close_081(struct search_context *context);
extern int search_ranking_visit_081(
    struct search_context *context, search_token_callback_081 callback, void *userdata);
extern tool_size search_ranking_count_081(const struct search_context *context);
extern const search_query_081 *search_ranking_find_081(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_081(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_082 {
    SEARCH_QUERY_082_PRIMARY = 1,
    SEARCH_QUERY_082_SECONDARY = 2,
    SEARCH_QUERY_082_ARCHIVED = 4
};
typedef struct search_query_082 {
    tool_u32 id_082;
    tool_u16 revision_082;
    unsigned int flags_082 : 5;
    unsigned int state_082 : 3;
    const char *name_082;
    const tool_byte *payload_082;
    tool_size payload_length_082;
    struct search_query_082 *next_082;
    void *extension_082[3];
} search_query_082;
typedef union search_ranking_value_082 {
    long signed_value_082;
    unsigned long unsigned_value_082;
    double decimal_value_082;
    const void *pointer_value_082;
} search_ranking_value_082;
typedef int (*search_token_callback_082)(
    struct search_context *, const search_query_082 *, void *);
extern search_status search_token_open_082(
    struct search_context **context, const char *path_082, tool_u32 options_082);
extern search_status search_token_close_082(struct search_context *context);
extern int search_ranking_visit_082(
    struct search_context *context, search_token_callback_082 callback, void *userdata);
extern tool_size search_ranking_count_082(const struct search_context *context);
extern const search_query_082 *search_ranking_find_082(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_082(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_083 {
    SEARCH_QUERY_083_PRIMARY = 1,
    SEARCH_QUERY_083_SECONDARY = 2,
    SEARCH_QUERY_083_ARCHIVED = 4
};
typedef struct search_query_083 {
    tool_u32 id_083;
    tool_u16 revision_083;
    unsigned int flags_083 : 5;
    unsigned int state_083 : 3;
    const char *name_083;
    const tool_byte *payload_083;
    tool_size payload_length_083;
    struct search_query_083 *next_083;
    void *extension_083[3];
} search_query_083;
typedef union search_ranking_value_083 {
    long signed_value_083;
    unsigned long unsigned_value_083;
    double decimal_value_083;
    const void *pointer_value_083;
} search_ranking_value_083;
typedef int (*search_token_callback_083)(
    struct search_context *, const search_query_083 *, void *);
extern search_status search_token_open_083(
    struct search_context **context, const char *path_083, tool_u32 options_083);
extern search_status search_token_close_083(struct search_context *context);
extern int search_ranking_visit_083(
    struct search_context *context, search_token_callback_083 callback, void *userdata);
extern tool_size search_ranking_count_083(const struct search_context *context);
extern const search_query_083 *search_ranking_find_083(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_083(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_084 {
    SEARCH_QUERY_084_PRIMARY = 1,
    SEARCH_QUERY_084_SECONDARY = 2,
    SEARCH_QUERY_084_ARCHIVED = 4
};
typedef struct search_query_084 {
    tool_u32 id_084;
    tool_u16 revision_084;
    unsigned int flags_084 : 5;
    unsigned int state_084 : 3;
    const char *name_084;
    const tool_byte *payload_084;
    tool_size payload_length_084;
    struct search_query_084 *next_084;
    void *extension_084[3];
} search_query_084;
typedef union search_ranking_value_084 {
    long signed_value_084;
    unsigned long unsigned_value_084;
    double decimal_value_084;
    const void *pointer_value_084;
} search_ranking_value_084;
typedef int (*search_token_callback_084)(
    struct search_context *, const search_query_084 *, void *);
extern search_status search_token_open_084(
    struct search_context **context, const char *path_084, tool_u32 options_084);
extern search_status search_token_close_084(struct search_context *context);
extern int search_ranking_visit_084(
    struct search_context *context, search_token_callback_084 callback, void *userdata);
extern tool_size search_ranking_count_084(const struct search_context *context);
extern const search_query_084 *search_ranking_find_084(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_084(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_085 {
    SEARCH_QUERY_085_PRIMARY = 1,
    SEARCH_QUERY_085_SECONDARY = 2,
    SEARCH_QUERY_085_ARCHIVED = 4
};
typedef struct search_query_085 {
    tool_u32 id_085;
    tool_u16 revision_085;
    unsigned int flags_085 : 5;
    unsigned int state_085 : 3;
    const char *name_085;
    const tool_byte *payload_085;
    tool_size payload_length_085;
    struct search_query_085 *next_085;
    void *extension_085[3];
} search_query_085;
typedef union search_ranking_value_085 {
    long signed_value_085;
    unsigned long unsigned_value_085;
    double decimal_value_085;
    const void *pointer_value_085;
} search_ranking_value_085;
typedef int (*search_token_callback_085)(
    struct search_context *, const search_query_085 *, void *);
extern search_status search_token_open_085(
    struct search_context **context, const char *path_085, tool_u32 options_085);
extern search_status search_token_close_085(struct search_context *context);
extern int search_ranking_visit_085(
    struct search_context *context, search_token_callback_085 callback, void *userdata);
extern tool_size search_ranking_count_085(const struct search_context *context);
extern const search_query_085 *search_ranking_find_085(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_085(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_086 {
    SEARCH_QUERY_086_PRIMARY = 1,
    SEARCH_QUERY_086_SECONDARY = 2,
    SEARCH_QUERY_086_ARCHIVED = 4
};
typedef struct search_query_086 {
    tool_u32 id_086;
    tool_u16 revision_086;
    unsigned int flags_086 : 5;
    unsigned int state_086 : 3;
    const char *name_086;
    const tool_byte *payload_086;
    tool_size payload_length_086;
    struct search_query_086 *next_086;
    void *extension_086[3];
} search_query_086;
typedef union search_ranking_value_086 {
    long signed_value_086;
    unsigned long unsigned_value_086;
    double decimal_value_086;
    const void *pointer_value_086;
} search_ranking_value_086;
typedef int (*search_token_callback_086)(
    struct search_context *, const search_query_086 *, void *);
extern search_status search_token_open_086(
    struct search_context **context, const char *path_086, tool_u32 options_086);
extern search_status search_token_close_086(struct search_context *context);
extern int search_ranking_visit_086(
    struct search_context *context, search_token_callback_086 callback, void *userdata);
extern tool_size search_ranking_count_086(const struct search_context *context);
extern const search_query_086 *search_ranking_find_086(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_086(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_087 {
    SEARCH_QUERY_087_PRIMARY = 1,
    SEARCH_QUERY_087_SECONDARY = 2,
    SEARCH_QUERY_087_ARCHIVED = 4
};
typedef struct search_query_087 {
    tool_u32 id_087;
    tool_u16 revision_087;
    unsigned int flags_087 : 5;
    unsigned int state_087 : 3;
    const char *name_087;
    const tool_byte *payload_087;
    tool_size payload_length_087;
    struct search_query_087 *next_087;
    void *extension_087[3];
} search_query_087;
typedef union search_ranking_value_087 {
    long signed_value_087;
    unsigned long unsigned_value_087;
    double decimal_value_087;
    const void *pointer_value_087;
} search_ranking_value_087;
typedef int (*search_token_callback_087)(
    struct search_context *, const search_query_087 *, void *);
extern search_status search_token_open_087(
    struct search_context **context, const char *path_087, tool_u32 options_087);
extern search_status search_token_close_087(struct search_context *context);
extern int search_ranking_visit_087(
    struct search_context *context, search_token_callback_087 callback, void *userdata);
extern tool_size search_ranking_count_087(const struct search_context *context);
extern const search_query_087 *search_ranking_find_087(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_087(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_088 {
    SEARCH_QUERY_088_PRIMARY = 1,
    SEARCH_QUERY_088_SECONDARY = 2,
    SEARCH_QUERY_088_ARCHIVED = 4
};
typedef struct search_query_088 {
    tool_u32 id_088;
    tool_u16 revision_088;
    unsigned int flags_088 : 5;
    unsigned int state_088 : 3;
    const char *name_088;
    const tool_byte *payload_088;
    tool_size payload_length_088;
    struct search_query_088 *next_088;
    void *extension_088[3];
} search_query_088;
typedef union search_ranking_value_088 {
    long signed_value_088;
    unsigned long unsigned_value_088;
    double decimal_value_088;
    const void *pointer_value_088;
} search_ranking_value_088;
typedef int (*search_token_callback_088)(
    struct search_context *, const search_query_088 *, void *);
extern search_status search_token_open_088(
    struct search_context **context, const char *path_088, tool_u32 options_088);
extern search_status search_token_close_088(struct search_context *context);
extern int search_ranking_visit_088(
    struct search_context *context, search_token_callback_088 callback, void *userdata);
extern tool_size search_ranking_count_088(const struct search_context *context);
extern const search_query_088 *search_ranking_find_088(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_088(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_089 {
    SEARCH_QUERY_089_PRIMARY = 1,
    SEARCH_QUERY_089_SECONDARY = 2,
    SEARCH_QUERY_089_ARCHIVED = 4
};
typedef struct search_query_089 {
    tool_u32 id_089;
    tool_u16 revision_089;
    unsigned int flags_089 : 5;
    unsigned int state_089 : 3;
    const char *name_089;
    const tool_byte *payload_089;
    tool_size payload_length_089;
    struct search_query_089 *next_089;
    void *extension_089[3];
} search_query_089;
typedef union search_ranking_value_089 {
    long signed_value_089;
    unsigned long unsigned_value_089;
    double decimal_value_089;
    const void *pointer_value_089;
} search_ranking_value_089;
typedef int (*search_token_callback_089)(
    struct search_context *, const search_query_089 *, void *);
extern search_status search_token_open_089(
    struct search_context **context, const char *path_089, tool_u32 options_089);
extern search_status search_token_close_089(struct search_context *context);
extern int search_ranking_visit_089(
    struct search_context *context, search_token_callback_089 callback, void *userdata);
extern tool_size search_ranking_count_089(const struct search_context *context);
extern const search_query_089 *search_ranking_find_089(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_089(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_090 {
    SEARCH_QUERY_090_PRIMARY = 1,
    SEARCH_QUERY_090_SECONDARY = 2,
    SEARCH_QUERY_090_ARCHIVED = 4
};
typedef struct search_query_090 {
    tool_u32 id_090;
    tool_u16 revision_090;
    unsigned int flags_090 : 5;
    unsigned int state_090 : 3;
    const char *name_090;
    const tool_byte *payload_090;
    tool_size payload_length_090;
    struct search_query_090 *next_090;
    void *extension_090[3];
} search_query_090;
typedef union search_ranking_value_090 {
    long signed_value_090;
    unsigned long unsigned_value_090;
    double decimal_value_090;
    const void *pointer_value_090;
} search_ranking_value_090;
typedef int (*search_token_callback_090)(
    struct search_context *, const search_query_090 *, void *);
extern search_status search_token_open_090(
    struct search_context **context, const char *path_090, tool_u32 options_090);
extern search_status search_token_close_090(struct search_context *context);
extern int search_ranking_visit_090(
    struct search_context *context, search_token_callback_090 callback, void *userdata);
extern tool_size search_ranking_count_090(const struct search_context *context);
extern const search_query_090 *search_ranking_find_090(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_090(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_091 {
    SEARCH_QUERY_091_PRIMARY = 1,
    SEARCH_QUERY_091_SECONDARY = 2,
    SEARCH_QUERY_091_ARCHIVED = 4
};
typedef struct search_query_091 {
    tool_u32 id_091;
    tool_u16 revision_091;
    unsigned int flags_091 : 5;
    unsigned int state_091 : 3;
    const char *name_091;
    const tool_byte *payload_091;
    tool_size payload_length_091;
    struct search_query_091 *next_091;
    void *extension_091[3];
} search_query_091;
typedef union search_ranking_value_091 {
    long signed_value_091;
    unsigned long unsigned_value_091;
    double decimal_value_091;
    const void *pointer_value_091;
} search_ranking_value_091;
typedef int (*search_token_callback_091)(
    struct search_context *, const search_query_091 *, void *);
extern search_status search_token_open_091(
    struct search_context **context, const char *path_091, tool_u32 options_091);
extern search_status search_token_close_091(struct search_context *context);
extern int search_ranking_visit_091(
    struct search_context *context, search_token_callback_091 callback, void *userdata);
extern tool_size search_ranking_count_091(const struct search_context *context);
extern const search_query_091 *search_ranking_find_091(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_091(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_092 {
    SEARCH_QUERY_092_PRIMARY = 1,
    SEARCH_QUERY_092_SECONDARY = 2,
    SEARCH_QUERY_092_ARCHIVED = 4
};
typedef struct search_query_092 {
    tool_u32 id_092;
    tool_u16 revision_092;
    unsigned int flags_092 : 5;
    unsigned int state_092 : 3;
    const char *name_092;
    const tool_byte *payload_092;
    tool_size payload_length_092;
    struct search_query_092 *next_092;
    void *extension_092[3];
} search_query_092;
typedef union search_ranking_value_092 {
    long signed_value_092;
    unsigned long unsigned_value_092;
    double decimal_value_092;
    const void *pointer_value_092;
} search_ranking_value_092;
typedef int (*search_token_callback_092)(
    struct search_context *, const search_query_092 *, void *);
extern search_status search_token_open_092(
    struct search_context **context, const char *path_092, tool_u32 options_092);
extern search_status search_token_close_092(struct search_context *context);
extern int search_ranking_visit_092(
    struct search_context *context, search_token_callback_092 callback, void *userdata);
extern tool_size search_ranking_count_092(const struct search_context *context);
extern const search_query_092 *search_ranking_find_092(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_092(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_093 {
    SEARCH_QUERY_093_PRIMARY = 1,
    SEARCH_QUERY_093_SECONDARY = 2,
    SEARCH_QUERY_093_ARCHIVED = 4
};
typedef struct search_query_093 {
    tool_u32 id_093;
    tool_u16 revision_093;
    unsigned int flags_093 : 5;
    unsigned int state_093 : 3;
    const char *name_093;
    const tool_byte *payload_093;
    tool_size payload_length_093;
    struct search_query_093 *next_093;
    void *extension_093[3];
} search_query_093;
typedef union search_ranking_value_093 {
    long signed_value_093;
    unsigned long unsigned_value_093;
    double decimal_value_093;
    const void *pointer_value_093;
} search_ranking_value_093;
typedef int (*search_token_callback_093)(
    struct search_context *, const search_query_093 *, void *);
extern search_status search_token_open_093(
    struct search_context **context, const char *path_093, tool_u32 options_093);
extern search_status search_token_close_093(struct search_context *context);
extern int search_ranking_visit_093(
    struct search_context *context, search_token_callback_093 callback, void *userdata);
extern tool_size search_ranking_count_093(const struct search_context *context);
extern const search_query_093 *search_ranking_find_093(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_093(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_094 {
    SEARCH_QUERY_094_PRIMARY = 1,
    SEARCH_QUERY_094_SECONDARY = 2,
    SEARCH_QUERY_094_ARCHIVED = 4
};
typedef struct search_query_094 {
    tool_u32 id_094;
    tool_u16 revision_094;
    unsigned int flags_094 : 5;
    unsigned int state_094 : 3;
    const char *name_094;
    const tool_byte *payload_094;
    tool_size payload_length_094;
    struct search_query_094 *next_094;
    void *extension_094[3];
} search_query_094;
typedef union search_ranking_value_094 {
    long signed_value_094;
    unsigned long unsigned_value_094;
    double decimal_value_094;
    const void *pointer_value_094;
} search_ranking_value_094;
typedef int (*search_token_callback_094)(
    struct search_context *, const search_query_094 *, void *);
extern search_status search_token_open_094(
    struct search_context **context, const char *path_094, tool_u32 options_094);
extern search_status search_token_close_094(struct search_context *context);
extern int search_ranking_visit_094(
    struct search_context *context, search_token_callback_094 callback, void *userdata);
extern tool_size search_ranking_count_094(const struct search_context *context);
extern const search_query_094 *search_ranking_find_094(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_094(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_095 {
    SEARCH_QUERY_095_PRIMARY = 1,
    SEARCH_QUERY_095_SECONDARY = 2,
    SEARCH_QUERY_095_ARCHIVED = 4
};
typedef struct search_query_095 {
    tool_u32 id_095;
    tool_u16 revision_095;
    unsigned int flags_095 : 5;
    unsigned int state_095 : 3;
    const char *name_095;
    const tool_byte *payload_095;
    tool_size payload_length_095;
    struct search_query_095 *next_095;
    void *extension_095[3];
} search_query_095;
typedef union search_ranking_value_095 {
    long signed_value_095;
    unsigned long unsigned_value_095;
    double decimal_value_095;
    const void *pointer_value_095;
} search_ranking_value_095;
typedef int (*search_token_callback_095)(
    struct search_context *, const search_query_095 *, void *);
extern search_status search_token_open_095(
    struct search_context **context, const char *path_095, tool_u32 options_095);
extern search_status search_token_close_095(struct search_context *context);
extern int search_ranking_visit_095(
    struct search_context *context, search_token_callback_095 callback, void *userdata);
extern tool_size search_ranking_count_095(const struct search_context *context);
extern const search_query_095 *search_ranking_find_095(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_095(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_096 {
    SEARCH_QUERY_096_PRIMARY = 1,
    SEARCH_QUERY_096_SECONDARY = 2,
    SEARCH_QUERY_096_ARCHIVED = 4
};
typedef struct search_query_096 {
    tool_u32 id_096;
    tool_u16 revision_096;
    unsigned int flags_096 : 5;
    unsigned int state_096 : 3;
    const char *name_096;
    const tool_byte *payload_096;
    tool_size payload_length_096;
    struct search_query_096 *next_096;
    void *extension_096[3];
} search_query_096;
typedef union search_ranking_value_096 {
    long signed_value_096;
    unsigned long unsigned_value_096;
    double decimal_value_096;
    const void *pointer_value_096;
} search_ranking_value_096;
typedef int (*search_token_callback_096)(
    struct search_context *, const search_query_096 *, void *);
extern search_status search_token_open_096(
    struct search_context **context, const char *path_096, tool_u32 options_096);
extern search_status search_token_close_096(struct search_context *context);
extern int search_ranking_visit_096(
    struct search_context *context, search_token_callback_096 callback, void *userdata);
extern tool_size search_ranking_count_096(const struct search_context *context);
extern const search_query_096 *search_ranking_find_096(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_096(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_097 {
    SEARCH_QUERY_097_PRIMARY = 1,
    SEARCH_QUERY_097_SECONDARY = 2,
    SEARCH_QUERY_097_ARCHIVED = 4
};
typedef struct search_query_097 {
    tool_u32 id_097;
    tool_u16 revision_097;
    unsigned int flags_097 : 5;
    unsigned int state_097 : 3;
    const char *name_097;
    const tool_byte *payload_097;
    tool_size payload_length_097;
    struct search_query_097 *next_097;
    void *extension_097[3];
} search_query_097;
typedef union search_ranking_value_097 {
    long signed_value_097;
    unsigned long unsigned_value_097;
    double decimal_value_097;
    const void *pointer_value_097;
} search_ranking_value_097;
typedef int (*search_token_callback_097)(
    struct search_context *, const search_query_097 *, void *);
extern search_status search_token_open_097(
    struct search_context **context, const char *path_097, tool_u32 options_097);
extern search_status search_token_close_097(struct search_context *context);
extern int search_ranking_visit_097(
    struct search_context *context, search_token_callback_097 callback, void *userdata);
extern tool_size search_ranking_count_097(const struct search_context *context);
extern const search_query_097 *search_ranking_find_097(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_097(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_098 {
    SEARCH_QUERY_098_PRIMARY = 1,
    SEARCH_QUERY_098_SECONDARY = 2,
    SEARCH_QUERY_098_ARCHIVED = 4
};
typedef struct search_query_098 {
    tool_u32 id_098;
    tool_u16 revision_098;
    unsigned int flags_098 : 5;
    unsigned int state_098 : 3;
    const char *name_098;
    const tool_byte *payload_098;
    tool_size payload_length_098;
    struct search_query_098 *next_098;
    void *extension_098[3];
} search_query_098;
typedef union search_ranking_value_098 {
    long signed_value_098;
    unsigned long unsigned_value_098;
    double decimal_value_098;
    const void *pointer_value_098;
} search_ranking_value_098;
typedef int (*search_token_callback_098)(
    struct search_context *, const search_query_098 *, void *);
extern search_status search_token_open_098(
    struct search_context **context, const char *path_098, tool_u32 options_098);
extern search_status search_token_close_098(struct search_context *context);
extern int search_ranking_visit_098(
    struct search_context *context, search_token_callback_098 callback, void *userdata);
extern tool_size search_ranking_count_098(const struct search_context *context);
extern const search_query_098 *search_ranking_find_098(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_098(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_099 {
    SEARCH_QUERY_099_PRIMARY = 1,
    SEARCH_QUERY_099_SECONDARY = 2,
    SEARCH_QUERY_099_ARCHIVED = 4
};
typedef struct search_query_099 {
    tool_u32 id_099;
    tool_u16 revision_099;
    unsigned int flags_099 : 5;
    unsigned int state_099 : 3;
    const char *name_099;
    const tool_byte *payload_099;
    tool_size payload_length_099;
    struct search_query_099 *next_099;
    void *extension_099[3];
} search_query_099;
typedef union search_ranking_value_099 {
    long signed_value_099;
    unsigned long unsigned_value_099;
    double decimal_value_099;
    const void *pointer_value_099;
} search_ranking_value_099;
typedef int (*search_token_callback_099)(
    struct search_context *, const search_query_099 *, void *);
extern search_status search_token_open_099(
    struct search_context **context, const char *path_099, tool_u32 options_099);
extern search_status search_token_close_099(struct search_context *context);
extern int search_ranking_visit_099(
    struct search_context *context, search_token_callback_099 callback, void *userdata);
extern tool_size search_ranking_count_099(const struct search_context *context);
extern const search_query_099 *search_ranking_find_099(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_099(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_100 {
    SEARCH_QUERY_100_PRIMARY = 1,
    SEARCH_QUERY_100_SECONDARY = 2,
    SEARCH_QUERY_100_ARCHIVED = 4
};
typedef struct search_query_100 {
    tool_u32 id_100;
    tool_u16 revision_100;
    unsigned int flags_100 : 5;
    unsigned int state_100 : 3;
    const char *name_100;
    const tool_byte *payload_100;
    tool_size payload_length_100;
    struct search_query_100 *next_100;
    void *extension_100[3];
} search_query_100;
typedef union search_ranking_value_100 {
    long signed_value_100;
    unsigned long unsigned_value_100;
    double decimal_value_100;
    const void *pointer_value_100;
} search_ranking_value_100;
typedef int (*search_token_callback_100)(
    struct search_context *, const search_query_100 *, void *);
extern search_status search_token_open_100(
    struct search_context **context, const char *path_100, tool_u32 options_100);
extern search_status search_token_close_100(struct search_context *context);
extern int search_ranking_visit_100(
    struct search_context *context, search_token_callback_100 callback, void *userdata);
extern tool_size search_ranking_count_100(const struct search_context *context);
extern const search_query_100 *search_ranking_find_100(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_100(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_101 {
    SEARCH_QUERY_101_PRIMARY = 1,
    SEARCH_QUERY_101_SECONDARY = 2,
    SEARCH_QUERY_101_ARCHIVED = 4
};
typedef struct search_query_101 {
    tool_u32 id_101;
    tool_u16 revision_101;
    unsigned int flags_101 : 5;
    unsigned int state_101 : 3;
    const char *name_101;
    const tool_byte *payload_101;
    tool_size payload_length_101;
    struct search_query_101 *next_101;
    void *extension_101[3];
} search_query_101;
typedef union search_ranking_value_101 {
    long signed_value_101;
    unsigned long unsigned_value_101;
    double decimal_value_101;
    const void *pointer_value_101;
} search_ranking_value_101;
typedef int (*search_token_callback_101)(
    struct search_context *, const search_query_101 *, void *);
extern search_status search_token_open_101(
    struct search_context **context, const char *path_101, tool_u32 options_101);
extern search_status search_token_close_101(struct search_context *context);
extern int search_ranking_visit_101(
    struct search_context *context, search_token_callback_101 callback, void *userdata);
extern tool_size search_ranking_count_101(const struct search_context *context);
extern const search_query_101 *search_ranking_find_101(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_101(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_102 {
    SEARCH_QUERY_102_PRIMARY = 1,
    SEARCH_QUERY_102_SECONDARY = 2,
    SEARCH_QUERY_102_ARCHIVED = 4
};
typedef struct search_query_102 {
    tool_u32 id_102;
    tool_u16 revision_102;
    unsigned int flags_102 : 5;
    unsigned int state_102 : 3;
    const char *name_102;
    const tool_byte *payload_102;
    tool_size payload_length_102;
    struct search_query_102 *next_102;
    void *extension_102[3];
} search_query_102;
typedef union search_ranking_value_102 {
    long signed_value_102;
    unsigned long unsigned_value_102;
    double decimal_value_102;
    const void *pointer_value_102;
} search_ranking_value_102;
typedef int (*search_token_callback_102)(
    struct search_context *, const search_query_102 *, void *);
extern search_status search_token_open_102(
    struct search_context **context, const char *path_102, tool_u32 options_102);
extern search_status search_token_close_102(struct search_context *context);
extern int search_ranking_visit_102(
    struct search_context *context, search_token_callback_102 callback, void *userdata);
extern tool_size search_ranking_count_102(const struct search_context *context);
extern const search_query_102 *search_ranking_find_102(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_102(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_103 {
    SEARCH_QUERY_103_PRIMARY = 1,
    SEARCH_QUERY_103_SECONDARY = 2,
    SEARCH_QUERY_103_ARCHIVED = 4
};
typedef struct search_query_103 {
    tool_u32 id_103;
    tool_u16 revision_103;
    unsigned int flags_103 : 5;
    unsigned int state_103 : 3;
    const char *name_103;
    const tool_byte *payload_103;
    tool_size payload_length_103;
    struct search_query_103 *next_103;
    void *extension_103[3];
} search_query_103;
typedef union search_ranking_value_103 {
    long signed_value_103;
    unsigned long unsigned_value_103;
    double decimal_value_103;
    const void *pointer_value_103;
} search_ranking_value_103;
typedef int (*search_token_callback_103)(
    struct search_context *, const search_query_103 *, void *);
extern search_status search_token_open_103(
    struct search_context **context, const char *path_103, tool_u32 options_103);
extern search_status search_token_close_103(struct search_context *context);
extern int search_ranking_visit_103(
    struct search_context *context, search_token_callback_103 callback, void *userdata);
extern tool_size search_ranking_count_103(const struct search_context *context);
extern const search_query_103 *search_ranking_find_103(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_103(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_104 {
    SEARCH_QUERY_104_PRIMARY = 1,
    SEARCH_QUERY_104_SECONDARY = 2,
    SEARCH_QUERY_104_ARCHIVED = 4
};
typedef struct search_query_104 {
    tool_u32 id_104;
    tool_u16 revision_104;
    unsigned int flags_104 : 5;
    unsigned int state_104 : 3;
    const char *name_104;
    const tool_byte *payload_104;
    tool_size payload_length_104;
    struct search_query_104 *next_104;
    void *extension_104[3];
} search_query_104;
typedef union search_ranking_value_104 {
    long signed_value_104;
    unsigned long unsigned_value_104;
    double decimal_value_104;
    const void *pointer_value_104;
} search_ranking_value_104;
typedef int (*search_token_callback_104)(
    struct search_context *, const search_query_104 *, void *);
extern search_status search_token_open_104(
    struct search_context **context, const char *path_104, tool_u32 options_104);
extern search_status search_token_close_104(struct search_context *context);
extern int search_ranking_visit_104(
    struct search_context *context, search_token_callback_104 callback, void *userdata);
extern tool_size search_ranking_count_104(const struct search_context *context);
extern const search_query_104 *search_ranking_find_104(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_104(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_105 {
    SEARCH_QUERY_105_PRIMARY = 1,
    SEARCH_QUERY_105_SECONDARY = 2,
    SEARCH_QUERY_105_ARCHIVED = 4
};
typedef struct search_query_105 {
    tool_u32 id_105;
    tool_u16 revision_105;
    unsigned int flags_105 : 5;
    unsigned int state_105 : 3;
    const char *name_105;
    const tool_byte *payload_105;
    tool_size payload_length_105;
    struct search_query_105 *next_105;
    void *extension_105[3];
} search_query_105;
typedef union search_ranking_value_105 {
    long signed_value_105;
    unsigned long unsigned_value_105;
    double decimal_value_105;
    const void *pointer_value_105;
} search_ranking_value_105;
typedef int (*search_token_callback_105)(
    struct search_context *, const search_query_105 *, void *);
extern search_status search_token_open_105(
    struct search_context **context, const char *path_105, tool_u32 options_105);
extern search_status search_token_close_105(struct search_context *context);
extern int search_ranking_visit_105(
    struct search_context *context, search_token_callback_105 callback, void *userdata);
extern tool_size search_ranking_count_105(const struct search_context *context);
extern const search_query_105 *search_ranking_find_105(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_105(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_106 {
    SEARCH_QUERY_106_PRIMARY = 1,
    SEARCH_QUERY_106_SECONDARY = 2,
    SEARCH_QUERY_106_ARCHIVED = 4
};
typedef struct search_query_106 {
    tool_u32 id_106;
    tool_u16 revision_106;
    unsigned int flags_106 : 5;
    unsigned int state_106 : 3;
    const char *name_106;
    const tool_byte *payload_106;
    tool_size payload_length_106;
    struct search_query_106 *next_106;
    void *extension_106[3];
} search_query_106;
typedef union search_ranking_value_106 {
    long signed_value_106;
    unsigned long unsigned_value_106;
    double decimal_value_106;
    const void *pointer_value_106;
} search_ranking_value_106;
typedef int (*search_token_callback_106)(
    struct search_context *, const search_query_106 *, void *);
extern search_status search_token_open_106(
    struct search_context **context, const char *path_106, tool_u32 options_106);
extern search_status search_token_close_106(struct search_context *context);
extern int search_ranking_visit_106(
    struct search_context *context, search_token_callback_106 callback, void *userdata);
extern tool_size search_ranking_count_106(const struct search_context *context);
extern const search_query_106 *search_ranking_find_106(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_106(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_107 {
    SEARCH_QUERY_107_PRIMARY = 1,
    SEARCH_QUERY_107_SECONDARY = 2,
    SEARCH_QUERY_107_ARCHIVED = 4
};
typedef struct search_query_107 {
    tool_u32 id_107;
    tool_u16 revision_107;
    unsigned int flags_107 : 5;
    unsigned int state_107 : 3;
    const char *name_107;
    const tool_byte *payload_107;
    tool_size payload_length_107;
    struct search_query_107 *next_107;
    void *extension_107[3];
} search_query_107;
typedef union search_ranking_value_107 {
    long signed_value_107;
    unsigned long unsigned_value_107;
    double decimal_value_107;
    const void *pointer_value_107;
} search_ranking_value_107;
typedef int (*search_token_callback_107)(
    struct search_context *, const search_query_107 *, void *);
extern search_status search_token_open_107(
    struct search_context **context, const char *path_107, tool_u32 options_107);
extern search_status search_token_close_107(struct search_context *context);
extern int search_ranking_visit_107(
    struct search_context *context, search_token_callback_107 callback, void *userdata);
extern tool_size search_ranking_count_107(const struct search_context *context);
extern const search_query_107 *search_ranking_find_107(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_107(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_108 {
    SEARCH_QUERY_108_PRIMARY = 1,
    SEARCH_QUERY_108_SECONDARY = 2,
    SEARCH_QUERY_108_ARCHIVED = 4
};
typedef struct search_query_108 {
    tool_u32 id_108;
    tool_u16 revision_108;
    unsigned int flags_108 : 5;
    unsigned int state_108 : 3;
    const char *name_108;
    const tool_byte *payload_108;
    tool_size payload_length_108;
    struct search_query_108 *next_108;
    void *extension_108[3];
} search_query_108;
typedef union search_ranking_value_108 {
    long signed_value_108;
    unsigned long unsigned_value_108;
    double decimal_value_108;
    const void *pointer_value_108;
} search_ranking_value_108;
typedef int (*search_token_callback_108)(
    struct search_context *, const search_query_108 *, void *);
extern search_status search_token_open_108(
    struct search_context **context, const char *path_108, tool_u32 options_108);
extern search_status search_token_close_108(struct search_context *context);
extern int search_ranking_visit_108(
    struct search_context *context, search_token_callback_108 callback, void *userdata);
extern tool_size search_ranking_count_108(const struct search_context *context);
extern const search_query_108 *search_ranking_find_108(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_108(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_109 {
    SEARCH_QUERY_109_PRIMARY = 1,
    SEARCH_QUERY_109_SECONDARY = 2,
    SEARCH_QUERY_109_ARCHIVED = 4
};
typedef struct search_query_109 {
    tool_u32 id_109;
    tool_u16 revision_109;
    unsigned int flags_109 : 5;
    unsigned int state_109 : 3;
    const char *name_109;
    const tool_byte *payload_109;
    tool_size payload_length_109;
    struct search_query_109 *next_109;
    void *extension_109[3];
} search_query_109;
typedef union search_ranking_value_109 {
    long signed_value_109;
    unsigned long unsigned_value_109;
    double decimal_value_109;
    const void *pointer_value_109;
} search_ranking_value_109;
typedef int (*search_token_callback_109)(
    struct search_context *, const search_query_109 *, void *);
extern search_status search_token_open_109(
    struct search_context **context, const char *path_109, tool_u32 options_109);
extern search_status search_token_close_109(struct search_context *context);
extern int search_ranking_visit_109(
    struct search_context *context, search_token_callback_109 callback, void *userdata);
extern tool_size search_ranking_count_109(const struct search_context *context);
extern const search_query_109 *search_ranking_find_109(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_109(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_110 {
    SEARCH_QUERY_110_PRIMARY = 1,
    SEARCH_QUERY_110_SECONDARY = 2,
    SEARCH_QUERY_110_ARCHIVED = 4
};
typedef struct search_query_110 {
    tool_u32 id_110;
    tool_u16 revision_110;
    unsigned int flags_110 : 5;
    unsigned int state_110 : 3;
    const char *name_110;
    const tool_byte *payload_110;
    tool_size payload_length_110;
    struct search_query_110 *next_110;
    void *extension_110[3];
} search_query_110;
typedef union search_ranking_value_110 {
    long signed_value_110;
    unsigned long unsigned_value_110;
    double decimal_value_110;
    const void *pointer_value_110;
} search_ranking_value_110;
typedef int (*search_token_callback_110)(
    struct search_context *, const search_query_110 *, void *);
extern search_status search_token_open_110(
    struct search_context **context, const char *path_110, tool_u32 options_110);
extern search_status search_token_close_110(struct search_context *context);
extern int search_ranking_visit_110(
    struct search_context *context, search_token_callback_110 callback, void *userdata);
extern tool_size search_ranking_count_110(const struct search_context *context);
extern const search_query_110 *search_ranking_find_110(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_110(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_111 {
    SEARCH_QUERY_111_PRIMARY = 1,
    SEARCH_QUERY_111_SECONDARY = 2,
    SEARCH_QUERY_111_ARCHIVED = 4
};
typedef struct search_query_111 {
    tool_u32 id_111;
    tool_u16 revision_111;
    unsigned int flags_111 : 5;
    unsigned int state_111 : 3;
    const char *name_111;
    const tool_byte *payload_111;
    tool_size payload_length_111;
    struct search_query_111 *next_111;
    void *extension_111[3];
} search_query_111;
typedef union search_ranking_value_111 {
    long signed_value_111;
    unsigned long unsigned_value_111;
    double decimal_value_111;
    const void *pointer_value_111;
} search_ranking_value_111;
typedef int (*search_token_callback_111)(
    struct search_context *, const search_query_111 *, void *);
extern search_status search_token_open_111(
    struct search_context **context, const char *path_111, tool_u32 options_111);
extern search_status search_token_close_111(struct search_context *context);
extern int search_ranking_visit_111(
    struct search_context *context, search_token_callback_111 callback, void *userdata);
extern tool_size search_ranking_count_111(const struct search_context *context);
extern const search_query_111 *search_ranking_find_111(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_111(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_112 {
    SEARCH_QUERY_112_PRIMARY = 1,
    SEARCH_QUERY_112_SECONDARY = 2,
    SEARCH_QUERY_112_ARCHIVED = 4
};
typedef struct search_query_112 {
    tool_u32 id_112;
    tool_u16 revision_112;
    unsigned int flags_112 : 5;
    unsigned int state_112 : 3;
    const char *name_112;
    const tool_byte *payload_112;
    tool_size payload_length_112;
    struct search_query_112 *next_112;
    void *extension_112[3];
} search_query_112;
typedef union search_ranking_value_112 {
    long signed_value_112;
    unsigned long unsigned_value_112;
    double decimal_value_112;
    const void *pointer_value_112;
} search_ranking_value_112;
typedef int (*search_token_callback_112)(
    struct search_context *, const search_query_112 *, void *);
extern search_status search_token_open_112(
    struct search_context **context, const char *path_112, tool_u32 options_112);
extern search_status search_token_close_112(struct search_context *context);
extern int search_ranking_visit_112(
    struct search_context *context, search_token_callback_112 callback, void *userdata);
extern tool_size search_ranking_count_112(const struct search_context *context);
extern const search_query_112 *search_ranking_find_112(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_112(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_113 {
    SEARCH_QUERY_113_PRIMARY = 1,
    SEARCH_QUERY_113_SECONDARY = 2,
    SEARCH_QUERY_113_ARCHIVED = 4
};
typedef struct search_query_113 {
    tool_u32 id_113;
    tool_u16 revision_113;
    unsigned int flags_113 : 5;
    unsigned int state_113 : 3;
    const char *name_113;
    const tool_byte *payload_113;
    tool_size payload_length_113;
    struct search_query_113 *next_113;
    void *extension_113[3];
} search_query_113;
typedef union search_ranking_value_113 {
    long signed_value_113;
    unsigned long unsigned_value_113;
    double decimal_value_113;
    const void *pointer_value_113;
} search_ranking_value_113;
typedef int (*search_token_callback_113)(
    struct search_context *, const search_query_113 *, void *);
extern search_status search_token_open_113(
    struct search_context **context, const char *path_113, tool_u32 options_113);
extern search_status search_token_close_113(struct search_context *context);
extern int search_ranking_visit_113(
    struct search_context *context, search_token_callback_113 callback, void *userdata);
extern tool_size search_ranking_count_113(const struct search_context *context);
extern const search_query_113 *search_ranking_find_113(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_113(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_114 {
    SEARCH_QUERY_114_PRIMARY = 1,
    SEARCH_QUERY_114_SECONDARY = 2,
    SEARCH_QUERY_114_ARCHIVED = 4
};
typedef struct search_query_114 {
    tool_u32 id_114;
    tool_u16 revision_114;
    unsigned int flags_114 : 5;
    unsigned int state_114 : 3;
    const char *name_114;
    const tool_byte *payload_114;
    tool_size payload_length_114;
    struct search_query_114 *next_114;
    void *extension_114[3];
} search_query_114;
typedef union search_ranking_value_114 {
    long signed_value_114;
    unsigned long unsigned_value_114;
    double decimal_value_114;
    const void *pointer_value_114;
} search_ranking_value_114;
typedef int (*search_token_callback_114)(
    struct search_context *, const search_query_114 *, void *);
extern search_status search_token_open_114(
    struct search_context **context, const char *path_114, tool_u32 options_114);
extern search_status search_token_close_114(struct search_context *context);
extern int search_ranking_visit_114(
    struct search_context *context, search_token_callback_114 callback, void *userdata);
extern tool_size search_ranking_count_114(const struct search_context *context);
extern const search_query_114 *search_ranking_find_114(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_114(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_115 {
    SEARCH_QUERY_115_PRIMARY = 1,
    SEARCH_QUERY_115_SECONDARY = 2,
    SEARCH_QUERY_115_ARCHIVED = 4
};
typedef struct search_query_115 {
    tool_u32 id_115;
    tool_u16 revision_115;
    unsigned int flags_115 : 5;
    unsigned int state_115 : 3;
    const char *name_115;
    const tool_byte *payload_115;
    tool_size payload_length_115;
    struct search_query_115 *next_115;
    void *extension_115[3];
} search_query_115;
typedef union search_ranking_value_115 {
    long signed_value_115;
    unsigned long unsigned_value_115;
    double decimal_value_115;
    const void *pointer_value_115;
} search_ranking_value_115;
typedef int (*search_token_callback_115)(
    struct search_context *, const search_query_115 *, void *);
extern search_status search_token_open_115(
    struct search_context **context, const char *path_115, tool_u32 options_115);
extern search_status search_token_close_115(struct search_context *context);
extern int search_ranking_visit_115(
    struct search_context *context, search_token_callback_115 callback, void *userdata);
extern tool_size search_ranking_count_115(const struct search_context *context);
extern const search_query_115 *search_ranking_find_115(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_115(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_116 {
    SEARCH_QUERY_116_PRIMARY = 1,
    SEARCH_QUERY_116_SECONDARY = 2,
    SEARCH_QUERY_116_ARCHIVED = 4
};
typedef struct search_query_116 {
    tool_u32 id_116;
    tool_u16 revision_116;
    unsigned int flags_116 : 5;
    unsigned int state_116 : 3;
    const char *name_116;
    const tool_byte *payload_116;
    tool_size payload_length_116;
    struct search_query_116 *next_116;
    void *extension_116[3];
} search_query_116;
typedef union search_ranking_value_116 {
    long signed_value_116;
    unsigned long unsigned_value_116;
    double decimal_value_116;
    const void *pointer_value_116;
} search_ranking_value_116;
typedef int (*search_token_callback_116)(
    struct search_context *, const search_query_116 *, void *);
extern search_status search_token_open_116(
    struct search_context **context, const char *path_116, tool_u32 options_116);
extern search_status search_token_close_116(struct search_context *context);
extern int search_ranking_visit_116(
    struct search_context *context, search_token_callback_116 callback, void *userdata);
extern tool_size search_ranking_count_116(const struct search_context *context);
extern const search_query_116 *search_ranking_find_116(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_116(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_117 {
    SEARCH_QUERY_117_PRIMARY = 1,
    SEARCH_QUERY_117_SECONDARY = 2,
    SEARCH_QUERY_117_ARCHIVED = 4
};
typedef struct search_query_117 {
    tool_u32 id_117;
    tool_u16 revision_117;
    unsigned int flags_117 : 5;
    unsigned int state_117 : 3;
    const char *name_117;
    const tool_byte *payload_117;
    tool_size payload_length_117;
    struct search_query_117 *next_117;
    void *extension_117[3];
} search_query_117;
typedef union search_ranking_value_117 {
    long signed_value_117;
    unsigned long unsigned_value_117;
    double decimal_value_117;
    const void *pointer_value_117;
} search_ranking_value_117;
typedef int (*search_token_callback_117)(
    struct search_context *, const search_query_117 *, void *);
extern search_status search_token_open_117(
    struct search_context **context, const char *path_117, tool_u32 options_117);
extern search_status search_token_close_117(struct search_context *context);
extern int search_ranking_visit_117(
    struct search_context *context, search_token_callback_117 callback, void *userdata);
extern tool_size search_ranking_count_117(const struct search_context *context);
extern const search_query_117 *search_ranking_find_117(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_117(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_118 {
    SEARCH_QUERY_118_PRIMARY = 1,
    SEARCH_QUERY_118_SECONDARY = 2,
    SEARCH_QUERY_118_ARCHIVED = 4
};
typedef struct search_query_118 {
    tool_u32 id_118;
    tool_u16 revision_118;
    unsigned int flags_118 : 5;
    unsigned int state_118 : 3;
    const char *name_118;
    const tool_byte *payload_118;
    tool_size payload_length_118;
    struct search_query_118 *next_118;
    void *extension_118[3];
} search_query_118;
typedef union search_ranking_value_118 {
    long signed_value_118;
    unsigned long unsigned_value_118;
    double decimal_value_118;
    const void *pointer_value_118;
} search_ranking_value_118;
typedef int (*search_token_callback_118)(
    struct search_context *, const search_query_118 *, void *);
extern search_status search_token_open_118(
    struct search_context **context, const char *path_118, tool_u32 options_118);
extern search_status search_token_close_118(struct search_context *context);
extern int search_ranking_visit_118(
    struct search_context *context, search_token_callback_118 callback, void *userdata);
extern tool_size search_ranking_count_118(const struct search_context *context);
extern const search_query_118 *search_ranking_find_118(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_118(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_119 {
    SEARCH_QUERY_119_PRIMARY = 1,
    SEARCH_QUERY_119_SECONDARY = 2,
    SEARCH_QUERY_119_ARCHIVED = 4
};
typedef struct search_query_119 {
    tool_u32 id_119;
    tool_u16 revision_119;
    unsigned int flags_119 : 5;
    unsigned int state_119 : 3;
    const char *name_119;
    const tool_byte *payload_119;
    tool_size payload_length_119;
    struct search_query_119 *next_119;
    void *extension_119[3];
} search_query_119;
typedef union search_ranking_value_119 {
    long signed_value_119;
    unsigned long unsigned_value_119;
    double decimal_value_119;
    const void *pointer_value_119;
} search_ranking_value_119;
typedef int (*search_token_callback_119)(
    struct search_context *, const search_query_119 *, void *);
extern search_status search_token_open_119(
    struct search_context **context, const char *path_119, tool_u32 options_119);
extern search_status search_token_close_119(struct search_context *context);
extern int search_ranking_visit_119(
    struct search_context *context, search_token_callback_119 callback, void *userdata);
extern tool_size search_ranking_count_119(const struct search_context *context);
extern const search_query_119 *search_ranking_find_119(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_119(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_120 {
    SEARCH_QUERY_120_PRIMARY = 1,
    SEARCH_QUERY_120_SECONDARY = 2,
    SEARCH_QUERY_120_ARCHIVED = 4
};
typedef struct search_query_120 {
    tool_u32 id_120;
    tool_u16 revision_120;
    unsigned int flags_120 : 5;
    unsigned int state_120 : 3;
    const char *name_120;
    const tool_byte *payload_120;
    tool_size payload_length_120;
    struct search_query_120 *next_120;
    void *extension_120[3];
} search_query_120;
typedef union search_ranking_value_120 {
    long signed_value_120;
    unsigned long unsigned_value_120;
    double decimal_value_120;
    const void *pointer_value_120;
} search_ranking_value_120;
typedef int (*search_token_callback_120)(
    struct search_context *, const search_query_120 *, void *);
extern search_status search_token_open_120(
    struct search_context **context, const char *path_120, tool_u32 options_120);
extern search_status search_token_close_120(struct search_context *context);
extern int search_ranking_visit_120(
    struct search_context *context, search_token_callback_120 callback, void *userdata);
extern tool_size search_ranking_count_120(const struct search_context *context);
extern const search_query_120 *search_ranking_find_120(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_120(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_121 {
    SEARCH_QUERY_121_PRIMARY = 1,
    SEARCH_QUERY_121_SECONDARY = 2,
    SEARCH_QUERY_121_ARCHIVED = 4
};
typedef struct search_query_121 {
    tool_u32 id_121;
    tool_u16 revision_121;
    unsigned int flags_121 : 5;
    unsigned int state_121 : 3;
    const char *name_121;
    const tool_byte *payload_121;
    tool_size payload_length_121;
    struct search_query_121 *next_121;
    void *extension_121[3];
} search_query_121;
typedef union search_ranking_value_121 {
    long signed_value_121;
    unsigned long unsigned_value_121;
    double decimal_value_121;
    const void *pointer_value_121;
} search_ranking_value_121;
typedef int (*search_token_callback_121)(
    struct search_context *, const search_query_121 *, void *);
extern search_status search_token_open_121(
    struct search_context **context, const char *path_121, tool_u32 options_121);
extern search_status search_token_close_121(struct search_context *context);
extern int search_ranking_visit_121(
    struct search_context *context, search_token_callback_121 callback, void *userdata);
extern tool_size search_ranking_count_121(const struct search_context *context);
extern const search_query_121 *search_ranking_find_121(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_121(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_122 {
    SEARCH_QUERY_122_PRIMARY = 1,
    SEARCH_QUERY_122_SECONDARY = 2,
    SEARCH_QUERY_122_ARCHIVED = 4
};
typedef struct search_query_122 {
    tool_u32 id_122;
    tool_u16 revision_122;
    unsigned int flags_122 : 5;
    unsigned int state_122 : 3;
    const char *name_122;
    const tool_byte *payload_122;
    tool_size payload_length_122;
    struct search_query_122 *next_122;
    void *extension_122[3];
} search_query_122;
typedef union search_ranking_value_122 {
    long signed_value_122;
    unsigned long unsigned_value_122;
    double decimal_value_122;
    const void *pointer_value_122;
} search_ranking_value_122;
typedef int (*search_token_callback_122)(
    struct search_context *, const search_query_122 *, void *);
extern search_status search_token_open_122(
    struct search_context **context, const char *path_122, tool_u32 options_122);
extern search_status search_token_close_122(struct search_context *context);
extern int search_ranking_visit_122(
    struct search_context *context, search_token_callback_122 callback, void *userdata);
extern tool_size search_ranking_count_122(const struct search_context *context);
extern const search_query_122 *search_ranking_find_122(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_122(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_123 {
    SEARCH_QUERY_123_PRIMARY = 1,
    SEARCH_QUERY_123_SECONDARY = 2,
    SEARCH_QUERY_123_ARCHIVED = 4
};
typedef struct search_query_123 {
    tool_u32 id_123;
    tool_u16 revision_123;
    unsigned int flags_123 : 5;
    unsigned int state_123 : 3;
    const char *name_123;
    const tool_byte *payload_123;
    tool_size payload_length_123;
    struct search_query_123 *next_123;
    void *extension_123[3];
} search_query_123;
typedef union search_ranking_value_123 {
    long signed_value_123;
    unsigned long unsigned_value_123;
    double decimal_value_123;
    const void *pointer_value_123;
} search_ranking_value_123;
typedef int (*search_token_callback_123)(
    struct search_context *, const search_query_123 *, void *);
extern search_status search_token_open_123(
    struct search_context **context, const char *path_123, tool_u32 options_123);
extern search_status search_token_close_123(struct search_context *context);
extern int search_ranking_visit_123(
    struct search_context *context, search_token_callback_123 callback, void *userdata);
extern tool_size search_ranking_count_123(const struct search_context *context);
extern const search_query_123 *search_ranking_find_123(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_123(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_124 {
    SEARCH_QUERY_124_PRIMARY = 1,
    SEARCH_QUERY_124_SECONDARY = 2,
    SEARCH_QUERY_124_ARCHIVED = 4
};
typedef struct search_query_124 {
    tool_u32 id_124;
    tool_u16 revision_124;
    unsigned int flags_124 : 5;
    unsigned int state_124 : 3;
    const char *name_124;
    const tool_byte *payload_124;
    tool_size payload_length_124;
    struct search_query_124 *next_124;
    void *extension_124[3];
} search_query_124;
typedef union search_ranking_value_124 {
    long signed_value_124;
    unsigned long unsigned_value_124;
    double decimal_value_124;
    const void *pointer_value_124;
} search_ranking_value_124;
typedef int (*search_token_callback_124)(
    struct search_context *, const search_query_124 *, void *);
extern search_status search_token_open_124(
    struct search_context **context, const char *path_124, tool_u32 options_124);
extern search_status search_token_close_124(struct search_context *context);
extern int search_ranking_visit_124(
    struct search_context *context, search_token_callback_124 callback, void *userdata);
extern tool_size search_ranking_count_124(const struct search_context *context);
extern const search_query_124 *search_ranking_find_124(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_124(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_125 {
    SEARCH_QUERY_125_PRIMARY = 1,
    SEARCH_QUERY_125_SECONDARY = 2,
    SEARCH_QUERY_125_ARCHIVED = 4
};
typedef struct search_query_125 {
    tool_u32 id_125;
    tool_u16 revision_125;
    unsigned int flags_125 : 5;
    unsigned int state_125 : 3;
    const char *name_125;
    const tool_byte *payload_125;
    tool_size payload_length_125;
    struct search_query_125 *next_125;
    void *extension_125[3];
} search_query_125;
typedef union search_ranking_value_125 {
    long signed_value_125;
    unsigned long unsigned_value_125;
    double decimal_value_125;
    const void *pointer_value_125;
} search_ranking_value_125;
typedef int (*search_token_callback_125)(
    struct search_context *, const search_query_125 *, void *);
extern search_status search_token_open_125(
    struct search_context **context, const char *path_125, tool_u32 options_125);
extern search_status search_token_close_125(struct search_context *context);
extern int search_ranking_visit_125(
    struct search_context *context, search_token_callback_125 callback, void *userdata);
extern tool_size search_ranking_count_125(const struct search_context *context);
extern const search_query_125 *search_ranking_find_125(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_125(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_126 {
    SEARCH_QUERY_126_PRIMARY = 1,
    SEARCH_QUERY_126_SECONDARY = 2,
    SEARCH_QUERY_126_ARCHIVED = 4
};
typedef struct search_query_126 {
    tool_u32 id_126;
    tool_u16 revision_126;
    unsigned int flags_126 : 5;
    unsigned int state_126 : 3;
    const char *name_126;
    const tool_byte *payload_126;
    tool_size payload_length_126;
    struct search_query_126 *next_126;
    void *extension_126[3];
} search_query_126;
typedef union search_ranking_value_126 {
    long signed_value_126;
    unsigned long unsigned_value_126;
    double decimal_value_126;
    const void *pointer_value_126;
} search_ranking_value_126;
typedef int (*search_token_callback_126)(
    struct search_context *, const search_query_126 *, void *);
extern search_status search_token_open_126(
    struct search_context **context, const char *path_126, tool_u32 options_126);
extern search_status search_token_close_126(struct search_context *context);
extern int search_ranking_visit_126(
    struct search_context *context, search_token_callback_126 callback, void *userdata);
extern tool_size search_ranking_count_126(const struct search_context *context);
extern const search_query_126 *search_ranking_find_126(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_126(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_127 {
    SEARCH_QUERY_127_PRIMARY = 1,
    SEARCH_QUERY_127_SECONDARY = 2,
    SEARCH_QUERY_127_ARCHIVED = 4
};
typedef struct search_query_127 {
    tool_u32 id_127;
    tool_u16 revision_127;
    unsigned int flags_127 : 5;
    unsigned int state_127 : 3;
    const char *name_127;
    const tool_byte *payload_127;
    tool_size payload_length_127;
    struct search_query_127 *next_127;
    void *extension_127[3];
} search_query_127;
typedef union search_ranking_value_127 {
    long signed_value_127;
    unsigned long unsigned_value_127;
    double decimal_value_127;
    const void *pointer_value_127;
} search_ranking_value_127;
typedef int (*search_token_callback_127)(
    struct search_context *, const search_query_127 *, void *);
extern search_status search_token_open_127(
    struct search_context **context, const char *path_127, tool_u32 options_127);
extern search_status search_token_close_127(struct search_context *context);
extern int search_ranking_visit_127(
    struct search_context *context, search_token_callback_127 callback, void *userdata);
extern tool_size search_ranking_count_127(const struct search_context *context);
extern const search_query_127 *search_ranking_find_127(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_127(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_128 {
    SEARCH_QUERY_128_PRIMARY = 1,
    SEARCH_QUERY_128_SECONDARY = 2,
    SEARCH_QUERY_128_ARCHIVED = 4
};
typedef struct search_query_128 {
    tool_u32 id_128;
    tool_u16 revision_128;
    unsigned int flags_128 : 5;
    unsigned int state_128 : 3;
    const char *name_128;
    const tool_byte *payload_128;
    tool_size payload_length_128;
    struct search_query_128 *next_128;
    void *extension_128[3];
} search_query_128;
typedef union search_ranking_value_128 {
    long signed_value_128;
    unsigned long unsigned_value_128;
    double decimal_value_128;
    const void *pointer_value_128;
} search_ranking_value_128;
typedef int (*search_token_callback_128)(
    struct search_context *, const search_query_128 *, void *);
extern search_status search_token_open_128(
    struct search_context **context, const char *path_128, tool_u32 options_128);
extern search_status search_token_close_128(struct search_context *context);
extern int search_ranking_visit_128(
    struct search_context *context, search_token_callback_128 callback, void *userdata);
extern tool_size search_ranking_count_128(const struct search_context *context);
extern const search_query_128 *search_ranking_find_128(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_128(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_129 {
    SEARCH_QUERY_129_PRIMARY = 1,
    SEARCH_QUERY_129_SECONDARY = 2,
    SEARCH_QUERY_129_ARCHIVED = 4
};
typedef struct search_query_129 {
    tool_u32 id_129;
    tool_u16 revision_129;
    unsigned int flags_129 : 5;
    unsigned int state_129 : 3;
    const char *name_129;
    const tool_byte *payload_129;
    tool_size payload_length_129;
    struct search_query_129 *next_129;
    void *extension_129[3];
} search_query_129;
typedef union search_ranking_value_129 {
    long signed_value_129;
    unsigned long unsigned_value_129;
    double decimal_value_129;
    const void *pointer_value_129;
} search_ranking_value_129;
typedef int (*search_token_callback_129)(
    struct search_context *, const search_query_129 *, void *);
extern search_status search_token_open_129(
    struct search_context **context, const char *path_129, tool_u32 options_129);
extern search_status search_token_close_129(struct search_context *context);
extern int search_ranking_visit_129(
    struct search_context *context, search_token_callback_129 callback, void *userdata);
extern tool_size search_ranking_count_129(const struct search_context *context);
extern const search_query_129 *search_ranking_find_129(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_129(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_130 {
    SEARCH_QUERY_130_PRIMARY = 1,
    SEARCH_QUERY_130_SECONDARY = 2,
    SEARCH_QUERY_130_ARCHIVED = 4
};
typedef struct search_query_130 {
    tool_u32 id_130;
    tool_u16 revision_130;
    unsigned int flags_130 : 5;
    unsigned int state_130 : 3;
    const char *name_130;
    const tool_byte *payload_130;
    tool_size payload_length_130;
    struct search_query_130 *next_130;
    void *extension_130[3];
} search_query_130;
typedef union search_ranking_value_130 {
    long signed_value_130;
    unsigned long unsigned_value_130;
    double decimal_value_130;
    const void *pointer_value_130;
} search_ranking_value_130;
typedef int (*search_token_callback_130)(
    struct search_context *, const search_query_130 *, void *);
extern search_status search_token_open_130(
    struct search_context **context, const char *path_130, tool_u32 options_130);
extern search_status search_token_close_130(struct search_context *context);
extern int search_ranking_visit_130(
    struct search_context *context, search_token_callback_130 callback, void *userdata);
extern tool_size search_ranking_count_130(const struct search_context *context);
extern const search_query_130 *search_ranking_find_130(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_130(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_131 {
    SEARCH_QUERY_131_PRIMARY = 1,
    SEARCH_QUERY_131_SECONDARY = 2,
    SEARCH_QUERY_131_ARCHIVED = 4
};
typedef struct search_query_131 {
    tool_u32 id_131;
    tool_u16 revision_131;
    unsigned int flags_131 : 5;
    unsigned int state_131 : 3;
    const char *name_131;
    const tool_byte *payload_131;
    tool_size payload_length_131;
    struct search_query_131 *next_131;
    void *extension_131[3];
} search_query_131;
typedef union search_ranking_value_131 {
    long signed_value_131;
    unsigned long unsigned_value_131;
    double decimal_value_131;
    const void *pointer_value_131;
} search_ranking_value_131;
typedef int (*search_token_callback_131)(
    struct search_context *, const search_query_131 *, void *);
extern search_status search_token_open_131(
    struct search_context **context, const char *path_131, tool_u32 options_131);
extern search_status search_token_close_131(struct search_context *context);
extern int search_ranking_visit_131(
    struct search_context *context, search_token_callback_131 callback, void *userdata);
extern tool_size search_ranking_count_131(const struct search_context *context);
extern const search_query_131 *search_ranking_find_131(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_131(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_132 {
    SEARCH_QUERY_132_PRIMARY = 1,
    SEARCH_QUERY_132_SECONDARY = 2,
    SEARCH_QUERY_132_ARCHIVED = 4
};
typedef struct search_query_132 {
    tool_u32 id_132;
    tool_u16 revision_132;
    unsigned int flags_132 : 5;
    unsigned int state_132 : 3;
    const char *name_132;
    const tool_byte *payload_132;
    tool_size payload_length_132;
    struct search_query_132 *next_132;
    void *extension_132[3];
} search_query_132;
typedef union search_ranking_value_132 {
    long signed_value_132;
    unsigned long unsigned_value_132;
    double decimal_value_132;
    const void *pointer_value_132;
} search_ranking_value_132;
typedef int (*search_token_callback_132)(
    struct search_context *, const search_query_132 *, void *);
extern search_status search_token_open_132(
    struct search_context **context, const char *path_132, tool_u32 options_132);
extern search_status search_token_close_132(struct search_context *context);
extern int search_ranking_visit_132(
    struct search_context *context, search_token_callback_132 callback, void *userdata);
extern tool_size search_ranking_count_132(const struct search_context *context);
extern const search_query_132 *search_ranking_find_132(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_132(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_133 {
    SEARCH_QUERY_133_PRIMARY = 1,
    SEARCH_QUERY_133_SECONDARY = 2,
    SEARCH_QUERY_133_ARCHIVED = 4
};
typedef struct search_query_133 {
    tool_u32 id_133;
    tool_u16 revision_133;
    unsigned int flags_133 : 5;
    unsigned int state_133 : 3;
    const char *name_133;
    const tool_byte *payload_133;
    tool_size payload_length_133;
    struct search_query_133 *next_133;
    void *extension_133[3];
} search_query_133;
typedef union search_ranking_value_133 {
    long signed_value_133;
    unsigned long unsigned_value_133;
    double decimal_value_133;
    const void *pointer_value_133;
} search_ranking_value_133;
typedef int (*search_token_callback_133)(
    struct search_context *, const search_query_133 *, void *);
extern search_status search_token_open_133(
    struct search_context **context, const char *path_133, tool_u32 options_133);
extern search_status search_token_close_133(struct search_context *context);
extern int search_ranking_visit_133(
    struct search_context *context, search_token_callback_133 callback, void *userdata);
extern tool_size search_ranking_count_133(const struct search_context *context);
extern const search_query_133 *search_ranking_find_133(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_133(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_134 {
    SEARCH_QUERY_134_PRIMARY = 1,
    SEARCH_QUERY_134_SECONDARY = 2,
    SEARCH_QUERY_134_ARCHIVED = 4
};
typedef struct search_query_134 {
    tool_u32 id_134;
    tool_u16 revision_134;
    unsigned int flags_134 : 5;
    unsigned int state_134 : 3;
    const char *name_134;
    const tool_byte *payload_134;
    tool_size payload_length_134;
    struct search_query_134 *next_134;
    void *extension_134[3];
} search_query_134;
typedef union search_ranking_value_134 {
    long signed_value_134;
    unsigned long unsigned_value_134;
    double decimal_value_134;
    const void *pointer_value_134;
} search_ranking_value_134;
typedef int (*search_token_callback_134)(
    struct search_context *, const search_query_134 *, void *);
extern search_status search_token_open_134(
    struct search_context **context, const char *path_134, tool_u32 options_134);
extern search_status search_token_close_134(struct search_context *context);
extern int search_ranking_visit_134(
    struct search_context *context, search_token_callback_134 callback, void *userdata);
extern tool_size search_ranking_count_134(const struct search_context *context);
extern const search_query_134 *search_ranking_find_134(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_134(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_135 {
    SEARCH_QUERY_135_PRIMARY = 1,
    SEARCH_QUERY_135_SECONDARY = 2,
    SEARCH_QUERY_135_ARCHIVED = 4
};
typedef struct search_query_135 {
    tool_u32 id_135;
    tool_u16 revision_135;
    unsigned int flags_135 : 5;
    unsigned int state_135 : 3;
    const char *name_135;
    const tool_byte *payload_135;
    tool_size payload_length_135;
    struct search_query_135 *next_135;
    void *extension_135[3];
} search_query_135;
typedef union search_ranking_value_135 {
    long signed_value_135;
    unsigned long unsigned_value_135;
    double decimal_value_135;
    const void *pointer_value_135;
} search_ranking_value_135;
typedef int (*search_token_callback_135)(
    struct search_context *, const search_query_135 *, void *);
extern search_status search_token_open_135(
    struct search_context **context, const char *path_135, tool_u32 options_135);
extern search_status search_token_close_135(struct search_context *context);
extern int search_ranking_visit_135(
    struct search_context *context, search_token_callback_135 callback, void *userdata);
extern tool_size search_ranking_count_135(const struct search_context *context);
extern const search_query_135 *search_ranking_find_135(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_135(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_136 {
    SEARCH_QUERY_136_PRIMARY = 1,
    SEARCH_QUERY_136_SECONDARY = 2,
    SEARCH_QUERY_136_ARCHIVED = 4
};
typedef struct search_query_136 {
    tool_u32 id_136;
    tool_u16 revision_136;
    unsigned int flags_136 : 5;
    unsigned int state_136 : 3;
    const char *name_136;
    const tool_byte *payload_136;
    tool_size payload_length_136;
    struct search_query_136 *next_136;
    void *extension_136[3];
} search_query_136;
typedef union search_ranking_value_136 {
    long signed_value_136;
    unsigned long unsigned_value_136;
    double decimal_value_136;
    const void *pointer_value_136;
} search_ranking_value_136;
typedef int (*search_token_callback_136)(
    struct search_context *, const search_query_136 *, void *);
extern search_status search_token_open_136(
    struct search_context **context, const char *path_136, tool_u32 options_136);
extern search_status search_token_close_136(struct search_context *context);
extern int search_ranking_visit_136(
    struct search_context *context, search_token_callback_136 callback, void *userdata);
extern tool_size search_ranking_count_136(const struct search_context *context);
extern const search_query_136 *search_ranking_find_136(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_136(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_137 {
    SEARCH_QUERY_137_PRIMARY = 1,
    SEARCH_QUERY_137_SECONDARY = 2,
    SEARCH_QUERY_137_ARCHIVED = 4
};
typedef struct search_query_137 {
    tool_u32 id_137;
    tool_u16 revision_137;
    unsigned int flags_137 : 5;
    unsigned int state_137 : 3;
    const char *name_137;
    const tool_byte *payload_137;
    tool_size payload_length_137;
    struct search_query_137 *next_137;
    void *extension_137[3];
} search_query_137;
typedef union search_ranking_value_137 {
    long signed_value_137;
    unsigned long unsigned_value_137;
    double decimal_value_137;
    const void *pointer_value_137;
} search_ranking_value_137;
typedef int (*search_token_callback_137)(
    struct search_context *, const search_query_137 *, void *);
extern search_status search_token_open_137(
    struct search_context **context, const char *path_137, tool_u32 options_137);
extern search_status search_token_close_137(struct search_context *context);
extern int search_ranking_visit_137(
    struct search_context *context, search_token_callback_137 callback, void *userdata);
extern tool_size search_ranking_count_137(const struct search_context *context);
extern const search_query_137 *search_ranking_find_137(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_137(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_138 {
    SEARCH_QUERY_138_PRIMARY = 1,
    SEARCH_QUERY_138_SECONDARY = 2,
    SEARCH_QUERY_138_ARCHIVED = 4
};
typedef struct search_query_138 {
    tool_u32 id_138;
    tool_u16 revision_138;
    unsigned int flags_138 : 5;
    unsigned int state_138 : 3;
    const char *name_138;
    const tool_byte *payload_138;
    tool_size payload_length_138;
    struct search_query_138 *next_138;
    void *extension_138[3];
} search_query_138;
typedef union search_ranking_value_138 {
    long signed_value_138;
    unsigned long unsigned_value_138;
    double decimal_value_138;
    const void *pointer_value_138;
} search_ranking_value_138;
typedef int (*search_token_callback_138)(
    struct search_context *, const search_query_138 *, void *);
extern search_status search_token_open_138(
    struct search_context **context, const char *path_138, tool_u32 options_138);
extern search_status search_token_close_138(struct search_context *context);
extern int search_ranking_visit_138(
    struct search_context *context, search_token_callback_138 callback, void *userdata);
extern tool_size search_ranking_count_138(const struct search_context *context);
extern const search_query_138 *search_ranking_find_138(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_138(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_139 {
    SEARCH_QUERY_139_PRIMARY = 1,
    SEARCH_QUERY_139_SECONDARY = 2,
    SEARCH_QUERY_139_ARCHIVED = 4
};
typedef struct search_query_139 {
    tool_u32 id_139;
    tool_u16 revision_139;
    unsigned int flags_139 : 5;
    unsigned int state_139 : 3;
    const char *name_139;
    const tool_byte *payload_139;
    tool_size payload_length_139;
    struct search_query_139 *next_139;
    void *extension_139[3];
} search_query_139;
typedef union search_ranking_value_139 {
    long signed_value_139;
    unsigned long unsigned_value_139;
    double decimal_value_139;
    const void *pointer_value_139;
} search_ranking_value_139;
typedef int (*search_token_callback_139)(
    struct search_context *, const search_query_139 *, void *);
extern search_status search_token_open_139(
    struct search_context **context, const char *path_139, tool_u32 options_139);
extern search_status search_token_close_139(struct search_context *context);
extern int search_ranking_visit_139(
    struct search_context *context, search_token_callback_139 callback, void *userdata);
extern tool_size search_ranking_count_139(const struct search_context *context);
extern const search_query_139 *search_ranking_find_139(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_139(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_140 {
    SEARCH_QUERY_140_PRIMARY = 1,
    SEARCH_QUERY_140_SECONDARY = 2,
    SEARCH_QUERY_140_ARCHIVED = 4
};
typedef struct search_query_140 {
    tool_u32 id_140;
    tool_u16 revision_140;
    unsigned int flags_140 : 5;
    unsigned int state_140 : 3;
    const char *name_140;
    const tool_byte *payload_140;
    tool_size payload_length_140;
    struct search_query_140 *next_140;
    void *extension_140[3];
} search_query_140;
typedef union search_ranking_value_140 {
    long signed_value_140;
    unsigned long unsigned_value_140;
    double decimal_value_140;
    const void *pointer_value_140;
} search_ranking_value_140;
typedef int (*search_token_callback_140)(
    struct search_context *, const search_query_140 *, void *);
extern search_status search_token_open_140(
    struct search_context **context, const char *path_140, tool_u32 options_140);
extern search_status search_token_close_140(struct search_context *context);
extern int search_ranking_visit_140(
    struct search_context *context, search_token_callback_140 callback, void *userdata);
extern tool_size search_ranking_count_140(const struct search_context *context);
extern const search_query_140 *search_ranking_find_140(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_140(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_141 {
    SEARCH_QUERY_141_PRIMARY = 1,
    SEARCH_QUERY_141_SECONDARY = 2,
    SEARCH_QUERY_141_ARCHIVED = 4
};
typedef struct search_query_141 {
    tool_u32 id_141;
    tool_u16 revision_141;
    unsigned int flags_141 : 5;
    unsigned int state_141 : 3;
    const char *name_141;
    const tool_byte *payload_141;
    tool_size payload_length_141;
    struct search_query_141 *next_141;
    void *extension_141[3];
} search_query_141;
typedef union search_ranking_value_141 {
    long signed_value_141;
    unsigned long unsigned_value_141;
    double decimal_value_141;
    const void *pointer_value_141;
} search_ranking_value_141;
typedef int (*search_token_callback_141)(
    struct search_context *, const search_query_141 *, void *);
extern search_status search_token_open_141(
    struct search_context **context, const char *path_141, tool_u32 options_141);
extern search_status search_token_close_141(struct search_context *context);
extern int search_ranking_visit_141(
    struct search_context *context, search_token_callback_141 callback, void *userdata);
extern tool_size search_ranking_count_141(const struct search_context *context);
extern const search_query_141 *search_ranking_find_141(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_141(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_142 {
    SEARCH_QUERY_142_PRIMARY = 1,
    SEARCH_QUERY_142_SECONDARY = 2,
    SEARCH_QUERY_142_ARCHIVED = 4
};
typedef struct search_query_142 {
    tool_u32 id_142;
    tool_u16 revision_142;
    unsigned int flags_142 : 5;
    unsigned int state_142 : 3;
    const char *name_142;
    const tool_byte *payload_142;
    tool_size payload_length_142;
    struct search_query_142 *next_142;
    void *extension_142[3];
} search_query_142;
typedef union search_ranking_value_142 {
    long signed_value_142;
    unsigned long unsigned_value_142;
    double decimal_value_142;
    const void *pointer_value_142;
} search_ranking_value_142;
typedef int (*search_token_callback_142)(
    struct search_context *, const search_query_142 *, void *);
extern search_status search_token_open_142(
    struct search_context **context, const char *path_142, tool_u32 options_142);
extern search_status search_token_close_142(struct search_context *context);
extern int search_ranking_visit_142(
    struct search_context *context, search_token_callback_142 callback, void *userdata);
extern tool_size search_ranking_count_142(const struct search_context *context);
extern const search_query_142 *search_ranking_find_142(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_142(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_143 {
    SEARCH_QUERY_143_PRIMARY = 1,
    SEARCH_QUERY_143_SECONDARY = 2,
    SEARCH_QUERY_143_ARCHIVED = 4
};
typedef struct search_query_143 {
    tool_u32 id_143;
    tool_u16 revision_143;
    unsigned int flags_143 : 5;
    unsigned int state_143 : 3;
    const char *name_143;
    const tool_byte *payload_143;
    tool_size payload_length_143;
    struct search_query_143 *next_143;
    void *extension_143[3];
} search_query_143;
typedef union search_ranking_value_143 {
    long signed_value_143;
    unsigned long unsigned_value_143;
    double decimal_value_143;
    const void *pointer_value_143;
} search_ranking_value_143;
typedef int (*search_token_callback_143)(
    struct search_context *, const search_query_143 *, void *);
extern search_status search_token_open_143(
    struct search_context **context, const char *path_143, tool_u32 options_143);
extern search_status search_token_close_143(struct search_context *context);
extern int search_ranking_visit_143(
    struct search_context *context, search_token_callback_143 callback, void *userdata);
extern tool_size search_ranking_count_143(const struct search_context *context);
extern const search_query_143 *search_ranking_find_143(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_143(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_144 {
    SEARCH_QUERY_144_PRIMARY = 1,
    SEARCH_QUERY_144_SECONDARY = 2,
    SEARCH_QUERY_144_ARCHIVED = 4
};
typedef struct search_query_144 {
    tool_u32 id_144;
    tool_u16 revision_144;
    unsigned int flags_144 : 5;
    unsigned int state_144 : 3;
    const char *name_144;
    const tool_byte *payload_144;
    tool_size payload_length_144;
    struct search_query_144 *next_144;
    void *extension_144[3];
} search_query_144;
typedef union search_ranking_value_144 {
    long signed_value_144;
    unsigned long unsigned_value_144;
    double decimal_value_144;
    const void *pointer_value_144;
} search_ranking_value_144;
typedef int (*search_token_callback_144)(
    struct search_context *, const search_query_144 *, void *);
extern search_status search_token_open_144(
    struct search_context **context, const char *path_144, tool_u32 options_144);
extern search_status search_token_close_144(struct search_context *context);
extern int search_ranking_visit_144(
    struct search_context *context, search_token_callback_144 callback, void *userdata);
extern tool_size search_ranking_count_144(const struct search_context *context);
extern const search_query_144 *search_ranking_find_144(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_144(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_145 {
    SEARCH_QUERY_145_PRIMARY = 1,
    SEARCH_QUERY_145_SECONDARY = 2,
    SEARCH_QUERY_145_ARCHIVED = 4
};
typedef struct search_query_145 {
    tool_u32 id_145;
    tool_u16 revision_145;
    unsigned int flags_145 : 5;
    unsigned int state_145 : 3;
    const char *name_145;
    const tool_byte *payload_145;
    tool_size payload_length_145;
    struct search_query_145 *next_145;
    void *extension_145[3];
} search_query_145;
typedef union search_ranking_value_145 {
    long signed_value_145;
    unsigned long unsigned_value_145;
    double decimal_value_145;
    const void *pointer_value_145;
} search_ranking_value_145;
typedef int (*search_token_callback_145)(
    struct search_context *, const search_query_145 *, void *);
extern search_status search_token_open_145(
    struct search_context **context, const char *path_145, tool_u32 options_145);
extern search_status search_token_close_145(struct search_context *context);
extern int search_ranking_visit_145(
    struct search_context *context, search_token_callback_145 callback, void *userdata);
extern tool_size search_ranking_count_145(const struct search_context *context);
extern const search_query_145 *search_ranking_find_145(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_145(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_146 {
    SEARCH_QUERY_146_PRIMARY = 1,
    SEARCH_QUERY_146_SECONDARY = 2,
    SEARCH_QUERY_146_ARCHIVED = 4
};
typedef struct search_query_146 {
    tool_u32 id_146;
    tool_u16 revision_146;
    unsigned int flags_146 : 5;
    unsigned int state_146 : 3;
    const char *name_146;
    const tool_byte *payload_146;
    tool_size payload_length_146;
    struct search_query_146 *next_146;
    void *extension_146[3];
} search_query_146;
typedef union search_ranking_value_146 {
    long signed_value_146;
    unsigned long unsigned_value_146;
    double decimal_value_146;
    const void *pointer_value_146;
} search_ranking_value_146;
typedef int (*search_token_callback_146)(
    struct search_context *, const search_query_146 *, void *);
extern search_status search_token_open_146(
    struct search_context **context, const char *path_146, tool_u32 options_146);
extern search_status search_token_close_146(struct search_context *context);
extern int search_ranking_visit_146(
    struct search_context *context, search_token_callback_146 callback, void *userdata);
extern tool_size search_ranking_count_146(const struct search_context *context);
extern const search_query_146 *search_ranking_find_146(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_146(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_147 {
    SEARCH_QUERY_147_PRIMARY = 1,
    SEARCH_QUERY_147_SECONDARY = 2,
    SEARCH_QUERY_147_ARCHIVED = 4
};
typedef struct search_query_147 {
    tool_u32 id_147;
    tool_u16 revision_147;
    unsigned int flags_147 : 5;
    unsigned int state_147 : 3;
    const char *name_147;
    const tool_byte *payload_147;
    tool_size payload_length_147;
    struct search_query_147 *next_147;
    void *extension_147[3];
} search_query_147;
typedef union search_ranking_value_147 {
    long signed_value_147;
    unsigned long unsigned_value_147;
    double decimal_value_147;
    const void *pointer_value_147;
} search_ranking_value_147;
typedef int (*search_token_callback_147)(
    struct search_context *, const search_query_147 *, void *);
extern search_status search_token_open_147(
    struct search_context **context, const char *path_147, tool_u32 options_147);
extern search_status search_token_close_147(struct search_context *context);
extern int search_ranking_visit_147(
    struct search_context *context, search_token_callback_147 callback, void *userdata);
extern tool_size search_ranking_count_147(const struct search_context *context);
extern const search_query_147 *search_ranking_find_147(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_147(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_148 {
    SEARCH_QUERY_148_PRIMARY = 1,
    SEARCH_QUERY_148_SECONDARY = 2,
    SEARCH_QUERY_148_ARCHIVED = 4
};
typedef struct search_query_148 {
    tool_u32 id_148;
    tool_u16 revision_148;
    unsigned int flags_148 : 5;
    unsigned int state_148 : 3;
    const char *name_148;
    const tool_byte *payload_148;
    tool_size payload_length_148;
    struct search_query_148 *next_148;
    void *extension_148[3];
} search_query_148;
typedef union search_ranking_value_148 {
    long signed_value_148;
    unsigned long unsigned_value_148;
    double decimal_value_148;
    const void *pointer_value_148;
} search_ranking_value_148;
typedef int (*search_token_callback_148)(
    struct search_context *, const search_query_148 *, void *);
extern search_status search_token_open_148(
    struct search_context **context, const char *path_148, tool_u32 options_148);
extern search_status search_token_close_148(struct search_context *context);
extern int search_ranking_visit_148(
    struct search_context *context, search_token_callback_148 callback, void *userdata);
extern tool_size search_ranking_count_148(const struct search_context *context);
extern const search_query_148 *search_ranking_find_148(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_148(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_149 {
    SEARCH_QUERY_149_PRIMARY = 1,
    SEARCH_QUERY_149_SECONDARY = 2,
    SEARCH_QUERY_149_ARCHIVED = 4
};
typedef struct search_query_149 {
    tool_u32 id_149;
    tool_u16 revision_149;
    unsigned int flags_149 : 5;
    unsigned int state_149 : 3;
    const char *name_149;
    const tool_byte *payload_149;
    tool_size payload_length_149;
    struct search_query_149 *next_149;
    void *extension_149[3];
} search_query_149;
typedef union search_ranking_value_149 {
    long signed_value_149;
    unsigned long unsigned_value_149;
    double decimal_value_149;
    const void *pointer_value_149;
} search_ranking_value_149;
typedef int (*search_token_callback_149)(
    struct search_context *, const search_query_149 *, void *);
extern search_status search_token_open_149(
    struct search_context **context, const char *path_149, tool_u32 options_149);
extern search_status search_token_close_149(struct search_context *context);
extern int search_ranking_visit_149(
    struct search_context *context, search_token_callback_149 callback, void *userdata);
extern tool_size search_ranking_count_149(const struct search_context *context);
extern const search_query_149 *search_ranking_find_149(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_149(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_150 {
    SEARCH_QUERY_150_PRIMARY = 1,
    SEARCH_QUERY_150_SECONDARY = 2,
    SEARCH_QUERY_150_ARCHIVED = 4
};
typedef struct search_query_150 {
    tool_u32 id_150;
    tool_u16 revision_150;
    unsigned int flags_150 : 5;
    unsigned int state_150 : 3;
    const char *name_150;
    const tool_byte *payload_150;
    tool_size payload_length_150;
    struct search_query_150 *next_150;
    void *extension_150[3];
} search_query_150;
typedef union search_ranking_value_150 {
    long signed_value_150;
    unsigned long unsigned_value_150;
    double decimal_value_150;
    const void *pointer_value_150;
} search_ranking_value_150;
typedef int (*search_token_callback_150)(
    struct search_context *, const search_query_150 *, void *);
extern search_status search_token_open_150(
    struct search_context **context, const char *path_150, tool_u32 options_150);
extern search_status search_token_close_150(struct search_context *context);
extern int search_ranking_visit_150(
    struct search_context *context, search_token_callback_150 callback, void *userdata);
extern tool_size search_ranking_count_150(const struct search_context *context);
extern const search_query_150 *search_ranking_find_150(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_150(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_151 {
    SEARCH_QUERY_151_PRIMARY = 1,
    SEARCH_QUERY_151_SECONDARY = 2,
    SEARCH_QUERY_151_ARCHIVED = 4
};
typedef struct search_query_151 {
    tool_u32 id_151;
    tool_u16 revision_151;
    unsigned int flags_151 : 5;
    unsigned int state_151 : 3;
    const char *name_151;
    const tool_byte *payload_151;
    tool_size payload_length_151;
    struct search_query_151 *next_151;
    void *extension_151[3];
} search_query_151;
typedef union search_ranking_value_151 {
    long signed_value_151;
    unsigned long unsigned_value_151;
    double decimal_value_151;
    const void *pointer_value_151;
} search_ranking_value_151;
typedef int (*search_token_callback_151)(
    struct search_context *, const search_query_151 *, void *);
extern search_status search_token_open_151(
    struct search_context **context, const char *path_151, tool_u32 options_151);
extern search_status search_token_close_151(struct search_context *context);
extern int search_ranking_visit_151(
    struct search_context *context, search_token_callback_151 callback, void *userdata);
extern tool_size search_ranking_count_151(const struct search_context *context);
extern const search_query_151 *search_ranking_find_151(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_151(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_152 {
    SEARCH_QUERY_152_PRIMARY = 1,
    SEARCH_QUERY_152_SECONDARY = 2,
    SEARCH_QUERY_152_ARCHIVED = 4
};
typedef struct search_query_152 {
    tool_u32 id_152;
    tool_u16 revision_152;
    unsigned int flags_152 : 5;
    unsigned int state_152 : 3;
    const char *name_152;
    const tool_byte *payload_152;
    tool_size payload_length_152;
    struct search_query_152 *next_152;
    void *extension_152[3];
} search_query_152;
typedef union search_ranking_value_152 {
    long signed_value_152;
    unsigned long unsigned_value_152;
    double decimal_value_152;
    const void *pointer_value_152;
} search_ranking_value_152;
typedef int (*search_token_callback_152)(
    struct search_context *, const search_query_152 *, void *);
extern search_status search_token_open_152(
    struct search_context **context, const char *path_152, tool_u32 options_152);
extern search_status search_token_close_152(struct search_context *context);
extern int search_ranking_visit_152(
    struct search_context *context, search_token_callback_152 callback, void *userdata);
extern tool_size search_ranking_count_152(const struct search_context *context);
extern const search_query_152 *search_ranking_find_152(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_152(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_153 {
    SEARCH_QUERY_153_PRIMARY = 1,
    SEARCH_QUERY_153_SECONDARY = 2,
    SEARCH_QUERY_153_ARCHIVED = 4
};
typedef struct search_query_153 {
    tool_u32 id_153;
    tool_u16 revision_153;
    unsigned int flags_153 : 5;
    unsigned int state_153 : 3;
    const char *name_153;
    const tool_byte *payload_153;
    tool_size payload_length_153;
    struct search_query_153 *next_153;
    void *extension_153[3];
} search_query_153;
typedef union search_ranking_value_153 {
    long signed_value_153;
    unsigned long unsigned_value_153;
    double decimal_value_153;
    const void *pointer_value_153;
} search_ranking_value_153;
typedef int (*search_token_callback_153)(
    struct search_context *, const search_query_153 *, void *);
extern search_status search_token_open_153(
    struct search_context **context, const char *path_153, tool_u32 options_153);
extern search_status search_token_close_153(struct search_context *context);
extern int search_ranking_visit_153(
    struct search_context *context, search_token_callback_153 callback, void *userdata);
extern tool_size search_ranking_count_153(const struct search_context *context);
extern const search_query_153 *search_ranking_find_153(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_153(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_154 {
    SEARCH_QUERY_154_PRIMARY = 1,
    SEARCH_QUERY_154_SECONDARY = 2,
    SEARCH_QUERY_154_ARCHIVED = 4
};
typedef struct search_query_154 {
    tool_u32 id_154;
    tool_u16 revision_154;
    unsigned int flags_154 : 5;
    unsigned int state_154 : 3;
    const char *name_154;
    const tool_byte *payload_154;
    tool_size payload_length_154;
    struct search_query_154 *next_154;
    void *extension_154[3];
} search_query_154;
typedef union search_ranking_value_154 {
    long signed_value_154;
    unsigned long unsigned_value_154;
    double decimal_value_154;
    const void *pointer_value_154;
} search_ranking_value_154;
typedef int (*search_token_callback_154)(
    struct search_context *, const search_query_154 *, void *);
extern search_status search_token_open_154(
    struct search_context **context, const char *path_154, tool_u32 options_154);
extern search_status search_token_close_154(struct search_context *context);
extern int search_ranking_visit_154(
    struct search_context *context, search_token_callback_154 callback, void *userdata);
extern tool_size search_ranking_count_154(const struct search_context *context);
extern const search_query_154 *search_ranking_find_154(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_154(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_155 {
    SEARCH_QUERY_155_PRIMARY = 1,
    SEARCH_QUERY_155_SECONDARY = 2,
    SEARCH_QUERY_155_ARCHIVED = 4
};
typedef struct search_query_155 {
    tool_u32 id_155;
    tool_u16 revision_155;
    unsigned int flags_155 : 5;
    unsigned int state_155 : 3;
    const char *name_155;
    const tool_byte *payload_155;
    tool_size payload_length_155;
    struct search_query_155 *next_155;
    void *extension_155[3];
} search_query_155;
typedef union search_ranking_value_155 {
    long signed_value_155;
    unsigned long unsigned_value_155;
    double decimal_value_155;
    const void *pointer_value_155;
} search_ranking_value_155;
typedef int (*search_token_callback_155)(
    struct search_context *, const search_query_155 *, void *);
extern search_status search_token_open_155(
    struct search_context **context, const char *path_155, tool_u32 options_155);
extern search_status search_token_close_155(struct search_context *context);
extern int search_ranking_visit_155(
    struct search_context *context, search_token_callback_155 callback, void *userdata);
extern tool_size search_ranking_count_155(const struct search_context *context);
extern const search_query_155 *search_ranking_find_155(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_155(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_156 {
    SEARCH_QUERY_156_PRIMARY = 1,
    SEARCH_QUERY_156_SECONDARY = 2,
    SEARCH_QUERY_156_ARCHIVED = 4
};
typedef struct search_query_156 {
    tool_u32 id_156;
    tool_u16 revision_156;
    unsigned int flags_156 : 5;
    unsigned int state_156 : 3;
    const char *name_156;
    const tool_byte *payload_156;
    tool_size payload_length_156;
    struct search_query_156 *next_156;
    void *extension_156[3];
} search_query_156;
typedef union search_ranking_value_156 {
    long signed_value_156;
    unsigned long unsigned_value_156;
    double decimal_value_156;
    const void *pointer_value_156;
} search_ranking_value_156;
typedef int (*search_token_callback_156)(
    struct search_context *, const search_query_156 *, void *);
extern search_status search_token_open_156(
    struct search_context **context, const char *path_156, tool_u32 options_156);
extern search_status search_token_close_156(struct search_context *context);
extern int search_ranking_visit_156(
    struct search_context *context, search_token_callback_156 callback, void *userdata);
extern tool_size search_ranking_count_156(const struct search_context *context);
extern const search_query_156 *search_ranking_find_156(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_156(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_157 {
    SEARCH_QUERY_157_PRIMARY = 1,
    SEARCH_QUERY_157_SECONDARY = 2,
    SEARCH_QUERY_157_ARCHIVED = 4
};
typedef struct search_query_157 {
    tool_u32 id_157;
    tool_u16 revision_157;
    unsigned int flags_157 : 5;
    unsigned int state_157 : 3;
    const char *name_157;
    const tool_byte *payload_157;
    tool_size payload_length_157;
    struct search_query_157 *next_157;
    void *extension_157[3];
} search_query_157;
typedef union search_ranking_value_157 {
    long signed_value_157;
    unsigned long unsigned_value_157;
    double decimal_value_157;
    const void *pointer_value_157;
} search_ranking_value_157;
typedef int (*search_token_callback_157)(
    struct search_context *, const search_query_157 *, void *);
extern search_status search_token_open_157(
    struct search_context **context, const char *path_157, tool_u32 options_157);
extern search_status search_token_close_157(struct search_context *context);
extern int search_ranking_visit_157(
    struct search_context *context, search_token_callback_157 callback, void *userdata);
extern tool_size search_ranking_count_157(const struct search_context *context);
extern const search_query_157 *search_ranking_find_157(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_157(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_158 {
    SEARCH_QUERY_158_PRIMARY = 1,
    SEARCH_QUERY_158_SECONDARY = 2,
    SEARCH_QUERY_158_ARCHIVED = 4
};
typedef struct search_query_158 {
    tool_u32 id_158;
    tool_u16 revision_158;
    unsigned int flags_158 : 5;
    unsigned int state_158 : 3;
    const char *name_158;
    const tool_byte *payload_158;
    tool_size payload_length_158;
    struct search_query_158 *next_158;
    void *extension_158[3];
} search_query_158;
typedef union search_ranking_value_158 {
    long signed_value_158;
    unsigned long unsigned_value_158;
    double decimal_value_158;
    const void *pointer_value_158;
} search_ranking_value_158;
typedef int (*search_token_callback_158)(
    struct search_context *, const search_query_158 *, void *);
extern search_status search_token_open_158(
    struct search_context **context, const char *path_158, tool_u32 options_158);
extern search_status search_token_close_158(struct search_context *context);
extern int search_ranking_visit_158(
    struct search_context *context, search_token_callback_158 callback, void *userdata);
extern tool_size search_ranking_count_158(const struct search_context *context);
extern const search_query_158 *search_ranking_find_158(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_158(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_159 {
    SEARCH_QUERY_159_PRIMARY = 1,
    SEARCH_QUERY_159_SECONDARY = 2,
    SEARCH_QUERY_159_ARCHIVED = 4
};
typedef struct search_query_159 {
    tool_u32 id_159;
    tool_u16 revision_159;
    unsigned int flags_159 : 5;
    unsigned int state_159 : 3;
    const char *name_159;
    const tool_byte *payload_159;
    tool_size payload_length_159;
    struct search_query_159 *next_159;
    void *extension_159[3];
} search_query_159;
typedef union search_ranking_value_159 {
    long signed_value_159;
    unsigned long unsigned_value_159;
    double decimal_value_159;
    const void *pointer_value_159;
} search_ranking_value_159;
typedef int (*search_token_callback_159)(
    struct search_context *, const search_query_159 *, void *);
extern search_status search_token_open_159(
    struct search_context **context, const char *path_159, tool_u32 options_159);
extern search_status search_token_close_159(struct search_context *context);
extern int search_ranking_visit_159(
    struct search_context *context, search_token_callback_159 callback, void *userdata);
extern tool_size search_ranking_count_159(const struct search_context *context);
extern const search_query_159 *search_ranking_find_159(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_159(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_160 {
    SEARCH_QUERY_160_PRIMARY = 1,
    SEARCH_QUERY_160_SECONDARY = 2,
    SEARCH_QUERY_160_ARCHIVED = 4
};
typedef struct search_query_160 {
    tool_u32 id_160;
    tool_u16 revision_160;
    unsigned int flags_160 : 5;
    unsigned int state_160 : 3;
    const char *name_160;
    const tool_byte *payload_160;
    tool_size payload_length_160;
    struct search_query_160 *next_160;
    void *extension_160[3];
} search_query_160;
typedef union search_ranking_value_160 {
    long signed_value_160;
    unsigned long unsigned_value_160;
    double decimal_value_160;
    const void *pointer_value_160;
} search_ranking_value_160;
typedef int (*search_token_callback_160)(
    struct search_context *, const search_query_160 *, void *);
extern search_status search_token_open_160(
    struct search_context **context, const char *path_160, tool_u32 options_160);
extern search_status search_token_close_160(struct search_context *context);
extern int search_ranking_visit_160(
    struct search_context *context, search_token_callback_160 callback, void *userdata);
extern tool_size search_ranking_count_160(const struct search_context *context);
extern const search_query_160 *search_ranking_find_160(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_160(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_161 {
    SEARCH_QUERY_161_PRIMARY = 1,
    SEARCH_QUERY_161_SECONDARY = 2,
    SEARCH_QUERY_161_ARCHIVED = 4
};
typedef struct search_query_161 {
    tool_u32 id_161;
    tool_u16 revision_161;
    unsigned int flags_161 : 5;
    unsigned int state_161 : 3;
    const char *name_161;
    const tool_byte *payload_161;
    tool_size payload_length_161;
    struct search_query_161 *next_161;
    void *extension_161[3];
} search_query_161;
typedef union search_ranking_value_161 {
    long signed_value_161;
    unsigned long unsigned_value_161;
    double decimal_value_161;
    const void *pointer_value_161;
} search_ranking_value_161;
typedef int (*search_token_callback_161)(
    struct search_context *, const search_query_161 *, void *);
extern search_status search_token_open_161(
    struct search_context **context, const char *path_161, tool_u32 options_161);
extern search_status search_token_close_161(struct search_context *context);
extern int search_ranking_visit_161(
    struct search_context *context, search_token_callback_161 callback, void *userdata);
extern tool_size search_ranking_count_161(const struct search_context *context);
extern const search_query_161 *search_ranking_find_161(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_161(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_162 {
    SEARCH_QUERY_162_PRIMARY = 1,
    SEARCH_QUERY_162_SECONDARY = 2,
    SEARCH_QUERY_162_ARCHIVED = 4
};
typedef struct search_query_162 {
    tool_u32 id_162;
    tool_u16 revision_162;
    unsigned int flags_162 : 5;
    unsigned int state_162 : 3;
    const char *name_162;
    const tool_byte *payload_162;
    tool_size payload_length_162;
    struct search_query_162 *next_162;
    void *extension_162[3];
} search_query_162;
typedef union search_ranking_value_162 {
    long signed_value_162;
    unsigned long unsigned_value_162;
    double decimal_value_162;
    const void *pointer_value_162;
} search_ranking_value_162;
typedef int (*search_token_callback_162)(
    struct search_context *, const search_query_162 *, void *);
extern search_status search_token_open_162(
    struct search_context **context, const char *path_162, tool_u32 options_162);
extern search_status search_token_close_162(struct search_context *context);
extern int search_ranking_visit_162(
    struct search_context *context, search_token_callback_162 callback, void *userdata);
extern tool_size search_ranking_count_162(const struct search_context *context);
extern const search_query_162 *search_ranking_find_162(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_162(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_163 {
    SEARCH_QUERY_163_PRIMARY = 1,
    SEARCH_QUERY_163_SECONDARY = 2,
    SEARCH_QUERY_163_ARCHIVED = 4
};
typedef struct search_query_163 {
    tool_u32 id_163;
    tool_u16 revision_163;
    unsigned int flags_163 : 5;
    unsigned int state_163 : 3;
    const char *name_163;
    const tool_byte *payload_163;
    tool_size payload_length_163;
    struct search_query_163 *next_163;
    void *extension_163[3];
} search_query_163;
typedef union search_ranking_value_163 {
    long signed_value_163;
    unsigned long unsigned_value_163;
    double decimal_value_163;
    const void *pointer_value_163;
} search_ranking_value_163;
typedef int (*search_token_callback_163)(
    struct search_context *, const search_query_163 *, void *);
extern search_status search_token_open_163(
    struct search_context **context, const char *path_163, tool_u32 options_163);
extern search_status search_token_close_163(struct search_context *context);
extern int search_ranking_visit_163(
    struct search_context *context, search_token_callback_163 callback, void *userdata);
extern tool_size search_ranking_count_163(const struct search_context *context);
extern const search_query_163 *search_ranking_find_163(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_163(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_164 {
    SEARCH_QUERY_164_PRIMARY = 1,
    SEARCH_QUERY_164_SECONDARY = 2,
    SEARCH_QUERY_164_ARCHIVED = 4
};
typedef struct search_query_164 {
    tool_u32 id_164;
    tool_u16 revision_164;
    unsigned int flags_164 : 5;
    unsigned int state_164 : 3;
    const char *name_164;
    const tool_byte *payload_164;
    tool_size payload_length_164;
    struct search_query_164 *next_164;
    void *extension_164[3];
} search_query_164;
typedef union search_ranking_value_164 {
    long signed_value_164;
    unsigned long unsigned_value_164;
    double decimal_value_164;
    const void *pointer_value_164;
} search_ranking_value_164;
typedef int (*search_token_callback_164)(
    struct search_context *, const search_query_164 *, void *);
extern search_status search_token_open_164(
    struct search_context **context, const char *path_164, tool_u32 options_164);
extern search_status search_token_close_164(struct search_context *context);
extern int search_ranking_visit_164(
    struct search_context *context, search_token_callback_164 callback, void *userdata);
extern tool_size search_ranking_count_164(const struct search_context *context);
extern const search_query_164 *search_ranking_find_164(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_164(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_165 {
    SEARCH_QUERY_165_PRIMARY = 1,
    SEARCH_QUERY_165_SECONDARY = 2,
    SEARCH_QUERY_165_ARCHIVED = 4
};
typedef struct search_query_165 {
    tool_u32 id_165;
    tool_u16 revision_165;
    unsigned int flags_165 : 5;
    unsigned int state_165 : 3;
    const char *name_165;
    const tool_byte *payload_165;
    tool_size payload_length_165;
    struct search_query_165 *next_165;
    void *extension_165[3];
} search_query_165;
typedef union search_ranking_value_165 {
    long signed_value_165;
    unsigned long unsigned_value_165;
    double decimal_value_165;
    const void *pointer_value_165;
} search_ranking_value_165;
typedef int (*search_token_callback_165)(
    struct search_context *, const search_query_165 *, void *);
extern search_status search_token_open_165(
    struct search_context **context, const char *path_165, tool_u32 options_165);
extern search_status search_token_close_165(struct search_context *context);
extern int search_ranking_visit_165(
    struct search_context *context, search_token_callback_165 callback, void *userdata);
extern tool_size search_ranking_count_165(const struct search_context *context);
extern const search_query_165 *search_ranking_find_165(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_165(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_166 {
    SEARCH_QUERY_166_PRIMARY = 1,
    SEARCH_QUERY_166_SECONDARY = 2,
    SEARCH_QUERY_166_ARCHIVED = 4
};
typedef struct search_query_166 {
    tool_u32 id_166;
    tool_u16 revision_166;
    unsigned int flags_166 : 5;
    unsigned int state_166 : 3;
    const char *name_166;
    const tool_byte *payload_166;
    tool_size payload_length_166;
    struct search_query_166 *next_166;
    void *extension_166[3];
} search_query_166;
typedef union search_ranking_value_166 {
    long signed_value_166;
    unsigned long unsigned_value_166;
    double decimal_value_166;
    const void *pointer_value_166;
} search_ranking_value_166;
typedef int (*search_token_callback_166)(
    struct search_context *, const search_query_166 *, void *);
extern search_status search_token_open_166(
    struct search_context **context, const char *path_166, tool_u32 options_166);
extern search_status search_token_close_166(struct search_context *context);
extern int search_ranking_visit_166(
    struct search_context *context, search_token_callback_166 callback, void *userdata);
extern tool_size search_ranking_count_166(const struct search_context *context);
extern const search_query_166 *search_ranking_find_166(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_166(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_167 {
    SEARCH_QUERY_167_PRIMARY = 1,
    SEARCH_QUERY_167_SECONDARY = 2,
    SEARCH_QUERY_167_ARCHIVED = 4
};
typedef struct search_query_167 {
    tool_u32 id_167;
    tool_u16 revision_167;
    unsigned int flags_167 : 5;
    unsigned int state_167 : 3;
    const char *name_167;
    const tool_byte *payload_167;
    tool_size payload_length_167;
    struct search_query_167 *next_167;
    void *extension_167[3];
} search_query_167;
typedef union search_ranking_value_167 {
    long signed_value_167;
    unsigned long unsigned_value_167;
    double decimal_value_167;
    const void *pointer_value_167;
} search_ranking_value_167;
typedef int (*search_token_callback_167)(
    struct search_context *, const search_query_167 *, void *);
extern search_status search_token_open_167(
    struct search_context **context, const char *path_167, tool_u32 options_167);
extern search_status search_token_close_167(struct search_context *context);
extern int search_ranking_visit_167(
    struct search_context *context, search_token_callback_167 callback, void *userdata);
extern tool_size search_ranking_count_167(const struct search_context *context);
extern const search_query_167 *search_ranking_find_167(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_167(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_168 {
    SEARCH_QUERY_168_PRIMARY = 1,
    SEARCH_QUERY_168_SECONDARY = 2,
    SEARCH_QUERY_168_ARCHIVED = 4
};
typedef struct search_query_168 {
    tool_u32 id_168;
    tool_u16 revision_168;
    unsigned int flags_168 : 5;
    unsigned int state_168 : 3;
    const char *name_168;
    const tool_byte *payload_168;
    tool_size payload_length_168;
    struct search_query_168 *next_168;
    void *extension_168[3];
} search_query_168;
typedef union search_ranking_value_168 {
    long signed_value_168;
    unsigned long unsigned_value_168;
    double decimal_value_168;
    const void *pointer_value_168;
} search_ranking_value_168;
typedef int (*search_token_callback_168)(
    struct search_context *, const search_query_168 *, void *);
extern search_status search_token_open_168(
    struct search_context **context, const char *path_168, tool_u32 options_168);
extern search_status search_token_close_168(struct search_context *context);
extern int search_ranking_visit_168(
    struct search_context *context, search_token_callback_168 callback, void *userdata);
extern tool_size search_ranking_count_168(const struct search_context *context);
extern const search_query_168 *search_ranking_find_168(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_168(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_169 {
    SEARCH_QUERY_169_PRIMARY = 1,
    SEARCH_QUERY_169_SECONDARY = 2,
    SEARCH_QUERY_169_ARCHIVED = 4
};
typedef struct search_query_169 {
    tool_u32 id_169;
    tool_u16 revision_169;
    unsigned int flags_169 : 5;
    unsigned int state_169 : 3;
    const char *name_169;
    const tool_byte *payload_169;
    tool_size payload_length_169;
    struct search_query_169 *next_169;
    void *extension_169[3];
} search_query_169;
typedef union search_ranking_value_169 {
    long signed_value_169;
    unsigned long unsigned_value_169;
    double decimal_value_169;
    const void *pointer_value_169;
} search_ranking_value_169;
typedef int (*search_token_callback_169)(
    struct search_context *, const search_query_169 *, void *);
extern search_status search_token_open_169(
    struct search_context **context, const char *path_169, tool_u32 options_169);
extern search_status search_token_close_169(struct search_context *context);
extern int search_ranking_visit_169(
    struct search_context *context, search_token_callback_169 callback, void *userdata);
extern tool_size search_ranking_count_169(const struct search_context *context);
extern const search_query_169 *search_ranking_find_169(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_169(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_170 {
    SEARCH_QUERY_170_PRIMARY = 1,
    SEARCH_QUERY_170_SECONDARY = 2,
    SEARCH_QUERY_170_ARCHIVED = 4
};
typedef struct search_query_170 {
    tool_u32 id_170;
    tool_u16 revision_170;
    unsigned int flags_170 : 5;
    unsigned int state_170 : 3;
    const char *name_170;
    const tool_byte *payload_170;
    tool_size payload_length_170;
    struct search_query_170 *next_170;
    void *extension_170[3];
} search_query_170;
typedef union search_ranking_value_170 {
    long signed_value_170;
    unsigned long unsigned_value_170;
    double decimal_value_170;
    const void *pointer_value_170;
} search_ranking_value_170;
typedef int (*search_token_callback_170)(
    struct search_context *, const search_query_170 *, void *);
extern search_status search_token_open_170(
    struct search_context **context, const char *path_170, tool_u32 options_170);
extern search_status search_token_close_170(struct search_context *context);
extern int search_ranking_visit_170(
    struct search_context *context, search_token_callback_170 callback, void *userdata);
extern tool_size search_ranking_count_170(const struct search_context *context);
extern const search_query_170 *search_ranking_find_170(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_170(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_171 {
    SEARCH_QUERY_171_PRIMARY = 1,
    SEARCH_QUERY_171_SECONDARY = 2,
    SEARCH_QUERY_171_ARCHIVED = 4
};
typedef struct search_query_171 {
    tool_u32 id_171;
    tool_u16 revision_171;
    unsigned int flags_171 : 5;
    unsigned int state_171 : 3;
    const char *name_171;
    const tool_byte *payload_171;
    tool_size payload_length_171;
    struct search_query_171 *next_171;
    void *extension_171[3];
} search_query_171;
typedef union search_ranking_value_171 {
    long signed_value_171;
    unsigned long unsigned_value_171;
    double decimal_value_171;
    const void *pointer_value_171;
} search_ranking_value_171;
typedef int (*search_token_callback_171)(
    struct search_context *, const search_query_171 *, void *);
extern search_status search_token_open_171(
    struct search_context **context, const char *path_171, tool_u32 options_171);
extern search_status search_token_close_171(struct search_context *context);
extern int search_ranking_visit_171(
    struct search_context *context, search_token_callback_171 callback, void *userdata);
extern tool_size search_ranking_count_171(const struct search_context *context);
extern const search_query_171 *search_ranking_find_171(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_171(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_172 {
    SEARCH_QUERY_172_PRIMARY = 1,
    SEARCH_QUERY_172_SECONDARY = 2,
    SEARCH_QUERY_172_ARCHIVED = 4
};
typedef struct search_query_172 {
    tool_u32 id_172;
    tool_u16 revision_172;
    unsigned int flags_172 : 5;
    unsigned int state_172 : 3;
    const char *name_172;
    const tool_byte *payload_172;
    tool_size payload_length_172;
    struct search_query_172 *next_172;
    void *extension_172[3];
} search_query_172;
typedef union search_ranking_value_172 {
    long signed_value_172;
    unsigned long unsigned_value_172;
    double decimal_value_172;
    const void *pointer_value_172;
} search_ranking_value_172;
typedef int (*search_token_callback_172)(
    struct search_context *, const search_query_172 *, void *);
extern search_status search_token_open_172(
    struct search_context **context, const char *path_172, tool_u32 options_172);
extern search_status search_token_close_172(struct search_context *context);
extern int search_ranking_visit_172(
    struct search_context *context, search_token_callback_172 callback, void *userdata);
extern tool_size search_ranking_count_172(const struct search_context *context);
extern const search_query_172 *search_ranking_find_172(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_172(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_173 {
    SEARCH_QUERY_173_PRIMARY = 1,
    SEARCH_QUERY_173_SECONDARY = 2,
    SEARCH_QUERY_173_ARCHIVED = 4
};
typedef struct search_query_173 {
    tool_u32 id_173;
    tool_u16 revision_173;
    unsigned int flags_173 : 5;
    unsigned int state_173 : 3;
    const char *name_173;
    const tool_byte *payload_173;
    tool_size payload_length_173;
    struct search_query_173 *next_173;
    void *extension_173[3];
} search_query_173;
typedef union search_ranking_value_173 {
    long signed_value_173;
    unsigned long unsigned_value_173;
    double decimal_value_173;
    const void *pointer_value_173;
} search_ranking_value_173;
typedef int (*search_token_callback_173)(
    struct search_context *, const search_query_173 *, void *);
extern search_status search_token_open_173(
    struct search_context **context, const char *path_173, tool_u32 options_173);
extern search_status search_token_close_173(struct search_context *context);
extern int search_ranking_visit_173(
    struct search_context *context, search_token_callback_173 callback, void *userdata);
extern tool_size search_ranking_count_173(const struct search_context *context);
extern const search_query_173 *search_ranking_find_173(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_173(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_174 {
    SEARCH_QUERY_174_PRIMARY = 1,
    SEARCH_QUERY_174_SECONDARY = 2,
    SEARCH_QUERY_174_ARCHIVED = 4
};
typedef struct search_query_174 {
    tool_u32 id_174;
    tool_u16 revision_174;
    unsigned int flags_174 : 5;
    unsigned int state_174 : 3;
    const char *name_174;
    const tool_byte *payload_174;
    tool_size payload_length_174;
    struct search_query_174 *next_174;
    void *extension_174[3];
} search_query_174;
typedef union search_ranking_value_174 {
    long signed_value_174;
    unsigned long unsigned_value_174;
    double decimal_value_174;
    const void *pointer_value_174;
} search_ranking_value_174;
typedef int (*search_token_callback_174)(
    struct search_context *, const search_query_174 *, void *);
extern search_status search_token_open_174(
    struct search_context **context, const char *path_174, tool_u32 options_174);
extern search_status search_token_close_174(struct search_context *context);
extern int search_ranking_visit_174(
    struct search_context *context, search_token_callback_174 callback, void *userdata);
extern tool_size search_ranking_count_174(const struct search_context *context);
extern const search_query_174 *search_ranking_find_174(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_174(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_175 {
    SEARCH_QUERY_175_PRIMARY = 1,
    SEARCH_QUERY_175_SECONDARY = 2,
    SEARCH_QUERY_175_ARCHIVED = 4
};
typedef struct search_query_175 {
    tool_u32 id_175;
    tool_u16 revision_175;
    unsigned int flags_175 : 5;
    unsigned int state_175 : 3;
    const char *name_175;
    const tool_byte *payload_175;
    tool_size payload_length_175;
    struct search_query_175 *next_175;
    void *extension_175[3];
} search_query_175;
typedef union search_ranking_value_175 {
    long signed_value_175;
    unsigned long unsigned_value_175;
    double decimal_value_175;
    const void *pointer_value_175;
} search_ranking_value_175;
typedef int (*search_token_callback_175)(
    struct search_context *, const search_query_175 *, void *);
extern search_status search_token_open_175(
    struct search_context **context, const char *path_175, tool_u32 options_175);
extern search_status search_token_close_175(struct search_context *context);
extern int search_ranking_visit_175(
    struct search_context *context, search_token_callback_175 callback, void *userdata);
extern tool_size search_ranking_count_175(const struct search_context *context);
extern const search_query_175 *search_ranking_find_175(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_175(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_176 {
    SEARCH_QUERY_176_PRIMARY = 1,
    SEARCH_QUERY_176_SECONDARY = 2,
    SEARCH_QUERY_176_ARCHIVED = 4
};
typedef struct search_query_176 {
    tool_u32 id_176;
    tool_u16 revision_176;
    unsigned int flags_176 : 5;
    unsigned int state_176 : 3;
    const char *name_176;
    const tool_byte *payload_176;
    tool_size payload_length_176;
    struct search_query_176 *next_176;
    void *extension_176[3];
} search_query_176;
typedef union search_ranking_value_176 {
    long signed_value_176;
    unsigned long unsigned_value_176;
    double decimal_value_176;
    const void *pointer_value_176;
} search_ranking_value_176;
typedef int (*search_token_callback_176)(
    struct search_context *, const search_query_176 *, void *);
extern search_status search_token_open_176(
    struct search_context **context, const char *path_176, tool_u32 options_176);
extern search_status search_token_close_176(struct search_context *context);
extern int search_ranking_visit_176(
    struct search_context *context, search_token_callback_176 callback, void *userdata);
extern tool_size search_ranking_count_176(const struct search_context *context);
extern const search_query_176 *search_ranking_find_176(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_176(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_177 {
    SEARCH_QUERY_177_PRIMARY = 1,
    SEARCH_QUERY_177_SECONDARY = 2,
    SEARCH_QUERY_177_ARCHIVED = 4
};
typedef struct search_query_177 {
    tool_u32 id_177;
    tool_u16 revision_177;
    unsigned int flags_177 : 5;
    unsigned int state_177 : 3;
    const char *name_177;
    const tool_byte *payload_177;
    tool_size payload_length_177;
    struct search_query_177 *next_177;
    void *extension_177[3];
} search_query_177;
typedef union search_ranking_value_177 {
    long signed_value_177;
    unsigned long unsigned_value_177;
    double decimal_value_177;
    const void *pointer_value_177;
} search_ranking_value_177;
typedef int (*search_token_callback_177)(
    struct search_context *, const search_query_177 *, void *);
extern search_status search_token_open_177(
    struct search_context **context, const char *path_177, tool_u32 options_177);
extern search_status search_token_close_177(struct search_context *context);
extern int search_ranking_visit_177(
    struct search_context *context, search_token_callback_177 callback, void *userdata);
extern tool_size search_ranking_count_177(const struct search_context *context);
extern const search_query_177 *search_ranking_find_177(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_177(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_178 {
    SEARCH_QUERY_178_PRIMARY = 1,
    SEARCH_QUERY_178_SECONDARY = 2,
    SEARCH_QUERY_178_ARCHIVED = 4
};
typedef struct search_query_178 {
    tool_u32 id_178;
    tool_u16 revision_178;
    unsigned int flags_178 : 5;
    unsigned int state_178 : 3;
    const char *name_178;
    const tool_byte *payload_178;
    tool_size payload_length_178;
    struct search_query_178 *next_178;
    void *extension_178[3];
} search_query_178;
typedef union search_ranking_value_178 {
    long signed_value_178;
    unsigned long unsigned_value_178;
    double decimal_value_178;
    const void *pointer_value_178;
} search_ranking_value_178;
typedef int (*search_token_callback_178)(
    struct search_context *, const search_query_178 *, void *);
extern search_status search_token_open_178(
    struct search_context **context, const char *path_178, tool_u32 options_178);
extern search_status search_token_close_178(struct search_context *context);
extern int search_ranking_visit_178(
    struct search_context *context, search_token_callback_178 callback, void *userdata);
extern tool_size search_ranking_count_178(const struct search_context *context);
extern const search_query_178 *search_ranking_find_178(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_178(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

enum search_query_class_179 {
    SEARCH_QUERY_179_PRIMARY = 1,
    SEARCH_QUERY_179_SECONDARY = 2,
    SEARCH_QUERY_179_ARCHIVED = 4
};
typedef struct search_query_179 {
    tool_u32 id_179;
    tool_u16 revision_179;
    unsigned int flags_179 : 5;
    unsigned int state_179 : 3;
    const char *name_179;
    const tool_byte *payload_179;
    tool_size payload_length_179;
    struct search_query_179 *next_179;
    void *extension_179[3];
} search_query_179;
typedef union search_ranking_value_179 {
    long signed_value_179;
    unsigned long unsigned_value_179;
    double decimal_value_179;
    const void *pointer_value_179;
} search_ranking_value_179;
typedef int (*search_token_callback_179)(
    struct search_context *, const search_query_179 *, void *);
extern search_status search_token_open_179(
    struct search_context **context, const char *path_179, tool_u32 options_179);
extern search_status search_token_close_179(struct search_context *context);
extern int search_ranking_visit_179(
    struct search_context *context, search_token_callback_179 callback, void *userdata);
extern tool_size search_ranking_count_179(const struct search_context *context);
extern const search_query_179 *search_ranking_find_179(
    const struct search_context *context, tool_u32 identifier, struct search_cursor *cursor);
static tool_u32 search_ranking_mix_179(tool_u32 value) {
    value ^= value >> 16;
    value *= 0x7feb352dU;
    value ^= value >> 15;
    value *= 0x846ca68bU;
    return value ^ (value >> 16);
}

typedef struct search_context {
    tool_size capacity;
    tool_size active;
    tool_u32 generation;
    tool_u32 flags;
    void *allocator_state;
    search_visit_fn visitor;
    search_release_fn release;
} search_context;
typedef struct search_cursor {
    tool_size position;
    tool_size limit;
    tool_u32 generation;
    tool_u32 direction;
} search_cursor;
extern search_status search_context_reset(struct search_context *context);
extern search_status search_context_validate(const struct search_context *context);
extern int search_compare_bytes(const void *left, const void *right, tool_size length);
static tool_size search_clamp_length(tool_size requested, tool_size available) {
    if (requested > available) {
        return available;
    }
    return requested;
}
