"""
PaperTrading URL routing configuration.
"""
from django.urls import path

from apps.paper_trading import views

app_name = "paper_trading"

urlpatterns = [
    # Terminal Dashboard
    path("", views.terminal_view, name="terminal"),

    # Order Lifecycle Actions
    path("order/drawer/<str:symbol>/", views.order_drawer_view, name="order_drawer"),
    path("order/place/", views.place_order_view, name="order_place"),
    path("order/cancel/<uuid:order_id>/", views.cancel_order_view, name="order_cancel"),
    path("order/estimate-charges/", views.estimate_charges_api, name="estimate_charges"),

    # Position Actions
    path("position/square-off/<uuid:position_id>/", views.square_off_position_view, name="position_square_off"),

    # Account Actions
    path("account/reset/", views.reset_account_view, name="account_reset"),
]

