from django.contrib.auth import (
    get_user_model, 
    authenticate, 
    login, 
    logout
)
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from datetime import timedelta
import logging

from apps.users.services.transfer_ownership import transfer_guest_data_to_user
from apps.users.tokens import email_verification_token
from apps.users.oauth.providers.google import GoogleOAuthService
from apps.users.oauth.providers.facebook import FacebookOAuthService
from apps.users.oauth.providers.apple import AppleOAuthService
from apps.users.oauth.oauth_service import OAuthService
from core.utils import generate_dynamic_url
from tasks.cleanup_data import delete_user_account
from tasks.send_email import send_verification_email_task
from .serializers import (
    RegisterSerializer, 
    UserUpdateSerializer, 
    UserReadSerializer,
    UserBillingAddressSerializer,
)
from apps.users.throttles import (
    RegisterThrottle,
    LoginThrottle,
    VerifyEmailThrottle,
    ResendVerificationThrottle,
    OAuthThrottle
)

logger = logging.getLogger("users")

User = get_user_model()


class RegisterAPIView(APIView):
    throttle_classes = [RegisterThrottle]

    def post(self, request):
        '''
            Required request params: email, password, first_name, last_name
        '''
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        # Verify user's email
        send_verification_email_task.delay(user.id, generate_dynamic_url(request, settings.VERIFY_EMAIL_PATH))

        # Transfer guest data
        transfer_guest_data_to_user(request, user)

        return Response(
            {"message": "User created. Check your email to verify."},
            status=status.HTTP_201_CREATED
        )


