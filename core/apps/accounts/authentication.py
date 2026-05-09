from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class SingleDeviceJWTAuthentication(JWTAuthentication):

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        token_version = validated_token.get("token_version")

        if user.token_version != token_version:
            raise AuthenticationFailed(
                "Session expired. Logged in from another device."
            )

        return user