from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.accounts.serializers import EmployeeCreateSerializer
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
            "user_id": user.id,
            "user_name": user.username,
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