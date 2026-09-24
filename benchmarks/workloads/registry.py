"""Explicit workload contract used by the benchmark controller.

Each iteration represents the named operation, not an arbitrary loop count.
The driver prints a correctness digest and operation count for every pass.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Workload:
    name: str
    category: str
    module: str
    operation: str
    iterations: int
    allocation_iterations: int
    packages: tuple[str, ...] = ()
    noise_class: str = "stable"


WORKLOADS: tuple[Workload, ...] = (
    Workload("django_wsgi_request", "web", "django", "request", 30, 5, ("Django",)),
    Workload("django_asgi_request", "web", "django", "request", 30, 5, ("Django",), "noisy"),
    Workload("django_orm_10k", "database", "django", "row", 1, 1, ("Django",)),
    Workload("django_template_realistic", "web", "django", "render", 30, 5, ("Django",)),
    Workload("pylint_source", "tooling", "tooling", "lint pass", 1, 1, ("pylint",)),
    Workload("pycparser_source", "parsing", "tooling", "parse pass", 1, 1, ("pycparser",)),
    Workload("compileall_source", "tooling", "tooling", "compiled source tree", 1, 1),
    Workload("python_startup", "startup", "extra", "process", 1, 1),
    Workload("import_django", "startup", "extra", "import process", 1, 1, ("Django",)),
    Workload("import_app_stack", "startup", "extra", "import process", 1, 1,
             ("Django", "FastAPI", "Pydantic", "SQLAlchemy")),
    Workload("pip_install_wheelhouse", "packaging", "extra", "installation", 1, 1, ("pip",), "noisy"),
    Workload("rust_base64_small", "encoding", "rust_base64", "64-byte Base64 encode", 100_000, 1),
    Workload("rust_base64_large", "encoding", "rust_base64", "1-MiB Base64 encode", 16, 1),
    Workload("zlib_decode_1m", "compression", "zlib", "decoded byte", 16, 1),
    Workload("zlib_stream_4k", "compression", "zlib", "decoded byte", 8, 1),
    Workload("gzip_extract_1m", "compression", "zlib", "extracted byte", 16, 1),
    Workload("zip_read_wheel", "packaging", "zlib", "extracted byte", 4, 1),
    Workload("zipimport_cold", "startup", "zlib", "import process", 3, 1,
             noise_class="noisy"),
    Workload("difflib_unified_mostly_equal", "tooling", "difflib",
             "complete unified diff", 500, 10),
    Workload("difflib_unified_reordered", "tooling", "difflib",
             "complete unified diff", 1000, 10),
    Workload("catalog_url_normalize", "web", "catalog_url", "catalog URL/key batch", 1500, 2),
    Workload("catalog_search_form", "web", "catalog_url_breadth", "48 search form requests and parses", 500, 2),
    Workload("catalog_request_path", "web", "catalog_url_breadth", "48 canonical request paths", 1000, 2),
    Workload("serialization_roundtrip", "serialization", "extra", "roundtrip", 100, 20),
    Workload("multiprocess_pool", "multiprocess", "extra", "pool task", 20, 2, noise_class="noisy"),
)

BY_NAME = {workload.name: workload for workload in WORKLOADS}


def select_workloads(suite: str, profile: str, name: str | None, category: str | None) -> list[Workload]:
    if name is not None and name not in BY_NAME:
        raise ValueError(f"unknown workload: {name}")
    if profile not in {"quick", "standard", "rigorous"}:
        raise ValueError(f"unknown profile: {profile}")
    if suite == "smoke":
        selected = [BY_NAME[n] for n in (
            "python_startup",
            "rust_base64_small",
            "rust_base64_large",
            "serialization_roundtrip",
            "multiprocess_pool",
        )]
    elif suite in {"realworld", "full"}:
        selected = list(WORKLOADS)
        if profile == "quick" and name is None and category is None:
            quick = {"django_wsgi_request", "django_orm_10k", "pycparser_source", "python_startup", "serialization_roundtrip"}
            selected = [w for w in selected if w.name in quick]
    elif suite == "pyperformance":
        selected = []
    else:
        raise ValueError(f"unknown suite: {suite}")
    if name is not None:
        selected = [w for w in selected if w.name == name]
    if category is not None:
        selected = [w for w in selected if w.category == category]
    if not selected and suite != "pyperformance":
        raise ValueError("no workloads selected")
    return selected
