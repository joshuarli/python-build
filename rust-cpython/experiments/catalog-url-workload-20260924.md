# Catalog URL normalization workload

## Scope and contract

`benchmarks.workloads.catalog_url` registers `catalog_url_normalize` in the
realworld/full application suite. One operation normalizes a fixed batch of
48 URLs and produces 48 stable keys through the checked-in catalog fixture's
public `normalize_url` and `stable_key` functions. The workload does not
replace those functions or introduce a Rust implementation. It loads
`benchmarks/workloads/fixtures/tooling/python_corpus/catalog_service/normalize.py`
from its own resolved module location, so the benchmark runner's
`python -m benchmarks.workloads.catalog_url` command does not depend on the
working directory or a separately installed catalog package.

The source batch is constructed and its digest checked before the timer.
Within the timer, each iteration calls both functions for every record,
serializes every URL and key into a length-framed SHA-256 digest, and checks
the complete result. The operation count is the number of complete batches;
each operation contains 96 catalog function calls. The runner's external
process measurement still includes interpreter startup and fixture loading,
while `elapsed_seconds` measures the steady batch loop. Those are separate
observations, not interchangeable speed results.

## Fixed data

`_batch()` holds 12 explicit URL/key cases, 24 numbered unique item URLs,
then repeats the first 12 cases once. There are 36 distinct records and 12
repeated records. The explicit cases include plain and Unicode paths,
reserved punctuation, encoded and malformed percent escapes, credentials,
IPv4 and IPv6 hosts, query and fragment data, path dot segments, a one-letter
key component, and long path/query/key components. The generated item URLs
are fixed by `range(24)` and include unique paths and queries. All strings
are in the source file; there is no random seed or external input.

The 48 URL strings occupy 7,348 UTF-8 bytes total, with lengths 25–2,459
bytes and upper median 59 bytes. The 144 key components occupy 3,832 UTF-8
bytes total, with lengths 0–1,024 bytes and upper median 6 bytes. The fixed
length-framed input digest is
`7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f`.
The fixed complete-output digest is
`a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941`.
Each framed record includes both outputs in order, including duplicates.

The fixture currently removes brackets around an IPv6 hostname when it
reconstructs a URL. This workload pins its actual output, for example
`https://reader:secret@2001:db8::1:443/docs?q=ok#part`; that result is not
claimed to be a valid URL. Malformed percent escapes likewise follow the
fixture's present behavior. The workload is a measure of the checked-in
application task, not a URL correctness oracle.

## Local checks and limits

On 2026-09-24, `python3 -m unittest benchmarks.tests.test_catalog_url_workload`
passed 2 tests. `/usr/bin/time -l` reported 0.05 user CPU seconds, 0.02
system CPU seconds, 26,034,176 bytes maximum RSS, and 0 swaps for that
command. The checks cover registration, fixed whole-batch digests, operation
counts, repeated outputs, and representative catalog behavior.

One bounded smoke of
`python3 -m benchmarks.workloads.catalog_url catalog_url_normalize --iterations 100`
returned the fixed digests and 100 operations. Its internal batch elapsed
time was 0.05146 seconds. `/usr/bin/time -l` reported 0.08 user CPU seconds,
0.01 system CPU seconds, 22,429,696 bytes maximum RSS, and 0 swaps for the
whole process. These shell commands spawned no workload children; their
kernel-accounted CPU and peak RSS cover the command processes. Their combined
reported CPU was 0.16 seconds, within the lane's 60 CPU-second and 512 MB
RSS limits. No formatter, linter, comparative benchmark, or Rust build ran.

The smoke only validates the interface and fixed result. The host was busy;
no control/candidate timing conclusion follows. This batch includes long
components but not the 200,000-byte `quote_from_bytes` chunking threshold.
Cold-process import is represented by runner process startup, not by the
internal `elapsed_seconds` value.
