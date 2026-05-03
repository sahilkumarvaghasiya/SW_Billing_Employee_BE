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


class LoginView(APIView):

    permission_classes = [AllowAny]
    
    def post(self, request):

        email = request.data.get("email")
        password = request.data.get("password")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "Login failed. Invalid email or password"}, status=400)

        user = authenticate(username=user.username, password=password)

        if user is None:
            return Response({"error": "Login failed. Invalid email or password"}, status=400)
        
        if user is None:
            return Response({"error": "Login failed. Invalid email or password"}, status=400)

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            # "user_id": user.id,
            # "user_name": user.username,
            # "shop_name": user.shop.name if user.shop else None,
            # "role": user.role
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