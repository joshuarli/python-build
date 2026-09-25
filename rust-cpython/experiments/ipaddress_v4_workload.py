"""Deterministic mixed-family routing and firewall address workload."""

import argparse
import hashlib
import ipaddress
import json


def rows(count):
    for index in range(count):
        key = (index * 1103515245 + 12345) & 0xffffffff
        if index % 5:
            a = 10 + (key % 11)
            b = (key >> 8) & 255
            c = (key >> 16) & 255
            d = (key >> 24) & 255
            prefix = (16, 20, 24, 28)[index % 4]
            address = f"{a}.{b}.{c}.{d}"
            peer = f"{a}.{b}.{c}.{(d + index % 19) & 255}"
        else:
            a = (key >> 16) & 0xffff
            b = key & 0xffff
            c = (index * 17) & 0xffff
            d = (index * 41) & 0xffff
            prefix = (32, 48, 64, 96)[index % 4]
            address = f"2001:db8:{a:x}:{b:x}:{c:x}:{d:x}::1"
            peer = f"2001:db8:{a:x}:{b:x}:{c:x}:{d:x}::2"
        yield address, peer, prefix


def run(count, rounds):
    entries = tuple(rows(count))
    digest = hashlib.sha256()
    contained = overlaps = 0
    for _ in range(rounds):
        for text, peer_text, prefix in entries:
            address = ipaddress.ip_address(text)
            peer = ipaddress.ip_address(peer_text)
            network = ipaddress.ip_network(f"{text}/{prefix}", strict=False)
            if peer in network:
                contained += 1
            parent = network.supernet(prefixlen_diff=1)
            if network.subnet_of(parent):
                overlaps += 1
            digest.update(str(address).encode("ascii"))
            digest.update(b"|")
            digest.update(str(network).encode("ascii"))
            digest.update(b"|")
            digest.update(bytes((int(peer in network), int(address in network))))
    return {"count": count, "rounds": rounds, "ipv4_fraction": "4/5",
            "contained": contained, "subnets": overlaps,
            "digest": digest.hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(run(args.count, args.rounds), sort_keys=True))
