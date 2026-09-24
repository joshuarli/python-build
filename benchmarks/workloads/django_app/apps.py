from django.apps import AppConfig


class BenchmarkDjangoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "benchmarks.workloads.django_app"
    label = "benchmark_django"
