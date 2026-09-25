"""Deterministic public tarfile extraction workload for installed interpreters."""

import argparse
import gzip
import hashlib
import io
import json
import tarfile
import time


ARCHIVE_SHA256 = "c3a1efad63406bc8045a04de881d778c171bdf9aa23e37f6196d36808a565c5f"
CONTENT_SHA256 = "882e28e798c459b79bd291bcac95cdd6b84f4ea11f332788a2d4202197e2d0fc"
SMALL_COUNT = 24
BULK_SIZE = 1_048_576


def members():
    for index in range(SMALL_COUNT):
        name = f"assets/item-{index:02d}.dat"
        payload = bytes((index * 17 + offset * 31) & 255 for offset in range(128 + index * 19))
        yield name, payload, 0o640 + index % 4, 1_700_000_000 + index
    bulk = b"".join(hashlib.sha256(index.to_bytes(4, "little")).digest()
                    for index in range(BULK_SIZE // 32))
    yield "assets/bulk-resource.bin", bulk, 0o644, 1_700_000_100


def record(digest, info, payload):
    fields = (info.name, info.size, info.mode, info.mtime, info.uid, info.gid,
              info.uname, info.gname, info.type.decode("ascii"))
    digest.update(json.dumps(fields, separators=(",", ":")).encode("utf-8"))
    digest.update(b"\0")
    digest.update(payload)


def make_archive():
    contents = hashlib.sha256()
    plain = io.BytesIO()
    with tarfile.open(fileobj=plain, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, payload, mode, mtime in members():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = mode
            info.mtime = mtime
            info.uid = 501
            info.gid = 20
            info.uname = "builder"
            info.gname = "staff"
            archive.addfile(info, io.BytesIO(payload))
            record(contents, info, payload)
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as stream:
        stream.write(plain.getvalue())
    data = compressed.getvalue()
    return data, contents.hexdigest()


def extract_digest(data):
    digest = hashlib.sha256()
    count = 0
    size = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for info in archive:
            if not info.isfile():
                raise ValueError("unexpected non-file member")
            stream = archive.extractfile(info)
            if stream is None:
                raise ValueError("missing member stream")
            with stream:
                payload = stream.read()
            if len(payload) != info.size:
                raise ValueError("truncated member")
            record(digest, info, payload)
            count += 1
            size += len(payload)
    if count != SMALL_COUNT + 1:
        raise ValueError(f"unexpected member count: {count}")
    return digest.hexdigest(), size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loops", type=int, required=True)
    args = parser.parse_args()
    if args.loops < 1:
        parser.error("--loops must be positive")
    archive, expected_content = make_archive()
    archive_sha = hashlib.sha256(archive).hexdigest()
    if archive_sha != ARCHIVE_SHA256:
        raise ValueError("archive bytes changed")
    if expected_content != CONTENT_SHA256:
        raise ValueError("fixture contents changed")
    start = time.perf_counter()
    for _ in range(args.loops):
        actual_content, extracted_bytes = extract_digest(archive)
        if actual_content != expected_content:
            raise ValueError("extracted content or metadata changed")
    elapsed = time.perf_counter() - start
    print(json.dumps({"archive_sha256": archive_sha,
                      "content_sha256": expected_content,
                      "archive_bytes": len(archive),
                      "entry_count": SMALL_COUNT + 1,
                      "bytes_per_loop": extracted_bytes,
                      "logical_extracted_bytes": extracted_bytes * args.loops,
                      "loops": args.loops,
                      "internal_seconds": elapsed}, sort_keys=True))


if __name__ == "__main__":
    main()
