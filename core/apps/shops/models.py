from django.db import models


class Shop(models.Model):

    name = models.CharField(max_length=200)
    employee_limit = models.IntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name