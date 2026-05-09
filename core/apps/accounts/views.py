from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.accounts.serializers import EmployeeCreateSerializer, ChangePasswordSerializer, LogoutSerializer
from apps.accounts.models import User  
from apps.accounts.jwt import CustomTokenObtainPairSerializer

class LoginView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        email = request.data.get("email")
        password = request.data.get("password")
        force_login = request.data.get("force_login", False)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Login failed. Invalid email or password"},
                status=400,
            )

        if user.is_blocked:
            return Response(
                {"error": "Account blocked. Contact admin."},
                status=403,
            )

        user = authenticate(
            username=user.username,
            password=password,
        )

        if user is None:
            return Response(
                {"error": "Login failed. Invalid email or password"},
                status=400,
            )

        already_logged_in = user.token_version > 1

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

        if already_logged_in and force_login:
            user.failed_device_login_count += 1

            if user.failed_device_login_count >= 3:
                user.is_blocked = True
                user.save(
                    update_fields=[
                        "failed_device_login_count",
                        "is_blocked",
                    ]
                )

                return Response(
                    {
                        "error": (
                            "Account blocked due to multiple "
                            "device login attempts."
                        )
                    },
                    status=403,
                )

        user.token_version += 1

        user.save(
            update_fields=[
                "token_version",
                "failed_device_login_count",
            ]
        )

        refresh = CustomTokenObtainPairSerializer.get_token(user)
        
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })

class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "user_id": user.id,
            "user_name": user.username,
            "email": user.email,
            "shop_name": user.shop.name if user.shop else None,
            "role": user.role
        })


class CreateEmployeeView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = EmployeeCreateSerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Employee created"})

        return Response(serializer.errors)


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
        request.user.save(update_fields=["password"])

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

        return Response({"message": "Logout successful."}, status=200)