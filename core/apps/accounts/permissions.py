from rest_framework.permissions import BasePermission
from apps.accounts.feature_access import FEATURE_LABELS, user_can_access_feature
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


class IsEmployeeWithFeature(BasePermission):
    """Employee access gated by view.feature_access_key (billing/stock/...)."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or user.role != User.Role.EMPLOYEE:
            return False

        feature = getattr(view, "feature_access_key", None)
        if not feature:
            return True

        allowed = user_can_access_feature(user, feature)
        if not allowed:
            label = FEATURE_LABELS.get(feature, feature.title())
            self.message = (
                f"{label} access is disabled for this employee. Contact your manager."
            )
        return allowed