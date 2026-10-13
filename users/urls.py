from django.urls import path

from .views import (
    ActivateInviteView,
    MeView,
    ProfileView,
    RefreshView,
    RequestCodeView,
    VerifyCodeView,
)

app_name = "users"

urlpatterns = [
    path("request-code/", RequestCodeView.as_view(), name="request-code"),
    path("verify-code/", VerifyCodeView.as_view(), name="verify-code"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path(
        "profile/activate-invite/",
        ActivateInviteView.as_view(),
        name="activate-invite",
    ),
]
