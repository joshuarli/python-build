PYTHON ?= python3

BENCH_TARGET ?= $(shell $(PYTHON) -c 'from buildsys.targets import native_target; print(native_target().triple)')
BENCH_ARTIFACT := dist/$(BENCH_TARGET)/cpython-3.14.6-$(BENCH_TARGET)-r2.tar.gz
BENCH_PROFILE ?= standard
BENCH_PYPERFORMANCE_SELECTION ?= all
BENCH_PYPERFORMANCE_ARGS = $(if $(strip $(BENCH_PYPERFORMANCE_SELECTION)),--pyperformance-selection $(BENCH_PYPERFORMANCE_SELECTION),)

.PHONY: bench bench-full bench-host-check bench-inputs bench-product

ifeq ($(BENCH_TARGET),aarch64-apple-darwin)
# The locked wheelhouse is Linux/musl-only; macOS uses dependency-free smoke workloads.
BENCH_SUITE ?= smoke
BENCH_RUN_OPTIONS = --local --timing-only
BENCH_PREPARE = @:
else
BENCH_SUITE ?= realworld
BENCH_RUN_OPTIONS =
BENCH_PREPARE = $(PYTHON) benchmarks/bench.py prepare
endif

bench: bench-inputs bench-product
	$(PYTHON) benchmarks/bench.py run \
		--preset pbs \
		--candidate "$(BENCH_ARTIFACT)" \
		--candidate-label "python-build CPython 3.14.6" \
		--candidate-kind python-build \
		--suite $(BENCH_SUITE) \
		--profile $(BENCH_PROFILE) \
		$(BENCH_RUN_OPTIONS)

ifeq ($(BENCH_TARGET),aarch64-apple-darwin)
bench-full:
	@echo "bench-full requires the Linux amd64 benchmark environment" >&2
	@exit 2
else
bench-full: bench-inputs bench-product
	$(PYTHON) benchmarks/bench.py run \
		--preset pbs \
		--candidate "$(BENCH_ARTIFACT)" \
		--candidate-label "python-build CPython 3.14.6" \
		--candidate-kind python-build \
		--suite full \
		--profile $(BENCH_PROFILE) \
		$(BENCH_PYPERFORMANCE_ARGS)
endif

bench-host-check:
	$(PYTHON) -c 'from buildsys.targets import native_target; actual = native_target().triple; expected = "$(BENCH_TARGET)"; supported = {"x86_64-unknown-linux-musl", "aarch64-apple-darwin"}; print("Benchmark target:", actual); assert actual in supported, f"make bench does not support {actual}"; assert actual == expected, f"make bench requires native {expected}, found {actual}"'

bench-inputs: bench-host-check
	$(PYTHON) benchmarks/bench.py fetch --target $(BENCH_TARGET)
	$(BENCH_PREPARE)

bench-product: bench-host-check
	@if test -f "$(BENCH_ARTIFACT)"; then \
		printf '%s\n' "Using existing product artifact: $(BENCH_ARTIFACT)"; \
	else \
		$(PYTHON) build.py fetch --target $(BENCH_TARGET) && \
		$(PYTHON) build.py build --target $(BENCH_TARGET) --dev && \
		$(PYTHON) build.py package --target $(BENCH_TARGET); \
	fi
