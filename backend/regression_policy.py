from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


POLICY_SOURCE = "backend/MODERN_TLS_POLICY.md"
EXPECTED_SSL_TEST_COUNT = 219
_FULL_SSL_PROGRESS = re.compile(
    r"^.*\[[^\]\n]+\]\s+test_ssl (?:(?:failed \((\d+) errors?, (\d+) failures?\))|passed)(?:\s|$)",
    re.MULTILINE,
)
_SSL_BLOCK_END = re.compile(r"^test test_ssl (?:failed|passed)$", re.MULTILINE)

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_RESULT_BLOCK = re.compile(
    r"^(FAIL|ERROR): ([^\n]+)\n-+\n(.*?)(?=^(?:FAIL|ERROR): |\Z)",
    re.MULTILINE | re.DOTALL,
)
_RUN = re.compile(r"^Ran ([0-9,]+) tests in ([0-9]+(?:\.[0-9]+)?s)$", re.MULTILINE)
_FAILED = re.compile(r"^FAILED \(([^\n]*)\)$", re.MULTILINE)
_OK = re.compile(r"^OK(?: \(([^\n]*)\))?$", re.MULTILINE)
_TOTAL_TESTS = re.compile(r"^Total tests: ([^\n]+)$", re.MULTILINE)
_TOTAL_FILES = re.compile(r"^Total test files: ([^\n]+)$", re.MULTILINE)
_RESULT = re.compile(r"^Result: (SUCCESS|FAILURE)$", re.MULTILINE)
_SKIP_LINE = re.compile(r"^.*\.\.\. skipped(?: .*)?$", re.MULTILINE)
_FAILED_FILES = re.compile(
    r"^(\d+) tests? failed:\n((?:[ \t]+\S.*(?:\n|$))+)", re.MULTILINE
)
_COUNT_FIELD = re.compile(r"^([a-z_]+)=([0-9,]+)$")
_BACKEND = re.compile(r"^test_ssl: testing with 'Rustls [^\n]+'", re.MULTILINE)


@dataclass(frozen=True)
class _ExpectedFailure:
    reason: str
    signatures: tuple[tuple[str, ...], ...]


def _signature(*patterns: str) -> tuple[tuple[str, ...], ...]:
    return (patterns,)


def _dh_signatures(test_line: int) -> tuple[tuple[str, ...], ...]:
    source = rf'test_ssl\.py", line {test_line}, in '
    return (
        (
            source,
            r"AttributeError: 'SSLContext' object has no attribute 'load_dh_params'",
        ),
        (
            source,
            r"NotImplementedError: Finite-field DH is outside the modern TLS policy",
        ),
    )


