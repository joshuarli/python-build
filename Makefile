PYTHON ?= python3

BENCH_TARGET := x86_64-unknown-linux-musl
BENCH_ARTIFACT := dist/$(BENCH_TARGET)/cpython-3.14.6-$(BENCH_TARGET)-r2.tar.gz
BENCH_PROFILE ?= standard
BENCH_PYPERFORMANCE_SELECTION ?= all
BENCH_PYPERFORMANCE_ARGS = $(if $(strip $(BENCH_PYPERFORMANCE_SELECTION)),--pyperformance-selection $(BENCH_PYPERFORMANCE_SELECTION),)

.PHONY: bench bench-full bench-host-check bench-inputs bench-product

# The default comparison measures all repository-owned workloads.
bench: bench-inputs bench-product
	$(PYTHON) benchmarks/bench.py run \
		--preset pbs \
		--suite realworld \
		--profile $(BENCH_PROFILE)

# Add every pinned pyperformance benchmark to the repository-owned suite.
bench-full: bench-inputs bench-product
	$(PYTHON) benchmarks/bench.py run \
		--preset pbs \
		--suite full \
		--profile $(BENCH_PROFILE) \
		$(BENCH_PYPERFORMANCE_ARGS)

bench-host-check:
	$(PYTHON) -c 'from buildsys.targets import native_target; actual = native_target().triple; expected = "$(BENCH_TARGET)"; print("Benchmark target:", actual); assert actual == expected, f"make bench requires native {expected}, found {actual}"'

bench-inputs: bench-host-check
	$(PYTHON) benchmarks/bench.py fetch
	$(PYTHON) benchmarks/bench.py prepare

bench-product: bench-host-check
	@if test -f "$(BENCH_ARTIFACT)"; then \
		printf '%s\n' "Using existing product artifact: $(BENCH_ARTIFACT)"; \
	else \
		$(PYTHON) build.py fetch --target $(BENCH_TARGET) && \
		$(PYTHON) build.py build --target $(BENCH_TARGET) --dev && \
		$(PYTHON) build.py package --target $(BENCH_TARGET); \
	fi
