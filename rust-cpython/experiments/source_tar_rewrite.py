"""Stream the locked CPython source archive into a deterministic plain tar."""

import argparse
import hashlib
import json
import tarfile
import time


ARCHIVE_SHA256 = "965dbc9c847b0ed779a16134495b8690c9fc957996d8bcbb83c47089d4e81467"
ARCHIVE_SIZE = 44_210_863
SOURCE_DIGEST = "4274d870abacbefea6bbdb2175de8b4073198e1fd39f34ede1c065b3faf1a805"
MEMBERS = 6539
REGULAR_FILES = 6031
REGULAR_BYTES = 136_064_031


def file_digest(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class DigestReader:
    def __init__(self, stream, digest):
        self.stream = stream
        self.digest = digest
        self.bytes_read = 0

    def read(self, size):
        chunk = self.stream.read(size)
        self.digest.update(chunk)
        self.bytes_read += len(chunk)
        return chunk


def rewrite(source, output):
    source_digest = hashlib.sha256()
    members = regular_files = regular_bytes = 0
    with tarfile.open(source, "r|gz") as incoming, tarfile.open(
        output, "w|", format=tarfile.PAX_FORMAT
    ) as outgoing:
        for info in incoming:
            members += 1
            if not info.isfile():
                outgoing.addfile(info)
                continue
            metadata = (info.name, info.size, info.mode, info.mtime,
                        info.uid, info.gid, info.uname, info.gname,
                        info.type.decode("ascii"))
            source_digest.update(json.dumps(metadata, separators=(",", ":")).encode())
            source_digest.update(b"\0")
            stream = incoming.extractfile(info)
            if stream is None:
                raise ValueError("regular member has no content")
            with stream:
                reader = DigestReader(stream, source_digest)
                outgoing.addfile(info, reader)
            if reader.bytes_read != info.size:
                raise ValueError("truncated regular member")
            regular_files += 1
            regular_bytes += reader.bytes_read
    if (source_digest.hexdigest(), members, regular_files, regular_bytes) != (
        SOURCE_DIGEST, MEMBERS, REGULAR_FILES, REGULAR_BYTES
    ):
        raise ValueError("source TAR member or content identity changed")
    output_digest, output_bytes = file_digest(output)
    return {"source_digest": source_digest.hexdigest(),
            "output_digest": output_digest, "output_bytes": output_bytes,
            "members": members, "regular_files": regular_files,
            "regular_bytes": regular_bytes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()
    source_digest, source_size = file_digest(args.source)
    if (source_digest, source_size) != (ARCHIVE_SHA256, ARCHIVE_SIZE):
        raise ValueError("source archive differs from the locked input")
    start = time.perf_counter()
    result = rewrite(args.source, args.output)
    result["internal_seconds"] = time.perf_counter() - start
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
