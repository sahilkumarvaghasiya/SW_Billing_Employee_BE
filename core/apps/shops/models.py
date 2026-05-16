from django.db import models


class Shop(models.Model):

    name = models.CharField(max_length=200)
    employee_limit = models.IntegerField(default=5)
    whatsapp_phone_number_id = models.CharField(max_length=100)
    whatsapp_access_token = models.TextField()
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name