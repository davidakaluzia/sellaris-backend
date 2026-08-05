from django.urls import path
from .views import PaymentInitializeAPIView, PaymentRecordListView, StaffPaymentRecordListView

urlpatterns = [
    path('all', StaffPaymentRecordListView.as_view()),
    path('', PaymentRecordListView.as_view()),
    path('initialize', PaymentInitializeAPIView.as_view()),
]