_EXPECTED: dict[tuple[str, str], _ExpectedFailure] = {
    (
        "ERROR",
        "test_random (test.test_ssl.BasicSocketTests.test_random)",
    ): _ExpectedFailure(
        "RAND_add entropy injection is unsupported by the selected random source; random-byte generation and status remain separately tested.",
        _signature(
            r'test_ssl\.py", line 509, in test_random',
            r'ssl\.RAND_add\("this is a random string", 75\.0\)',
            r"NotImplementedError: RAND_add entropy injection is unsupported by the selected random source",
        ),
    ),
    (
        "ERROR",
        "test_load_dh_params (test.test_ssl.ContextTests.test_load_dh_params)",
    ): _ExpectedFailure(
        "finite-field DH is retired by the modern TLS policy and is rejected explicitly.",
        _dh_signatures(1536),
    ),
    (
        "ERROR",
        "test_options (test.test_ssl.ContextTests.test_options)",
    ): _ExpectedFailure(
        "clearing the option word requests changes to unsupported TLS behaviors; the setter rejects the exact change atomically.",
        _signature(
            r'test_ssl\.py", line 1162, in test_options',
            r"ctx\.options = 0",
            r"NotImplementedError: RTLS cannot apply SSL option changes 0x80120050",
        ),
    ),
    (
        "ERROR",
        "test_verify_flags (test.test_ssl.ContextTests.test_verify_flags)",
    ): _ExpectedFailure(
        "proxy-certificate verification is unsupported and the setter fails explicitly.",
        _signature(
            r'test_ssl\.py", line 1327, in test_verify_flags',
            r"ctx\.verify_flags = ssl\.VERIFY_ALLOW_PROXY_CERTS",
            r"NotImplementedError: Unsupported certificate verification flags",
        ),
    ),
    (
        "ERROR",
        "test_lib_reason (test.test_ssl.SSLErrorTests.test_lib_reason)",
    ): _ExpectedFailure(
        "the test uses load_dh_params to probe OpenSSL PEM parser errors, but finite-field DH is outside the modern TLS policy.",
        _dh_signatures(2055),
    ),
    (
        "ERROR",
        "test_legacy_server_connect (test.test_ssl.ThreadedTests.test_legacy_server_connect)",
    ): _ExpectedFailure(
        "unsafe legacy server-connect behavior is retired; the option setter rejects the request.",
        _signature(
            r'test_ssl\.py", line 4694, in test_legacy_server_connect',
            r"client_context\.options \|= ssl\.OP_LEGACY_SERVER_CONNECT",
            r"NotImplementedError: RTLS cannot apply SSL option changes 0x4",
        ),
    ),
    (
        "FAIL",
        "test_openssl_version (test.test_ssl.BasicSocketTests.test_openssl_version)",
    ): _ExpectedFailure(
        "the upstream assertion requires an OpenSSL version tuple; the backend reports Rustls truthfully.",
        _signature(
            r'test_ssl\.py", line 639, in test_openssl_version',
            r"AssertionError: 0 not greater than or equal to 1",
        ),
    ),
    (
        "FAIL",
        "test_parse_cert_CVE_2013_4238 (test.test_ssl.BasicSocketTests.test_parse_cert_CVE_2013_4238)",
    ): _ExpectedFailure(
        "the pinned OpenSSL-version branch expects '<invalid>' for the IPv6 SAN; RTLS returns its parsed IPv6 address while preserving the embedded-NUL SAN values.",
        _signature(
            r'test_ssl\.py", line 591, in test_parse_cert_CVE_2013_4238',
            r"self\.assertEqual\(p\['subjectAltName'\], san\)",
            r"^  \(\('DNS', 'altnull\.python\.org\\x00example\.com'\),$",
            r"^   \('email', 'null@python\.org\\x00user@example\.org'\),$",
            r"^   \('URI', 'http://null\.python\.org\\x00http://example\.org'\),$",
            r"^-  \('IP Address', '2001:DB8:0:0:0:0:0:1'\)\)$",
            r"^\+  \('IP Address', '<invalid>'\)\)$",
            r"AssertionError: Tuples differ:",
        ),
    ),
    (
        "FAIL",
        "test_ssl_types (test.test_ssl.BasicSocketTests.test_ssl_types) (ssl_type=<class 'rtls._context.TLSContext'>)",
    ): _ExpectedFailure(
        "the upstream test requires immutable OpenSSL extension types, outside the RTLS Python wrapper contract.",
        _signature(
            r'test_ssl\.py", line 475, in test_ssl_types',
            r'assertRaisesRegex\(TypeError, "immutable type"\)',
            r"AssertionError: TypeError not raised",
        ),
    ),
    (
        "FAIL",
        "test_ssl_types (test.test_ssl.BasicSocketTests.test_ssl_types) (ssl_type=<class 'rtls._socket.TLSSocket'>)",
    ): _ExpectedFailure(
        "the upstream test requires immutable OpenSSL extension types, outside the RTLS Python wrapper contract.",
        _signature(
            r'test_ssl\.py", line 475, in test_ssl_types',
            r'assertRaisesRegex\(TypeError, "immutable type"\)',
            r"AssertionError: TypeError not raised",
        ),
    ),
    (
        "FAIL",
        "test_ssl_types (test.test_ssl.BasicSocketTests.test_ssl_types) (ssl_type=<class 'rtls._bio.MemoryBIO'>)",
    ): _ExpectedFailure(
        "the upstream test requires immutable OpenSSL extension types, outside the RTLS Python wrapper contract.",
        _signature(
            r'test_ssl\.py", line 475, in test_ssl_types',
            r'assertRaisesRegex\(TypeError, "immutable type"\)',
            r"AssertionError: TypeError not raised",
        ),
    ),
    (
        "FAIL",
        "test_ssl_types (test.test_ssl.BasicSocketTests.test_ssl_types) (ssl_type=<class 'rtls._certificate.TLSCertificate'>)",
    ): _ExpectedFailure(
        "the upstream test requires immutable OpenSSL extension types, outside the RTLS Python wrapper contract.",
        _signature(
            r'test_ssl\.py", line 475, in test_ssl_types',
            r'assertRaisesRegex\(TypeError, "immutable type"\)',
            r"AssertionError: TypeError not raised",
        ),
    ),
    (
        "FAIL",
        "test_ssl_types (test.test_ssl.BasicSocketTests.test_ssl_types) (ssl_type=<class 'rtls._native.RustlsSession'>)",
    ): _ExpectedFailure(
        "the upstream test requires immutable OpenSSL extension types, outside the RTLS Python wrapper contract.",
        _signature(
            r'test_ssl\.py", line 475, in test_ssl_types',
            r'assertRaisesRegex\(TypeError, "immutable type"\)',
            r"AssertionError: TypeError not raised",
        ),
    ),
    (
        "FAIL",
        "test_ssl_types (test.test_ssl.BasicSocketTests.test_ssl_types) (ssl_type=<class 'rtls._exceptions.SSLError'>)",
    ): _ExpectedFailure(
        "the upstream test requires immutable OpenSSL extension types, outside the RTLS Python wrapper contract.",
        _signature(
            r'test_ssl\.py", line 475, in test_ssl_types',
            r'assertRaisesRegex\(TypeError, "immutable type"\)',
            r"AssertionError: TypeError not raised",
        ),
    ),
    (
        "FAIL",
        "test_ssl_types (test.test_ssl.BasicSocketTests.test_ssl_types)",
    ): _ExpectedFailure(
        "the upstream test requires an uninstantiable OpenSSL C certificate type; RTLS exposes a Python wrapper type instead.",
        _signature(
            r'test_ssl\.py", line 477, in test_ssl_types',
            r"TLSCertificate\.__init__\(\) missing 1 required positional argument: 'der_bytes'",
            r"cannot create 'rtls\\\._certificate\\\.TLSCertificate' instances",
            r"does not match",
        ),
    ),
    (
        "FAIL",
        "test__create_stdlib_context (test.test_ssl.ContextTests.test__create_stdlib_context)",
    ): _ExpectedFailure(
        "CPython's OpenSSL-version branch expects OP_LEGACY_SERVER_CONNECT from the reported version; RTLS does not expose that unsafe OpenSSL behavior.",
        _signature(
            r'test_ssl\.py", line 1834, in test__create_stdlib_context',
            r"self\._assert_context_options\(ctx\)",
            r'test_ssl\.py", line 1801, in _assert_context_options',
            r"ssl\.OP_LEGACY_SERVER_CONNECT",
            r"0 if IS_OPENSSL_3_0_0 else ssl\.OP_LEGACY_SERVER_CONNECT",
            r"AssertionError: <Options\.OP_NO_SSLv2: 0> != <Options\.OP_LEGACY_SERVER_CONNECT: 4>",
        ),
    ),
    (
        "FAIL",
        "test_create_default_context (test.test_ssl.ContextTests.test_create_default_context)",
    ): _ExpectedFailure(
        "CPython's OpenSSL-version branch expects OP_LEGACY_SERVER_CONNECT from the reported version; RTLS does not expose that unsafe OpenSSL behavior.",
        _signature(
            r'test_ssl\.py", line 1814, in test_create_default_context',
            r"self\._assert_context_options\(ctx\)",
            r'test_ssl\.py", line 1801, in _assert_context_options',
            r"ssl\.OP_LEGACY_SERVER_CONNECT",
            r"0 if IS_OPENSSL_3_0_0 else ssl\.OP_LEGACY_SERVER_CONNECT",
            r"AssertionError: <Options\.OP_NO_SSLv2: 0> != <Options\.OP_LEGACY_SERVER_CONNECT: 4>",
        ),
    ),
}