class LoginAPIView(APIView):
    throttle_classes = [LoginThrottle]

    def post(self, request):
        '''
            Required request params: email & password
        '''
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, email=email, password=password)

        if not user:
            return Response(
                {"detail": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check if User is verified
        if not user.is_verified:
            #send_verification_email_task.delay()
            return Response(
                {"detail": f"Email not verified"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not user.is_active:
            if user.deletion_scheduled_at:
                # Reactivate
                user.is_active = True
                user.deletion_scheduled_at = None
                user.save()
            else:
                raise AuthenticationFailed("Account disabled")

        login(request, user)

        # Transfer guest data AFTER login
        transfer_guest_data_to_user(request, user)

        return Response(
            {"message": "Login successful"},
            status=status.HTTP_200_OK
        )
    
# Set CSRF cookie securely instead of returning it in JSON
@ensure_csrf_cookie
def get_csrf(request):
    return JsonResponse({"detail": "CSRF cookie set"})


class VerifyEmailAPIView(APIView):
    throttle_classes = [VerifyEmailThrottle]

    def get(self, request):
        uid = request.query_params.get("uid")
        token = request.query_params.get("token")

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except Exception:
            return Response({"detail": "Invalid link"}, status=status.HTTP_400_BAD_REQUEST)

        if email_verification_token.check_token(user, token):
            user.is_verified = True
            user.save(update_fields=["is_verified"])

            return Response({"message": "Email verified"}, status=status.HTTP_200_OK)

        return Response({"detail": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)
    

class ResendVerificationAPIView(APIView):
    throttle_classes = [ResendVerificationThrottle]

    def post(self, request):
        email = request.data.get("email")

        user = User.objects.filter(email=email).first()

        if user and not user.is_verified:
            send_verification_email_task.delay(user.id, generate_dynamic_url(request, settings.VERIFY_EMAIL_PATH))

        return Response({"message": "If account exists, email sent"})


class AccountUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"detail": "Account updated successfully"})


class AccountInfoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        serializer = UserReadSerializer(user)
        return Response(serializer.data)


class UserBillingAddressListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserBillingAddressSerializer

    def get_queryset(self):
        return self.request.user.addresses.all().order_by("-is_default", "id")

    def perform_create(self, serializer):
        address = serializer.save()

        if address.is_default:
            self.request.user.addresses.exclude(id=address.id).update(is_default=False)

        return address


class UserBillingAddressDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserBillingAddressSerializer
    lookup_field = "pk"

    def get_queryset(self):
        return self.request.user.addresses.all()

    def perform_update(self, serializer):
        address = serializer.save()

        if address.is_default:
            self.request.user.addresses.exclude(id=address.id).update(is_default=False)

        return address

    def perform_destroy(self, instance):
        was_default = instance.is_default
        user = self.request.user

        instance.delete()

        if was_default:
            replacement = user.addresses.order_by("-id").first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=["is_default"])


class UserBillingAddressDefaultAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        billing_address = request.user.addresses.filter(is_default=True).first()

        if not billing_address:
            return Response(
                {"detail": "No default billing address found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UserBillingAddressSerializer(billing_address)
        return Response(serializer.data)

    def patch(self, request):
        billing_address = request.user.addresses.filter(is_default=True).first()

        if not billing_address:
            return Response(
                {"detail": "No default billing address found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UserBillingAddressSerializer(
            billing_address,
            data=request.data,
            partial=True,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        address = serializer.save()

        if address.is_default:
            request.user.addresses.exclude(id=address.id).update(is_default=False)

        return Response(serializer.data)


class DeleteAccountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        password = request.data.get("password")

        if not password or not user.check_password(password):
            return Response(
                {"detail": "Invalid password"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if account is already deactivated
        if user.deletion_scheduled_at:
            return Response(
                {"detail": "Deletion already scheduled"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Soft delete
        user.is_active = False
        user.save()

        logout(request)

        # Schedule deletion
        delete_user_account.apply_async(
            args=[user.id],
            eta=timezone.now() + timedelta(days=30)
        )

        return Response(
            {"detail": "Account deactivated. It will be permanently deleted in 30 days."},
            status=status.HTTP_202_ACCEPTED
        )


class GoogleOAuthAPIView(APIView):
    throttle_classes = [OAuthThrottle]

    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response({"detail": "Token required"}, status=status.HTTP_400_BAD_REQUEST)

        google_service = GoogleOAuthService()
        user_data = google_service.verify_token(token)

        if not user_data:
            return Response({"detail": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

        oauth_service = OAuthService()
        user = oauth_service.handle_oauth_login("google", user_data)

        login(request, user)

        # transfer ownership
        transfer_guest_data_to_user(request, user)

        return Response(
            {"message": "Login successful"},
            status=status.HTTP_200_OK
        )


class FacebookOAuthAPIView(APIView):
    throttle_classes = [OAuthThrottle]

    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response({"detail": "Token required"}, status=status.HTTP_400_BAD_REQUEST)

        fb_service = FacebookOAuthService()
        user_data = fb_service.verify_token(token)

        if not user_data:
            return Response({"detail": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

        # Email may be missing
        if not user_data.get("email"):
            return Response(
                {"detail": "Email permission required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        oauth_service = OAuthService()
        user = oauth_service.handle_oauth_login("facebook", user_data)

        login(request, user)

        # ownership transfer
        transfer_guest_data_to_user(request, user)

        return Response(
            {"message": "Login successful"},
            status=status.HTTP_200_OK
        )
    

class AppleOAuthAPIView(APIView):
    throttle_classes = [OAuthThrottle]

    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response({"detail": "Token required"}, status=status.HTTP_400_BAD_REQUEST)

        apple_service = AppleOAuthService()
        user_data = apple_service.verify_token(token)

        if not user_data:
            return Response({"detail": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

        provider_user_id = user_data["provider_user_id"]

        # Handle missing email (VERY IMPORTANT)
        if not user_data.get("email"):
            # fallback: get from existing provider mapping
            from apps.users.models import UserAuthProvider

            provider = UserAuthProvider.objects.filter(
                provider="apple",
                provider_user_id=provider_user_id
            ).select_related("user").first()

            if not provider:
                return Response(
                    {"detail": "Email not provided by Apple"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user = provider.user
        else:
            oauth_service = OAuthService()
            user = oauth_service.handle_oauth_login("apple", user_data)

        login(request, user)

        transfer_guest_data_to_user(request, user)

        return Response(
            {"message": "Login successful"},
            status=status.HTTP_200_OK
        )