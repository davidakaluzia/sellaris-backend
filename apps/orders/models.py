from django.db import models
from django.conf import settings
from uuid import uuid4
from apps.products.models import ProductVariant
from core.utils import get_price_decimal_field


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed"


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # safer than CASCADE
        related_name="orders",
        null=True,
        blank=True
    )

    session_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True
    )

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True
    )

    total_amount = get_price_decimal_field() # temporary snapshot price
    currency = models.CharField(max_length=10, default=settings.DEFAULT_CURRENCY_CHOICE)

    # Snapshot of customer at time of order
    email = models.EmailField()
    phone_number = models.CharField(
        max_length=15, 
        null=True,
        blank=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status", "created_at"]),
            models.Index(fields=["session_id"]),
        ]

    def __str__(self):
        return f"Order {self.id} - {self.status}"


class OrderAddress(models.Model):
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="billing_address"
    )

    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    address_line = models.TextField()
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)

    def __str__(self):
        return f"Billing address for order {self.order_id}"

    def __str__(self):
        return f"Order {self.id} - {self.status}"

class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True
    )

    product_name = models.CharField(max_length=255)  # snapshot
    price = get_price_decimal_field()  # temporary snapshot price
    quantity = models.PositiveIntegerField()

    total_price = get_price_decimal_field()

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
    