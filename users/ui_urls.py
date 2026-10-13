from django.urls import path

from . import ui_views

app_name = "ui"

urlpatterns = [
    path("login/", ui_views.login_view, name="login"),
    path("verify/", ui_views.verify_view, name="verify"),
    path("profile/", ui_views.profile_view, name="profile"),
    path("profile/activate-invite/", ui_views.activate_invite_view, name="activate_invite"),
    path("logout/", ui_views.logout_view, name="logout"),
]
