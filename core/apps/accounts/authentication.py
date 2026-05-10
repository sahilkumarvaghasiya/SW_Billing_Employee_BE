from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class SingleDeviceJWTAuthentication(JWTAuthentication):

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