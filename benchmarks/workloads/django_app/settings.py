"""Fixed settings for the isolated, in-process Django benchmark application."""

import os


SECRET_KEY = "python-build-django-benchmark-only"
DEBUG = False
ALLOWED_HOSTS = ["testserver"]
ROOT_URLCONF = "benchmarks.workloads.django_app.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# Keep timestamps as fixed naive values so the workload can run in the Alpine
# benchmark image without a separate system tzdata dependency.
USE_TZ = False
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
APPEND_SLASH = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "benchmarks.workloads.django_app.apps.BenchmarkDjangoConfig",
]

# These are the conventional project middleware layers that participate in
# request parsing, sessions, CSRF handling, messages, and response security.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

_PREPARE_PATH = os.environ.get("BENCH_DJANGO_PREPARE_PATH")
_FIXTURE_PATH = os.environ.get("BENCH_DJANGO_FIXTURE_PATH")
if _PREPARE_PATH and _FIXTURE_PATH:
    raise RuntimeError("Django fixture preparation and consumption cannot overlap")
if _PREPARE_PATH:
    _DATABASE_NAME = _PREPARE_PATH
    _DATABASE_URI = False
elif _FIXTURE_PATH:
    _DATABASE_NAME = f"file:{_FIXTURE_PATH}?mode=ro"
    _DATABASE_URI = True
else:
    _DATABASE_NAME = f"file:python_build_django_benchmark_{os.getpid()}?mode=memory&cache=shared"
    _DATABASE_URI = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Warm requests share process-local memory across ASGI threads. Cold
        # children open the prepared file read-only during their timed process.
        "NAME": _DATABASE_NAME,
        "OPTIONS": {"uri": _DATABASE_URI, "timeout": 20},
        # Request cleanup closes Django's connection. The warm scenario keeps
        # a separate idle connection so its in-memory tables survive.
        "CONN_MAX_AGE": 0,
    }
}
