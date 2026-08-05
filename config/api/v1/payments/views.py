from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response
from rest_framework import status

from core.permissions import IsStaffUser

import logging

from apps.orders.models import Order
from apps.payments.models import Payment, PaymentStatus
from apps.payments.services.factory import get_payment_service
from core.utils import generate_dynamic_url
from .serializers import PaymentRecordReadSerializer


logger = logging.getLogger("payments")
    

class PaymentInitializeAPIView(APIView):

    @transaction.atomic
    def post(self, request):
        '''
        NOTE: This also requires `order_id`, and `provider` name
        ie. paystack or flutterwave
        '''
        order_id = request.data.get("order_id", "")
        provider = str(request.data.get("provider", "")).strip()

        if not order_id:
            return Response(
                {"detail":"missing parameter: order_id"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not provider:
            return Response(
                {"detail":"missing parameter: provider"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if provider not in ["flutterwave", "paystack"]:
            return Response(
                {"detail":"Supported payment providers are 'flutterwave' or 'paystack'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        order = Order.objects.select_for_update().get(id=order_id)

        # Ownership Check FIRST
        if request.user.is_authenticated:
            if order.user != request.user:
                raise PermissionDenied()
        else:
            if order.session_id != request.session.session_key:
                raise PermissionDenied()

        # Status Validation
        if order.status.upper() == "PAID":
            raise ValidationError("Order already paid")

        if order.status.upper() != "PENDING":
            raise ValidationError("Invalid order state")

        # IDEMPOTENCY CHECK
        existing_payment = Payment.objects.filter(
            order=order,
            status="INITIALIZED"
        ).first()

        if existing_payment:
            return Response({
                "payment_link": existing_payment.payment_link,
                "tx_ref": existing_payment.tx_ref,
                "message": "Reusing existing payment"
            })
        
        # PAYMENT PROVIDER VALIDATION
        payment_service = get_payment_service(provider)
        
        # CREATE PAYMENT
        payment = Payment.objects.create(
            order=order,
            provider=provider,
            amount=order.total_amount,
            status=PaymentStatus.INITIALIZED
        )

        logger.info(f"Payment created: {payment.reference_id}")

        # CALL GATEWAY
        payment_link = payment_service.initialize_payment(
            payment=payment,
            customer_email=order.email,
            payment_redirect=generate_dynamic_url(request, settings.PAYMENT_REDIRECT_PATH),
        )

        logger.info(f"Payment initialized: {payment.reference_id}")

        # STORE LINK, just incase an error occur, customer can try again
        payment.payment_link = payment_link
        payment.save(update_fields=["payment_link"])

        return Response({
            "payment_link": payment_link,
            "reference_id": payment.reference_id
        })


class PaymentRecordListView(ListAPIView):
    serializer_class = PaymentRecordReadSerializer
    permission_classes = [AllowAny]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "status",
        "provider",
        "currency",
    ]

    search_fields = [
        "reference_id",
        "=transaction_id",
        "order__id",
    ]

    ordering_fields = [
        "created_at",
        "confirmed_at",
        "amount",
    ]

    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user

        queryset = Payment.objects.select_related("order")

        # Authenticated users → their own orders
        if user.is_authenticated:
            return queryset.filter(order__user=user)

        # Guest users → session-based access
        session_key = self.request.session.session_key

        if not session_key:
            return queryset.none()

        return queryset.filter(order__session_id=session_key)


class StaffPaymentRecordListView(ListAPIView):
    serializer_class = PaymentRecordReadSerializer
    permission_classes = [IsStaffUser]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "status",
        "provider",
        "currency",
    ]

    search_fields = [
        "reference_id",
        "=transaction_id",
        "order__id",
    ]

    ordering_fields = [
        "created_at",
        "confirmed_at",
        "amount",
        "status",
    ]

    ordering = ["-created_at"]

    def get_queryset(self):
        return Payment.objects.select_related("order").all()