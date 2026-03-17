from django.db import models

class SystemSetting(models.Model):
    """Stores key-value pairs for global system configuration."""
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get_setting(cls, key, default=''):
        obj, created = cls.objects.get_or_create(key=key, defaults={'value': default})
        return obj.value

    @classmethod
    def set_setting(cls, key, value):
        obj, created = cls.objects.get_or_create(key=key)
        obj.value = str(value)
        obj.save()
