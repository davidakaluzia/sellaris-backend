from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings
from django.template.loader import render_to_string

from apps.users.tokens import email_verification_token
from .email_factory import get_email_service


def send_verification_email(user, verify_url):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)

    verify_email_url = f"{verify_url}?uid={uid}&token={token}"

    context = {
        "verify_url": verify_email_url,
        "shop_name": settings.SHOP_NAME,
        "brand_color": settings.BRAND_COLOR,
    }

    template_name = "emails/verify_email_dev.html" if settings.DEBUG else "emails/verify_email_prod.html"
    html_content = render_to_string(template_name, context)

    subject = f"Verify your email for {settings.SHOP_NAME}"
    body = f"Click to verify your {settings.SHOP_NAME} email: {verify_email_url}"  # fallback

    email_service = get_email_service()
    email_service.send_email(user.email, subject, body, html_content)