def _count_fields(value: str, allowed: set[str]) -> dict[str, int] | None:
    if not value.strip():
        return {}
    fields: dict[str, int] = {}
    separator = "," if "," in value else " "
    for item in value.split(separator):
        if not item.strip():
            continue
        match = _COUNT_FIELD.fullmatch(item.strip())
        if match is None or match.group(1) not in allowed or match.group(1) in fields:
            return None
        fields[match.group(1)] = int(match.group(2).replace(",", ""))
    return fields


def _diagnostic(body: str) -> str:
    for line in reversed(body.strip().splitlines()):
        value = line.strip()
        if re.match(r"[\w.]+(?:Error|Exception):", value):
            return value
    return body.strip()[-600:]


def _method_name(header: str) -> str:
    match = re.search(r"\((test\.test_ssl\.[^)]+)\)", header)
    return match.group(1) if match is not None else header


def _expected_result(kind: str, header: str, body: str) -> _ExpectedFailure | None:
    expected = _EXPECTED.get((kind, header))
    if expected is None:
        return None
    for signature in expected.signatures:
        if all(re.search(pattern, body, re.MULTILINE | re.DOTALL) for pattern in signature):
            return expected
    return None


def assess_ssl_log(
    output: str,
    *,
    expected_tests_run: int = EXPECTED_SSL_TEST_COUNT,
) -> dict[str, Any]:
    accepted: list[dict[str, str]] = []
    unexpected: list[dict[str, str]] = []
    accounting_errors: list[str] = []
    if not isinstance(output, str) or not output:
        return {
            "ok": False,
            "complete": False,
            "tests_run": 0,
            "failures": 0,
            "errors": 0,
            "skips": 0,
            "accepted": accepted,
            "unexpected": [],
            "accounting_errors": ["suite output is empty or not text"],
            "policy_source": POLICY_SOURCE,
        }

    text = _ANSI_ESCAPE.sub("", output)
    if _BACKEND.search(text) is None:
        accounting_errors.append("Rustls backend banner is missing")

    ran = list(_RUN.finditer(text))
    failed = list(_FAILED.finditer(text))
    successful = list(_OK.finditer(text))
    total_tests = list(_TOTAL_TESTS.finditer(text))
    total_files = list(_TOTAL_FILES.finditer(text))
    result_markers = list(_RESULT.finditer(text))
    blocks = list(_RESULT_BLOCK.finditer(text))
    tests_run = int(ran[0].group(1).replace(",", "")) if len(ran) == 1 else 0
    failures = 0
    errors = 0
    skips = 0
    suite_state: str | None = None

    if len(ran) != 1:
        accounting_errors.append("expected exactly one unittest Ran summary")
    if len(failed) + len(successful) != 1:
        accounting_errors.append("expected exactly one unittest OK or FAILED summary")
    elif failed:
        suite_state = "FAILED"
        fields = _count_fields(failed[0].group(1), {"failures", "errors", "skipped"})
        if fields is None:
            accounting_errors.append("unittest FAILED summary fields are malformed")
        else:
            failures = fields.get("failures", 0)
            errors = fields.get("errors", 0)
            skips = fields.get("skipped", 0)
    elif successful:
        suite_state = "OK"
        fields = _count_fields(successful[0].group(1) or "", {"skipped"})
        if fields is None:
            accounting_errors.append("unittest OK summary fields are malformed")
        else:
            skips = fields.get("skipped", 0)

    if len(total_tests) != 1:
        accounting_errors.append("expected exactly one outer Total tests summary")
    else:
        total_fields = _count_fields(
            total_tests[0].group(1), {"run", "failures", "errors", "skipped"}
        )
        if total_fields is None:
            accounting_errors.append("outer Total tests fields are malformed")
        else:
            if total_fields.get("run") != tests_run:
                accounting_errors.append("Ran and Total tests counts differ")
            if total_fields.get("failures", 0) != failures:
                accounting_errors.append("unittest and outer failure counts differ")
            if "errors" in total_fields and total_fields["errors"] != errors:
                accounting_errors.append("unittest and outer error counts differ")
            if total_fields.get("skipped", 0) != skips:
                accounting_errors.append("unittest and outer skip counts differ")

    if tests_run <= 0:
        accounting_errors.append("test run count is missing or zero")
    if type(expected_tests_run) is not int or expected_tests_run <= 0:
        accounting_errors.append("expected test count is missing or invalid")
    elif tests_run != expected_tests_run:
        accounting_errors.append(
            f"test_ssl run must include all {expected_tests_run} discovered tests"
        )
    if len(total_files) != 1:
        accounting_errors.append("expected exactly one outer Total test files summary")
    else:
        file_fields = re.fullmatch(
            r"run=([0-9,]+)/([0-9,]+)(?: failed=([0-9,]+)| passed=([0-9,]+))?",
            total_files[0].group(1),
        )
        if file_fields is None:
            accounting_errors.append("outer Total test files fields are malformed")
        else:
            files_run, files_expected = (
                int(value.replace(",", "")) for value in file_fields.group(1, 2)
            )
            file_failures = int((file_fields.group(3) or "0").replace(",", ""))
            file_passes = int((file_fields.group(4) or "0").replace(",", ""))
            if files_run <= 0 or files_run != files_expected:
                accounting_errors.append("test file run count is incomplete")
            if suite_state == "FAILED" and file_failures != 1:
                accounting_errors.append("failed suite must report its one test file failed")
            if suite_state == "OK" and file_passes != files_run:
                accounting_errors.append("successful suite file count is inconsistent")

    failed_file_lists = list(_FAILED_FILES.finditer(text))
    if suite_state == "FAILED":
        if len(failed_file_lists) != 1:
            accounting_errors.append("failed suite must report exactly one failed test-file list")
        else:
            listed_count = int(failed_file_lists[0].group(1))
            listed_files = failed_file_lists[0].group(2).split()
            if listed_count != len(listed_files) or listed_files != ["test_ssl"]:
                accounting_errors.append("failed test-file list does not match the pinned test_ssl run")
    elif failed_file_lists:
        accounting_errors.append("successful unittest summary contains a failed test-file list")

    expected_result = "FAILURE" if suite_state == "FAILED" else "SUCCESS"
    if len(result_markers) != 1 or result_markers[0].group(1) != expected_result:
        accounting_errors.append("outer Result state disagrees with unittest summary")
    if len(_SKIP_LINE.findall(text)) != skips:
        accounting_errors.append("unittest skip marker count disagrees with its summary")

    observed_failures = sum(match.group(1) == "FAIL" for match in blocks)
    observed_errors = sum(match.group(1) == "ERROR" for match in blocks)
    if observed_failures != failures:
        accounting_errors.append("parsed FAIL blocks do not match unittest failure count")
    if observed_errors != errors:
        accounting_errors.append("parsed ERROR blocks do not match unittest error count")

    seen: set[tuple[str, str]] = set()
    for block in blocks:
        kind, header, body = block.groups()
        key = (kind, header)
        expected = _expected_result(kind, header, body)
        if key in seen:
            unexpected.append(
                {
                    "case": header,
                    "kind": kind,
                    "reason": "duplicate unittest result block",
                    "detail": _diagnostic(body),
                }
            )
        elif expected is None:
            registered = _EXPECTED.get(key)
            unexpected.append(
                {
                    "case": header,
                    "kind": kind,
                    "reason": (
                        "known case did not match its exact expected trace signature"
                        if registered is not None
                        else "case is outside the explicit modern TLS accounting policy"
                    ),
                    "detail": _diagnostic(body),
                }
            )
        else:
            accepted.append(
                {
                    "case": header,
                    "kind": kind,
                    "reason": expected.reason,
                }
            )
        seen.add(key)

    if len(accepted) + len(unexpected) != failures + errors:
        accounting_errors.append("classification entries do not match the unittest failure and error totals")
    complete = not accounting_errors
    return {
        "ok": complete and not unexpected,
        "complete": complete,
        "tests_run": tests_run,
        "expected_tests_run": expected_tests_run,
        "failures": failures,
        "errors": errors,
        "skips": skips,
        "accepted": accepted,
        "unexpected": unexpected,
        "accounting_errors": accounting_errors,
        "outside_policy_methods": sorted({_method_name(header) for _, header in _EXPECTED}),
        "outside_policy_event_count": len(_EXPECTED),
        "policy_source": POLICY_SOURCE,
    }


