from rest_framework import serializers
from apps.accounts.models import User


class EmployeeCreateSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["username", "email", "password"]

    def create(self, validated_data):

        request = self.context["request"]

        if request.user.role != User.Role.MANAGER:
            raise serializers.ValidationError({
                "detail": "Only managers can create employees."
            })

        manager = request.user
        shop = manager.shop

        employee_count = shop.users.filter(role=User.Role.EMPLOYEE).count()

        if employee_count >= shop.employee_limit:
            raise serializers.ValidationError({
                "detail": "You cannot create more employees. Limit reached."
            })

        user = User(
            username=validated_data["username"],
            email=validated_data["email"],
            role=User.Role.EMPLOYEE,
            shop=shop
        )

        user.set_password(validated_data["password"])
        user.save()

        return user


class ChangePasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs.get("new_password") != attrs.get("confirm_password"):
            raise serializers.ValidationError(
                {"confirm_password": ["Confirm password does not match new password."]}
            )
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()