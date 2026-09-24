"""Run deterministic Django request, ORM materialization, and template workloads.

Invoke this module with a scenario name and iteration count. Django setup,
schema creation, fixture loading, handler initialization, and warm-up requests
are outside the reported elapsed_seconds interval.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any


SCENARIOS = (
    "django_wsgi_request",
    "django_asgi_request",
    "django_orm_10k",
    "django_template_realistic",
)
_DJANGO_VERSION = "6.1.1"
_SETTINGS_MODULE = "benchmarks.workloads.django_app.settings"
_APP_LABEL = "benchmark_django"
_ROW_COUNT = 10_000
_TARGET_ORDINAL = 7
_TARGET_SLUG = f"post-{_TARGET_ORDINAL:05d}"
_TARGET_TITLE = f"Post {_TARGET_ORDINAL:05d}: C++ & <Django>"
_TAG_NAMES = (
    "architecture",
    "async workflows",
    "CPython & runtime",
    "data <models>",
    "Django",
    "indexing",
    "observability",
    "Python & tools",
    "release engineering",
    "search",
    "templates",
    "Unicode café",
)
_AUTHOR_NAMES = (
    "Avery Chen",
    "Morgan O'Neil",
    "Riley Singh",
    "Sam Rivera",
    "Taylor Okafor",
    "Jordan Kim",
    "Casey Dubois",
    "Quinn Patel",
)
_BASE_TIME = datetime(2026, 1, 1, 9, 30)
_LAST_POST_YEAR = str((_BASE_TIME + timedelta(days=_ROW_COUNT - 1)).year)
_APP: _DjangoModels | None = None
_DATABASE_ANCHOR: sqlite3.Connection | None = None


@dataclass(frozen=True)
class RunResult:
    operation_count: int
    elapsed_seconds: float
    digest: str


@dataclass(frozen=True)
class _DjangoModels:
    Author: Any
    Comment: Any
    Post: Any
    Tag: Any


def _bootstrap_application() -> _DjangoModels:
    """Initialize Django and create deterministic in-memory benchmark data."""
    global _APP, _DATABASE_ANCHOR
    if _APP is not None:
        return _APP

    os.environ["DJANGO_SETTINGS_MODULE"] = _SETTINGS_MODULE
    try:
        import django
    except ImportError as exc:
        raise RuntimeError(
            f"Django {_DJANGO_VERSION} and its locked dependencies must be available on PYTHONPATH"
        ) from exc
    if django.get_version() != _DJANGO_VERSION:
        raise RuntimeError(
            f"Django workload requires {_DJANGO_VERSION}, got {django.get_version()}"
        )

    from django.apps import apps
    from django.conf import settings
    from django.db import connection

    if settings.configured and settings.SETTINGS_MODULE != _SETTINGS_MODULE:
        raise RuntimeError(
            "the Django benchmark must run with its own settings module"
        )
    django.setup()

    # Django closes request connections at request_finished, as recommended
    # for ASGI. Keep the shared in-memory SQLite URI alive with a private idle
    # anchor so the next WSGI or ASGI request sees the same seeded tables.
    database = settings.DATABASES["default"]
    _DATABASE_ANCHOR = sqlite3.connect(database["NAME"], uri=True)

    from benchmarks.workloads.django_app.models import Author, Comment, Post, Tag

    with connection.cursor() as cursor:
        # The database is process-private and in memory. Keep fixture writes
        # cheap, then leave the shared in-memory journal available to ASGI's
        # synchronous view thread.
        cursor.execute("PRAGMA journal_mode=MEMORY")
        cursor.execute("PRAGMA synchronous=OFF")

    app_models = apps.get_app_config(_APP_LABEL).get_models()
    with connection.schema_editor() as schema_editor:
        for model in app_models:
            schema_editor.create_model(model)

    _seed_database(Author=Author, Comment=Comment, Post=Post, Tag=Tag)
    _APP = _DjangoModels(Author=Author, Comment=Comment, Post=Post, Tag=Tag)
    return _APP


def _seed_database(*, Author: Any, Comment: Any, Post: Any, Tag: Any) -> None:
    authors = [
        Author(
            name=name,
            email=f"author-{index:02d}@example.test",
            bio=f"Editor {name} writes about Python, deployment, and application design.",
        )
        for index, name in enumerate(_AUTHOR_NAMES)
    ]
    Author.objects.bulk_create(authors)

    tags = [
        Tag(name=name, slug=f"tag-{index:02d}")
        for index, name in enumerate(_TAG_NAMES)
    ]
    Tag.objects.bulk_create(tags)
    authors = list(Author.objects.order_by("id"))
    tags = list(Tag.objects.order_by("id"))

    posts = []
    for ordinal in range(_ROW_COUNT):
        author = authors[ordinal % len(authors)]
        posts.append(
            Post(
                ordinal=ordinal,
                author_id=author.pk,
                title=f"Post {ordinal:05d}: C++ & <Django>",
                slug=f"post-{ordinal:05d}",
                body=(
                    f"Article {ordinal:05d} covers request handling, query planning, "
                    "and Unicode café. Quoted markup <script>review()</script> "
                    "remains text, while ampersands & quotes exercise escaping. "
                    "The application combines author data, tags, dates, and comments."
                ),
                published=True,
                published_at=_BASE_TIME + timedelta(days=ordinal, minutes=ordinal % 60),
                reading_minutes=3 + (ordinal % 18),
                score=Decimal(ordinal % 1000) / Decimal("100"),
            )
        )
    Post.objects.bulk_create(posts, batch_size=500)

    sample_ordinals = tuple(range(16)) + tuple(range(_ROW_COUNT - 16, _ROW_COUNT))
    sample_posts = {
        post.ordinal: post
        for post in Post.objects.filter(ordinal__in=sample_ordinals)
    }
    through_model = Post.tags.through
    tag_links = []
    comments = []
    for ordinal in sample_ordinals:
        post = sample_posts[ordinal]
        for tag_index in (ordinal % len(tags), (ordinal + 3) % len(tags)):
            tag_links.append(
                through_model(post_id=post.pk, tag_id=tags[tag_index].pk)
            )
        for comment_ordinal in range(3):
            comments.append(
                Comment(
                    post_id=post.pk,
                    ordinal=comment_ordinal,
                    display_name=f"Reader {comment_ordinal + 1}",
                    body=(
                        f"Comment {comment_ordinal + 1} on post {ordinal:05d}: "
                        "<script>review()</script> & useful notes."
                    ),
                    created_at=post.published_at
                    + timedelta(hours=comment_ordinal + 1),
                    approved=comment_ordinal < 2,
                )
            )
    through_model.objects.bulk_create(tag_links, batch_size=500)
    Comment.objects.bulk_create(comments, batch_size=500)


def _request_path() -> str:
    return f"/posts/{_TARGET_SLUG}/"


def _validate_post_response(status: int, body: bytes) -> None:
    if status != 200:
        raise AssertionError(f"expected Django request status 200, got {status}")
    document = json.loads(body)
    post = document.get("post")
    if not isinstance(post, dict):
        raise AssertionError("Django request did not return a post object")
    if post.get("slug") != _TARGET_SLUG or post.get("title") != _TARGET_TITLE:
        raise AssertionError("Django request returned the wrong seeded post")
    if post.get("url") != _request_path():
        raise AssertionError("Django request did not generate the canonical URL")
    if len(post.get("tags", ())) != 2 or len(post.get("comments", ())) != 2:
        raise AssertionError("Django request missed prefetched tags or approved comments")
    if post.get("body_word_count", 0) < 20:
        raise AssertionError("Django request returned an incomplete article body")


def _wsgi_exchange(handler: Any) -> tuple[int, bytes]:
    statuses: list[str] = []

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None):
        statuses.append(status)

        def write(chunk: bytes) -> None:
            return None

        return write

    path = _request_path()
    environ = {
        "REQUEST_METHOD": "GET",
        "SCRIPT_NAME": "",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "SERVER_NAME": "testserver",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "HTTP_HOST": "testserver",
        "HTTP_ACCEPT": "application/json",
        "HTTP_ACCEPT_ENCODING": "identity",
        "HTTP_USER_AGENT": "python-build-django-benchmark",
        "REMOTE_ADDR": "127.0.0.1",
        "CONTENT_LENGTH": "0",
        "CONTENT_TYPE": "",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(),
        "wsgi.errors": io.StringIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    response = handler(environ, start_response)
    try:
        body = b"".join(response)
    finally:
        close = getattr(response, "close", None)
        if close is not None:
            close()
    if len(statuses) != 1:
        raise AssertionError(f"WSGI handler called start_response {len(statuses)} times")
    return int(statuses[0].split(" ", 1)[0]), body


def _run_wsgi(iterations: int) -> RunResult:
    from django.core.handlers.wsgi import WSGIHandler

    handler = WSGIHandler()
    expected_status, expected_body = _wsgi_exchange(handler)
    _validate_post_response(expected_status, expected_body)

    started = time.perf_counter()
    for _ in range(iterations):
        status, body = _wsgi_exchange(handler)
        if status != expected_status or body != expected_body:
            raise AssertionError("WSGI response changed during the measured workload")
    elapsed_seconds = time.perf_counter() - started
    return RunResult(
        operation_count=iterations,
        elapsed_seconds=elapsed_seconds,
        digest=hashlib.sha256(expected_body).hexdigest(),
    )


async def _asgi_exchange(handler: Any) -> tuple[int, bytes]:
    messages: list[dict[str, Any]] = []
    request_delivered = False
    disconnect = asyncio.Event()
    path = _request_path()

    async def receive() -> dict[str, Any]:
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        # Keep the connection open until Django finishes the response. Returning
        # http.disconnect here would make the handler cancel a valid request.
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"accept", b"application/json"),
            (b"accept-encoding", b"identity"),
            (b"user-agent", b"python-build-django-benchmark"),
        ],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "state": {},
    }
    await handler(scope, receive, send)

    statuses = [message["status"] for message in messages if message["type"] == "http.response.start"]
    chunks = [
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ]
    if len(statuses) != 1:
        raise AssertionError(f"ASGI handler emitted {len(statuses)} response starts")
    return statuses[0], b"".join(chunks)


async def _measure_asgi(iterations: int) -> RunResult:
    from django.core.handlers.asgi import ASGIHandler

    handler = ASGIHandler()
    expected_status, expected_body = await _asgi_exchange(handler)
    _validate_post_response(expected_status, expected_body)

    started = time.perf_counter()
    for _ in range(iterations):
        status, body = await _asgi_exchange(handler)
        if status != expected_status or body != expected_body:
            raise AssertionError("ASGI response changed during the measured workload")
    elapsed_seconds = time.perf_counter() - started
    return RunResult(
        operation_count=iterations,
        elapsed_seconds=elapsed_seconds,
        digest=hashlib.sha256(expected_body).hexdigest(),
    )


def _digest_orm_rows(rows: list[tuple[Any, ...]]) -> str:
    digest = hashlib.sha256()
    for ordinal, title, body, published_at, score in rows:
        digest.update(str(ordinal).encode("ascii"))
        digest.update(b"\0")
        digest.update(title.encode("utf-8"))
        digest.update(b"\0")
        digest.update(body.encode("utf-8"))
        digest.update(b"\0")
        digest.update(published_at.isoformat().encode("ascii"))
        digest.update(b"\0")
        digest.update(format(score, ".2f").encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _run_orm(iterations: int) -> RunResult:
    app = _bootstrap_application()
    row_count = 0
    elapsed_seconds = 0.0
    result_digest = ""
    for _ in range(iterations):
        started = time.perf_counter()
        rows = list(
            app.Post.objects.order_by("ordinal").values_list(
                "ordinal", "title", "body", "published_at", "score"
            )
        )
        elapsed_seconds += time.perf_counter() - started
        if len(rows) != _ROW_COUNT:
            raise AssertionError(f"expected {_ROW_COUNT} ORM rows, got {len(rows)}")
        if rows[0][0] != 0 or rows[-1][0] != _ROW_COUNT - 1:
            raise AssertionError("ORM materialization returned the wrong row range")
        row_count += len(rows)
        # Hash the complete materialized result outside the measured interval.
        # Each iteration executes a fresh QuerySet and fully materializes rows.
        result_digest = _digest_orm_rows(rows)
    return RunResult(
        operation_count=row_count,
        elapsed_seconds=elapsed_seconds,
        digest=result_digest,
    )


def _template_inputs() -> tuple[Any, dict[str, Any]]:
    from django.db.models import Prefetch
    from django.template.loader import get_template

    app = _bootstrap_application()
    posts = list(
        app.Post.objects.filter(published=True)
        .select_related("author")
        .prefetch_related(
            Prefetch(
                "tags",
                queryset=app.Tag.objects.order_by("slug"),
                to_attr="benchmark_tags",
            ),
            Prefetch(
                "comments",
                queryset=app.Comment.objects.filter(approved=True).order_by("ordinal", "id"),
                to_attr="approved_comments",
            ),
        )
        .order_by("-published_at", "-ordinal")[:12]
    )
    if len(posts) != 12:
        raise AssertionError("realistic template requires twelve seeded posts")
    template = get_template("django_app/post_list.html")
    context = {"page_title": "Engineering journal", "posts": posts}
    return template, context


def _validate_template_output(output: str) -> None:
    required_fragments = (
        "Post 09999: C++ &amp; &lt;Django&gt;",
        'data-url="/posts/post-09999/"',
        _LAST_POST_YEAR,
        "minute read",
        "points",
        "<strong>Published</strong>",
        "&lt;script&gt;review()&lt;/script&gt;",
    )
    for fragment in required_fragments:
        if fragment not in output:
            raise AssertionError(f"realistic Django template omitted {fragment!r}")


def _run_template(iterations: int) -> RunResult:
    template, context = _template_inputs()
    expected_output = template.render(context)
    _validate_template_output(expected_output)

    started = time.perf_counter()
    output = ""
    for _ in range(iterations):
        output = template.render(context)
    elapsed_seconds = time.perf_counter() - started
    if output != expected_output:
        raise AssertionError("template output changed during the measured workload")
    return RunResult(
        operation_count=iterations,
        elapsed_seconds=elapsed_seconds,
        digest=hashlib.sha256(output.encode("utf-8")).hexdigest(),
    )


def run_scenario(scenario: str, iterations: int) -> RunResult:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown Django scenario: {scenario}")
    if iterations < 1:
        raise ValueError("iterations must be a positive integer")

    _bootstrap_application()
    if scenario == "django_wsgi_request":
        return _run_wsgi(iterations)
    if scenario == "django_asgi_request":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_measure_asgi(iterations))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            asyncio.set_event_loop(None)
    if scenario == "django_orm_10k":
        return _run_orm(iterations)
    return _run_template(iterations)


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("iterations must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("iterations must be a positive integer")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--iterations", type=_positive_integer, required=True)
    args = parser.parse_args(argv)
    result = run_scenario(args.scenario, args.iterations)
    print(json.dumps(asdict(result), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
