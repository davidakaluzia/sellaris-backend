from django.db import transaction
from rest_framework import serializers
from apps.products.models import (
    Category,
    Product,
    ProductVariant,
    Specification,
    ProductImage
)

# =========================
# Category Serializers
# =========================

class CategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Category name cannot be empty.")
        return value


class CategoryReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


# =========================
# Product Serializers
# =========================

class ProductWriteSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        allow_null=True,
        required=False
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "brand",
            "description",
            "category",
            "base_price",
            "currency",
            "slug",
        ]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Product name is too short.")
        return value

    def validate_description(self, value):
        value = value.strip()
        if len(value) > 400:
            raise serializers.ValidationError("Description exceeds 400 characters.")
        return value

    def validate_slug(self, value):
        return value.lower()
    
    def validate(self, attrs):
        price = attrs.get("base_price")
        if price is not None and price <= 0:
            raise serializers.ValidationError("Base price must be greater than zero.")
        return attrs


class ProductReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "brand",
            "description",
            "category",
            "base_price",
            "currency",
            "slug",
        ]


# =========================
# Product Variant Serializers
# =========================

class ProductVariantWriteSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all()
    )

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "sku_code",
            "color",
            "storage_size",
            "price",
            "currency",
            "stock_quantity",
            "reserved_stock",
        ]
        read_only_fields = ["id"]

    def validate_stock_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock quantity cannot be negative.")
        return value


class ProductVariantReadSerializer(serializers.ModelSerializer):
    product = ProductReadSerializer(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "sku_code",
            "color",
            "storage_size",
            "price",
            "currency",
            "stock_quantity",
            "reserved_stock",
        ]


# =========================
# Specification Serializers
# =========================

class SpecificationWriteSerializer(serializers.ModelSerializer):
    product_variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all()
    )

    class Meta:
        model = Specification
        fields = ["id", "product_variant", "name", "value"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        return value.strip().lower()

    def validate_value(self, value):
        return value.strip()


class SpecificationReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specification
        fields = ["id", "name", "value"]


# =========================
# Product Image Serializers
# =========================

class ProductImageWriteSerializer(serializers.ModelSerializer):
    product_variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all()
    )

    class Meta:
        model = ProductImage
        fields = ["id", "product_variant", "image", "is_main"]
        read_only_fields = ["id"]

    def validate_image(self, image):
        # Additional safety beyond model validators
        if image.size > 10 * 1024 * 1024:  # 10MB
            raise serializers.ValidationError("Image must be under 10MB.")
        return image

    def validate(self, attrs):
        # If the new image is marked as main
        if attrs.get("is_main"):
            variant = attrs["product_variant"]

            # Get the current main image for this variant
            current_main_image = ProductImage.objects.filter(
                product_variant=variant, is_main=True
            ).first()

            if current_main_image:
                # Set the current main image to non-main
                current_main_image.is_main = False
                current_main_image.save()

            # No need to check for duplicate 'main' images, just update the new one
            return attrs
        
        return attrs
    
    def create(self, validated_data):
        instance = super().create(validated_data)
        return instance


class ProductImageReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "is_main"]


# =========================
# Composite Read Serializer (Highly Useful)
# =========================

class ProductVariantDetailSerializer(serializers.ModelSerializer):
    product = ProductReadSerializer(read_only=True)
    specifications = SpecificationReadSerializer(many=True, read_only=True)
    images = ProductImageReadSerializer(many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "sku_code",
            "color",
            "storage_size",
            "price",
            "currency",
            "stock_quantity",
            "reserved_stock",
            "specifications",
            "images",
        ]