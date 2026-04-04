from rest_framework.permissions import BasePermission
from apps.accounts.models import User


class IsEmployee(BasePermission):
    """
    Allows access only to users with EMPLOYEE role.
    """

    message = "Only employees are allowed to access this API."

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and user.role == User.Role.EMPLOYEE
        )