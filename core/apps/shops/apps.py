from django.apps import AppConfig


class ShopsConfig(AppConfig):
    name = 'apps.shops'

    def ready(self):
        from apps.shops import signals  # noqa: F401
