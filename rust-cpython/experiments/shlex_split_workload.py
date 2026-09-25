"""Parse a deterministic batch of build and deployment command records."""

import argparse
import hashlib
import json
import shlex


TEMPLATES = (
    "clang -O3 -I'/opt/SDK Headers' -DNAME=alpha src/main.c -o build/main",
    "pkg-config --cflags --libs 'libssl >= 3.0' sqlite3",
    "cc -Wall -DVERSION=\"1.2.3\" 'path with spaces.c' -o app",
    "env MODE=release ROOT=/srv/app make -j8 install PREFIX='/srv/new root'",
    "python3 -m build --config-setting=--global-option=fast ./package",
    "rsync -av '/tmp/source tree/' deploy@example:/srv/releases/current/",
    "tool --message='hello world' --empty='' --literal=one\\ two end",
    "configure --prefix=/opt/demo --with-openssl='/opt/SSL 3' CFLAGS='-O3 -g'",
    "docker run --rm -e 'A=x y' -v /src:/work image:latest sh -c 'echo done'",
    "printf '%s\\n' 'quoted value' café/naïve 'it'\"'\"'s here'",
    "command --path=~/src/*.c --expr='a|b && c' -- arg1 arg2",
    "launch --newline='first\nsecond' --tab='x\ty' --backslash=one\\\\two",
)
FALLBACK = (
    ("echo one # ignored comment", True, True),
    ("cmd 'single quoted' \"double quoted\"", False, False),
    ("echo 'unterminated", False, True),
    ("echo trailing\\", False, True),
)


def run(count: int, rounds: int) -> dict[str, object]:
    records = []
    for index in range(count):
        template = TEMPLATES[index % len(TEMPLATES)]
        records.append((f"{template} --job={index:06d}", False, True))
        if index % 19 == 0:
            records.append(FALLBACK[(index // 19) % len(FALLBACK)])

    buckets: dict[str, list[int]] = {}
    digest = hashlib.sha256()
    errors = 0
    tokens = 0
    for _ in range(rounds):
        for command, comments, posix in records:
            try:
                parts = shlex.split(command, comments=comments, posix=posix)
            except ValueError as error:
                errors += 1
                digest.update(f"error:{error}\n".encode())
                continue
            tokens += len(parts)
            bucket = buckets.setdefault(parts[0], [0, 0])
            bucket[0] += 1
            bucket[1] += sum(map(len, parts))
            digest.update(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode())
            digest.update(b"\n")
    digest.update(json.dumps(sorted(buckets.items()), ensure_ascii=False).encode())
    return {"records": len(records), "rounds": rounds, "tokens": tokens,
            "errors": errors, "buckets": len(buckets), "digest": digest.hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=12000)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(run(args.count, args.rounds), sort_keys=True))
