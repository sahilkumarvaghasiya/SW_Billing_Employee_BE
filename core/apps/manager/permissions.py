from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class IsManager(BasePermission):
    message = "Only managers are allowed to access this API."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.MANAGER
        )
