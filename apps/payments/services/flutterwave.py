from django.conf import settings
import requests
import logging

logger = logging.getLogger("payments")

class FlutterwaveService:

    @staticmethod
    def initialize_payment(payment, customer_email, payment_redirect):
        url = f"{settings.FLW_BASE_URL}/payments"

        headers = {
            "Authorization": f"Bearer {settings.FLW_SECRET_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "tx_ref": payment.reference_id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            # For the user's browser (frontend), not webhook URL
            "redirect_url": payment_redirect,
            "customer": {
                "email": customer_email
            },
            "customizations": {
                "title": settings.SHOP_NAME,
            }
        }

        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()

        # For detailed error message for easy debugging on production
        try:
            data = response.json()
        except Exception:
            data = response.text

        if response.status_code != 200 or data.get("status") != "success":
            raise Exception(f"Payment initialization failed: {data}")

        return data["data"]["link"]
    