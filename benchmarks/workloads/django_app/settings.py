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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # URI shared memory keeps the same deterministic database visible to
        # Django's sync thread when ASGI adapts the synchronous ORM view.
        "NAME": f"file:python_build_django_benchmark_{os.getpid()}?mode=memory&cache=shared",
        "OPTIONS": {"uri": True, "timeout": 20},
        # Follow Django's per-request close policy, including on the ASGI
        # handler. django.py holds a separate URI connection as the shared
        # in-memory database anchor while request connections are closed.
        "CONN_MAX_AGE": 0,
    }
}
