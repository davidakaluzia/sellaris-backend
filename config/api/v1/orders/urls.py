from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderAPIView, StaffOrderListView, StaffOrderStatusUpdateAPIView

# For non-trailing slash
router = DefaultRouter(trailing_slash=False)
router.register('checkout', OrderAPIView,basename='checkout')

urlpatterns = [
    path('all', StaffOrderListView.as_view()),
    path('all/<uuid:pk>/status', StaffOrderStatusUpdateAPIView.as_view()),
    path('', include(router.urls)),
]