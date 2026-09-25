"""Read every regular file in the pinned CPython source archive through tarfile."""

import argparse
import hashlib
import json
import tarfile
import time


ARCHIVE_SHA256 = "965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467"
ARCHIVE_SIZE = 44_210_863
EXPECTED_DIGEST = "4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805"


def archive_digest(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as source:
        while chunk := source.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    if size != ARCHIVE_SIZE or digest.hexdigest() != ARCHIVE_SHA256:
        raise ValueError("source archive differs from the locked input")


def read_archive(path):
    digest = hashlib.sha256()
    regular_files = 0
    regular_bytes = 0
    members = 0
    with tarfile.open(path, mode="r:gz") as archive:
        for info in archive:
            members += 1
            if not info.isfile():
                continue
            metadata = (info.name, info.size, info.mode, info.mtime,
                        info.uid, info.gid, info.uname, info.gname,
                        info.type.decode("ascii"))
            digest.update(json.dumps(metadata, separators=(",", ":")).encode())
            digest.update(b"\0")
            stream = archive.extractfile(info)
            if stream is None:
                raise ValueError("regular member has no content")
            size = 0
            with stream:
                while chunk := stream.read(1 << 20):
                    digest.update(chunk)
                    size += len(chunk)
            if size != info.size:
                raise ValueError("truncated regular member")
            regular_files += 1
            regular_bytes += size
    return digest.hexdigest(), members, regular_files, regular_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    parser.add_argument("--loops", type=int, default=1)
    args = parser.parse_args()
    if args.loops < 1:
        parser.error("--loops must be positive")
    archive_digest(args.archive)
    start = time.perf_counter()
    result = None
    for _ in range(args.loops):
        current = read_archive(args.archive)
        if result is not None and current != result:
            raise ValueError("archive result changed across iterations")
        result = current
    internal = time.perf_counter() - start
    if result[0] != EXPECTED_DIGEST:
        raise ValueError("source archive output digest changed")
    print(json.dumps({"digest": result[0], "members": result[1],
                      "regular_files": result[2], "regular_bytes": result[3],
                      "logical_bytes": result[3] * args.loops,
                      "loops": args.loops, "internal_seconds": internal}, sort_keys=True))


if __name__ == "__main__":
    main()
