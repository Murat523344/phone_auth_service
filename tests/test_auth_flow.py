import pytest
from django.utils import timezone

from users.models import SMSCode, User

PHONE = "+79991234567"

pytestmark = pytest.mark.django_db


class TestSMSCodeModel:
    def test_issue_creates_code_with_ttl(self, settings):
        settings.SMS_CODE_TTL_SECONDS = 300
        sms = SMSCode.issue(PHONE)
        assert sms.phone == PHONE
        assert len(sms.code) == 4
        assert sms.is_valid
        assert not sms.is_used
        assert sms.expires_at > timezone.now()

    def test_issue_invalidates_previous_codes(self):
        first = SMSCode.issue(PHONE)
        second = SMSCode.issue(PHONE)
        first.refresh_from_db()
        assert first.is_used is True
        assert second.is_used is False

    def test_expired_code_is_invalid(self):
        sms = SMSCode.issue(PHONE)
        sms.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        sms.save(update_fields=["expires_at"])
        assert sms.is_expired
        assert not sms.is_valid

    def test_increment_attempts(self):
        sms = SMSCode.issue(PHONE)
        sms.increment_attempts()
        sms.refresh_from_db()
        assert sms.attempts == 1


class TestRequestCodeEndpoint:
    url = "/api/v1/auth/request-code/"

    def test_creates_code_and_returns_debug_code_in_debug(self, client, settings):
        settings.DEBUG = True
        resp = client.post(self.url, {"phone": PHONE}, content_type="application/json")
        assert resp.status_code == 200
        body = resp.json()
        assert "debug_code" in body
        assert SMSCode.objects.filter(phone=PHONE, is_used=False).count() == 1

    def test_rejects_invalid_phone(self, client):
        resp = client.post(self.url, {"phone": "12345"}, content_type="application/json")
        assert resp.status_code == 400
        assert "phone" in resp.json()

    def test_rejects_missing_phone(self, client):
        resp = client.post(self.url, {}, content_type="application/json")
        assert resp.status_code == 400


class TestVerifyCodeEndpoint:
    url = "/api/v1/auth/verify-code/"

    def test_happy_path_returns_tokens_and_user(self, client):
        sms = SMSCode.issue(PHONE)
        resp = client.post(
            self.url,
            {"phone": PHONE, "code": sms.code},
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access" in body and "refresh" in body
        assert body["user"]["phone"] == PHONE
        sms.refresh_from_db()
        assert sms.is_used is True

    def test_creates_user_if_not_exists(self, client):
        sms = SMSCode.issue(PHONE)
        assert User.objects.filter(phone=PHONE).count() == 0
        client.post(
            self.url,
            {"phone": PHONE, "code": sms.code},
            content_type="application/json",
        )
        assert User.objects.filter(phone=PHONE).count() == 1

    def test_wrong_code_increments_attempts(self, client):
        sms = SMSCode.issue(PHONE)
        resp = client.post(
            self.url,
            {"phone": PHONE, "code": "0000"},
            content_type="application/json",
        )
        assert resp.status_code == 400
        sms.refresh_from_db()
        assert sms.attempts == 1

    def test_unknown_phone_returns_error(self, client):
        resp = client.post(
            self.url,
            {"phone": "+79990000000", "code": "1234"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_expired_code_rejected(self, client):
        sms = SMSCode.issue(PHONE)
        sms.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        sms.save(update_fields=["expires_at"])
        resp = client.post(
            self.url,
            {"phone": PHONE, "code": sms.code},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_second_use_of_same_code_rejected(self, client):
        sms = SMSCode.issue(PHONE)
        first = client.post(
            self.url,
            {"phone": PHONE, "code": sms.code},
            content_type="application/json",
        )
        assert first.status_code == 200
        second = client.post(
            self.url,
            {"phone": PHONE, "code": sms.code},
            content_type="application/json",
        )
        assert second.status_code == 400


class TestMeEndpoint:
    url = "/api/v1/auth/me/"

    def test_requires_auth(self, client):
        assert client.get(self.url).status_code == 401

    def test_returns_profile(self, auth_client, user):
        resp = auth_client.get(self.url)
        assert resp.status_code == 200
        assert resp.json()["phone"] == user.phone


class TestRefreshEndpoint:
    url = "/api/v1/auth/refresh/"

    def test_refresh_returns_new_access(self, client):
        sms = SMSCode.issue(PHONE)
        verify = client.post(
            "/api/v1/auth/verify-code/",
            {"phone": PHONE, "code": sms.code},
            content_type="application/json",
        ).json()
        resp = client.post(
            self.url,
            {"refresh": verify["refresh"]},
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "access" in resp.json()
