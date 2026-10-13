from django.urls import path

from .views import MeView, RefreshView, RequestCodeView, VerifyCodeView

app_name = "users"

urlpatterns = [
    path("request-code/", RequestCodeView.as_view(), name="request-code"),
    path("verify-code/", VerifyCodeView.as_view(), name="verify-code"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("me/", MeView.as_view(), name="me"),
]
