from django.urls import path
from apps.accounts.views import ChangePasswordView, CreateEmployeeView, LoginView, LogoutView, UserDetailView
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("userinfo/", UserDetailView.as_view(), name="user-info"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("create-employee/", CreateEmployeeView.as_view(), name="create-employee"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]