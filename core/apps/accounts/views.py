import logging

from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.accounts.serializers import  ChangePasswordSerializer, LogoutSerializer
from apps.accounts.models import User  
from apps.accounts.jwt import CustomTokenObtainPairSerializer

logger = logging.getLogger(__name__)


# class LoginView(APIView):

#     permission_classes = [AllowAny]

#     def post(self, request):

#         email = (request.data.get("email") or "").strip()
#         password = request.data.get("password") or ""
#         force_login = request.data.get("force_login", False)

#         # Case-insensitive email match, so "Varshil@x.com" == "varshil@x.com".
#         user = User.objects.filter(email__iexact=email).first()

#         if user is None:
#             logger.warning("Login failed: email not found -> %s", email)
#             return Response(
#                 {"error": "Login failed. Invalid email or password"},
#                 status=400,
#             )

#         if not user.check_password(password):
#             logger.warning("Login failed: wrong password for %s", email)
#             return Response(
#                 {"error": "Login failed. Invalid email or password"},
#                 status=400,
#             )

#         if not user.is_active:
#             logger.warning("Login failed: inactive account %s", email)
#             return Response(
#                 {
#                     "error": (
#                         "Your account is inactive. "
#                         "Please contact the administrator."
#                     )
#                 },
#                 status=403,
#             )

#         if user.is_blocked:
#             return Response(
#                 {
#                     "error": (
#                         "Access to your account is currently restricted. "
#                         "Please contact the administrator."
#                     )
#                 },
#                 status=403,
#             )

#         already_logged_in = user.session_active

#         if already_logged_in and not force_login:
#             remaining_attempts = max(0, 3 - user.failed_device_login_count)
#             return Response(
#                 {
#                     "requires_force_login": True,
#                     "message": (
#                         "Account already logged in on another device. "
#                         "Continue and logout other device?"
#                     ),
#                     "remaining_attempts": remaining_attempts,
#                 },
#                 status=409,
#             )

#         if already_logged_in and force_login:
#             user.failed_device_login_count += 1

#             if user.failed_device_login_count > 3:
#                 user.is_blocked = True
#                 user.session_active = False
#                 user.save(
#                     update_fields=[
#                         "failed_device_login_count",
#                         "is_blocked",
#                         "session_active",
#                     ]
#                 )

#                 return Response(
#                     {
#                         "error": (
#                             "Access to your account is currently restricted. "
#                             "Please contact the administrator."
#                         )
#                     },
#                     status=403,
#                 )

#         user.token_version += 1
#         user.session_active = True

#         user.save(
#             update_fields=[
#                 "token_version",
#                 "failed_device_login_count",
#                 "session_active",
#             ]
#         )

#         refresh = CustomTokenObtainPairSerializer.get_token(user)
        
#         return Response({
#             "access": str(refresh.access_token),
#             "refresh": str(refresh),
#             "token_version": user.token_version,
#         })



class LoginView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        email = (request.data.get("email") or "").strip()
        password = request.data.get("password") or ""
        force_login = request.data.get("force_login", False)

        # Case-insensitive email match
        user = User.objects.filter(email__iexact=email).first()

        if user is None:
            logger.warning("Login failed: email not found -> %s", email)
            return Response(
                {"error": "Login failed. Invalid email or password"},
                status=400,
            )

        if not user.check_password(password):
            logger.warning("Login failed: wrong password for %s", email)
            return Response(
                {"error": "Login failed. Invalid email or password"},
                status=400,
            )

        if not user.is_active:
            logger.warning("Login failed: inactive account %s", email)
            return Response(
                {
                    "error": (
                        "Your account is inactive. "
                        "Please contact the administrator."
                    )
                },
                status=403,
            )

        if user.is_blocked:
            return Response(
                {
                    "error": (
                        "Access to your account is currently restricted. "
                        "Please contact the administrator."
                    )
                },
                status=403,
            )

        already_logged_in = user.session_active

        # User already logged in on another device
        if already_logged_in and not force_login:
            return Response(
                {
                    "requires_force_login": True,
                    "message": (
                        "Account already logged in on another device. "
                        "Continue and logout other device?"
                    ),
                },
                status=409,
            )

        # Unlimited force login
        user.token_version += 1
        user.session_active = True

        user.save(
            update_fields=[
                "token_version",
                "session_active",
            ]
        )

        refresh = CustomTokenObtainPairSerializer.get_token(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "token_version": user.token_version,
            }
        )

class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.accounts.feature_access import normalize_feature_access

        user = request.user
        return Response({
            "user_id": user.id,
            "user_name": user.username,
            "email": user.email,
            "shop_name": user.shop.name if user.shop else None,
            "role": user.role,
            "feature_access": normalize_feature_access(
                getattr(user, "feature_access", None)
            ),
        })


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_password = serializer.validated_data["new_password"]

        try:
            validate_password(new_password, request.user)
        except DjangoValidationError as exc:
            return Response({"new_password": exc.messages}, status=400)

        request.user.set_password(new_password)
        request.user.token_version += 1
        request.user.session_active = False
        request.user.save(
            update_fields=[
                "password",
                "token_version",
                "session_active",
            ]
        )

        return Response({"message": "Password changed successfully."}, status=200)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh"]

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response({"error": "Invalid or expired refresh token."}, status=400)

        request.user.session_active = False
        request.user.token_version += 1
        request.user.save(
            update_fields=[
                "session_active",
                "token_version",
            ]
        )

        return Response({"message": "Logout successful."}, status=200)