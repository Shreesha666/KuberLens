"""
PaperTrading URL routing configuration.
"""
from django.urls import path

from apps.paper_trading import views

app_name = "paper_trading"

urlpatterns = [
    # Phase 3 Order Drawer Endpoints
    path("order/drawer/<str:symbol>/", views.order_drawer_view, name="order_drawer"),
    path("order/place/", views.place_order_view, name="order_place"),
    path("order/estimate-charges/", views.estimate_charges_api, name="estimate_charges"),
]
