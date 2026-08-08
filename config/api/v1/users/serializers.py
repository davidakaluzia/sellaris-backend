from rest_framework import serializers
from uuid import uuid4
from django.contrib.auth import get_user_model

from apps.users.models import Address

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "password", "first_name", "last_name"]

    def create(self, validated_data):
        if not validated_data.get("username"):
            validated_data["username"] = str(uuid4())
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        return user


class UserReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "first_name", 
            "last_name", 
            "username", 
            "date_joined",
            "is_staff",
            "is_superuser",
        ]


class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "password"]

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance
    
    def validate_username(self, value):
        if User.objects.filter(username=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("Username already taken")
        return value


class UserBillingAddressSerializer(serializers.ModelSerializer):
    is_default = serializers.BooleanField(required=False)

    class Meta:
        model = Address
        fields = [
            "id",
            "full_name",
            "phone_number",
            "address_line",
            "city",
            "country",
            "is_default",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        user = self.context["request"].user
        is_default = validated_data.pop("is_default", None)

        address = Address.objects.create(
            user=user,
            is_default=False,
            **validated_data
        )

        has_existing = user.addresses.exclude(id=address.id).exists()
        if not has_existing and is_default is not False:
            address.is_default = True
            address.save(update_fields=["is_default"])

        if is_default is True:
            user.addresses.exclude(id=address.id).update(is_default=False)
            address.is_default = True
            address.save(update_fields=["is_default"])

        return address

    def update(self, instance, validated_data):
        is_default = validated_data.pop("is_default", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if is_default is True:
            user = self.context["request"].user
            user.addresses.exclude(id=instance.id).update(is_default=False)
            instance.is_default = True
        elif is_default is False:
            instance.is_default = False

        instance.save()
        return instance