def extract_test_ssl_log(full_run_output: str) -> str:
    if not isinstance(full_run_output, str) or not full_run_output:
        raise ValueError("full regression output is empty or not text")
    banners = list(_BACKEND.finditer(full_run_output))
    if len(banners) != 1:
        raise ValueError("full regression output must contain one Rustls test_ssl block")
    endings = [
        match for match in _SSL_BLOCK_END.finditer(full_run_output)
        if match.start() > banners[0].start()
    ]
    if len(endings) != 1:
        raise ValueError("full regression output has no unique completed test_ssl block")
    end = endings[0].end()
    if full_run_output[end : end + 2] == "\r\n":
        end += 2
    elif full_run_output[end : end + 1] == "\n":
        end += 1
    return full_run_output[banners[0].start() : end]


def assess_ssl_full_run(
    full_run_output: str,
    *,
    expected_tests_run: int = EXPECTED_SSL_TEST_COUNT,
) -> dict[str, Any]:
    ssl_output = extract_test_ssl_log(full_run_output)
    progress = list(_FULL_SSL_PROGRESS.finditer(full_run_output))
    if len(progress) != 1:
        raise ValueError("full regression output must report one completed test_ssl result")
    full_counts = (
        tuple(map(int, progress[0].groups()))
        if progress[0].group(1) is not None
        else (0, 0)
    )

    ran = list(_RUN.finditer(ssl_output))
    failed = list(_FAILED.finditer(ssl_output))
    successful = list(_OK.finditer(ssl_output))
    blocks = list(_RESULT_BLOCK.finditer(ssl_output))
    if len(ran) != 1 or len(failed) + len(successful) != 1:
        raise ValueError("full-run test_ssl block has incomplete unittest accounting")
    tests_run = int(ran[0].group(1).replace(",", ""))
    if type(expected_tests_run) is not int or expected_tests_run <= 0:
        raise ValueError("expected test count is missing or invalid")
    if tests_run != expected_tests_run:
        raise ValueError(
            f"full-run test_ssl block must include all {expected_tests_run} discovered tests"
        )

    if failed:
        fields = _count_fields(failed[0].group(1), {"failures", "errors", "skipped"})
        if fields is None:
            raise ValueError("full-run test_ssl FAILED summary is malformed")
        failures = fields.get("failures", 0)
        errors = fields.get("errors", 0)
        skips = fields.get("skipped", 0)
    else:
        fields = _count_fields(successful[0].group(1) or "", {"skipped"})
        if fields is None:
            raise ValueError("full-run test_ssl OK summary is malformed")
        failures = errors = 0
        skips = fields.get("skipped", 0)

    if (
        sum(match.group(1) == "FAIL" for match in blocks) != failures
        or sum(match.group(1) == "ERROR" for match in blocks) != errors
        or (errors, failures) != full_counts
    ):
        raise ValueError("full-suite and verbose test_ssl result counts differ")
    wrapper = ssl_output + (
        f"\nTotal tests: run={tests_run} failures={failures} errors={errors} skipped={skips}\n"
        "Total test files: run=1/1 failed=1\n"
        "Result: FAILURE\n1 test failed:\n    test_ssl\n"
        if failures or errors
        else f"\nTotal tests: run={tests_run} skipped={skips}\n"
        "Total test files: run=1/1 passed=1\n"
        "Result: SUCCESS\n"
    )
    return assess_ssl_log(wrapper, expected_tests_run=expected_tests_run)
