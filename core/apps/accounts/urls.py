from django.urls import path
from apps.accounts.views import CreateEmployeeView, LoginView
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("create-employee/", CreateEmployeeView.as_view(), name="create-employee"),
]