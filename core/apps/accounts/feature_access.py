"""Per-employee app section access (matches Employee FE radial menu)."""

EMPLOYEE_FEATURES = (
    "billing",
    "stock",
    "products",
    "sales",
    "payable",
)

FEATURE_LABELS = {
    "billing": "Billing",
    "stock": "Stock",
    "products": "Products",
    "sales": "Sales",
    "payable": "Payable",
}


def default_feature_access():
    return {key: True for key in EMPLOYEE_FEATURES}


def normalize_feature_access(raw):
    """Return a full feature map. Missing keys default to True (allowed)."""
    result = default_feature_access()
    if isinstance(raw, dict):
        for key in EMPLOYEE_FEATURES:
            if key in raw:
                result[key] = bool(raw[key])
    return result


def user_can_access_feature(user, feature):
    if not user or not getattr(user, "is_authenticated", False):
        return False

    from apps.accounts.models import User

    if getattr(user, "role", None) == User.Role.MANAGER:
        return True
    if getattr(user, "role", None) != User.Role.EMPLOYEE:
        return False

    access = normalize_feature_access(getattr(user, "feature_access", None))
    return bool(access.get(feature, True))
