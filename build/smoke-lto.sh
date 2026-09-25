#!/bin/sh
# LTO smoke test: verify clang+lld produce and link ThinLTO objects on native musl.
# Run this gate before launching dependency builds.
set -eu
cd "$(dirname "$0")/.."
work=$(mktemp -d /tmp/lto-smoke.XXXXXX)
trap 'rm -rf "$work"' EXIT
cat > "$work/a.c" << 'EOF'
extern int add(int, int);
int main(void) { return add(2, 3) == 5 ? 0 : 1; }
EOF
cat > "$work/b.c" << 'EOF'
int add(int a, int b) { return a + b; }
EOF
clang -O3 -flto=thin -c "$work/a.c" -o "$work/a.o"
clang -O3 -flto=thin -c "$work/b.c" -o "$work/b.o"
clang -flto=thin "$work/a.o" "$work/b.o" -fuse-ld=lld -o "$work/smoke"
"$work/smoke"
echo "LTO smoke: OK ($(file -b "$work/smoke" | cut -d, -f1-2))"
