from django.db import connection
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class SingleDeviceJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)

        if user.shop_id:
            connection.set_tenant(user.shop)

        return user, validated_token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if user.is_blocked:
            raise AuthenticationFailed(
                {
                    "code": "USER_BLOCKED",
                    "message": (
                        "Access to your account is currently restricted. "
                        "Please contact the administrator."
                    ),
                }
            )

        if not user.session_active:
            raise AuthenticationFailed(
                {
                    "code": "SESSION_INACTIVE",
                    "message": "Session expired. Please login again.",
                }
            )

        token_version = validated_token.get("token_version")

        if user.token_version != token_version:
            raise AuthenticationFailed(
                {
                    "code": "SESSION_REPLACED",
                    "message": "Logged in from another device",
                }
            )

        return user