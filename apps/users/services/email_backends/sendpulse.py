import requests
from django.conf import settings
from django.core.cache import cache

from apps.users.services.email_service import EmailService


class SendPulseEmailService(EmailService):
    BASE_URL = "https://api.sendpulse.com"

    # We cache access Token to prevent generating new ones on each request
    TOKEN_CACHE_KEY = "sendpulse_access_token"
    TOKEN_TTL = 3000  # ~50 minutes

    def _get_access_token(self):
        token = cache.get(self.TOKEN_CACHE_KEY)

        if token:
            return token
        
        url = f"{self.BASE_URL}/oauth/access_token"

        response = requests.post(url, json={
            "grant_type": "client_credentials",
            "client_id": settings.SENDPULSE_CLIENT_ID,
            "client_secret": settings.SENDPULSE_CLIENT_SECRET,
        })

        response.raise_for_status()
        token = response.json()["access_token"]
        cache.set(self.TOKEN_CACHE_KEY, token, timeout=self.TOKEN_TTL)
        return token

    def send_email(self, to_email, subject, body):
        token = self._get_access_token()

        url = f"{self.BASE_URL}/smtp/emails"

        payload = {
            "email": {
                "subject": subject,
                "html": body,
                "text": body,
                "from": {
                    "name": settings.SHOP_NAME,
                    "email": settings.DEFAULT_FROM_EMAIL,
                },
                "to": [
                    {
                        "email": to_email
                    }
                ]
            }
        }

        headers = {
            "Authorization": f"Bearer {token}"
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()