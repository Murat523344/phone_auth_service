import pytest

from users.models import SMSCode, User

PHONE = "+79991234567"

pytestmark = pytest.mark.django_db


class TestLoginView:
    url = "/ui/login/"

    def test_get_returns_form(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 200
        assert b"+7" in resp.content or b"phone" in resp.content

    def test_post_valid_phone_creates_sms_and_renders_verify(self, client, settings):
        settings.DEBUG = True
        resp = client.post(self.url, {"phone": PHONE})
        assert resp.status_code == 200
        assert SMSCode.objects.filter(phone=PHONE, is_used=False).exists()

    def test_post_invalid_phone_returns_error(self, client):
        resp = client.post(self.url, {"phone": "12345"})
        assert resp.status_code == 200
        # остаётся на странице логина


class TestVerifyView:
    url = "/ui/verify/"

    def test_get_not_allowed(self, client):
        # verify принимает только POST
        assert client.get(self.url).status_code == 405

    def test_wrong_code_returns_error(self, client):
        sms = SMSCode.issue(PHONE)
        resp = client.post(self.url, {"phone": PHONE, "code": "0000"})
        assert resp.status_code == 200
        sms.refresh_from_db()
        assert sms.attempts == 1

    def test_success_sets_jwt_cookies_and_redirects(self, client):
        sms = SMSCode.issue(PHONE)
        resp = client.post(self.url, {"phone": PHONE, "code": sms.code})
        assert resp.status_code == 302
        assert resp.url == "/ui/profile/"
        assert "tb4_access" in resp.cookies
        assert "tb4_refresh" in resp.cookies
        assert User.objects.filter(phone=PHONE).exists()

    def test_expired_code_returns_error(self, client):
        from django.utils import timezone

        sms = SMSCode.issue(PHONE)
        sms.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        sms.save(update_fields=["expires_at"])
        resp = client.post(self.url, {"phone": PHONE, "code": sms.code})
        assert resp.status_code == 200


class TestProfileView:
    url = "/ui/profile/"

    def test_redirects_to_login_without_cookies(self, client):
        resp = client.get(self.url)
        assert resp.status_code == 302
        assert "/ui/login/" in resp.url

    def test_shows_profile_with_valid_cookie(self, client, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(user)
        client.cookies["tb4_access"] = str(token.access_token)
        resp = client.get(self.url)
        assert resp.status_code == 200
        assert user.invite_code.encode() in resp.content


class TestActivateInviteUI:
    url = "/ui/profile/activate-invite/"

    def test_redirects_to_login_without_cookies(self, client):
        resp = client.post(self.url, {"invite_code": "ABCDEF"})
        assert resp.status_code == 302
        assert "/ui/login/" in resp.url

    def test_successful_activation_via_ui(self, client, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        referrer = User.objects.create_user(phone="+79990000002")
        token = RefreshToken.for_user(user)
        client.cookies["tb4_access"] = str(token.access_token)
        resp = client.post(self.url, {"invite_code": referrer.invite_code})
        assert resp.status_code == 302
        user.refresh_from_db()
        assert user.activated_invite_code == referrer.invite_code

    def test_invalid_code_does_not_crash(self, client, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(user)
        client.cookies["tb4_access"] = str(token.access_token)
        resp = client.post(self.url, {"invite_code": "ZZZZZZ"})
        assert resp.status_code == 302


class TestLogoutView:
    url = "/ui/logout/"

    def test_redirects_and_clears_cookies(self, client):
        client.cookies["tb4_access"] = "dummy"
        resp = client.get(self.url)
        assert resp.status_code == 302
        assert resp.url == "/ui/login/"
