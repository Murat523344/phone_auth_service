import re

import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import Referral, User, generate_invite_code, generate_unique_invite_code

PHONE_1 = "+79991111111"
PHONE_2 = "+79992222222"
PHONE_3 = "+79993333333"

pytestmark = pytest.mark.django_db


# ---------- генерация кода ----------


class TestInviteCodeGeneration:
    def test_code_has_correct_length(self):
        assert len(generate_invite_code()) == 6

    def test_code_uses_allowed_alphabet(self):
        for _ in range(50):
            code = generate_invite_code()
            assert re.fullmatch(r"[A-Z0-9]{6}", code)

    def test_unique_code_function_returns_unique(self):
        codes = {generate_unique_invite_code() for _ in range(20)}
        assert len(codes) == 20

    def test_user_gets_invite_code_on_creation(self):
        user = User.objects.create_user(phone=PHONE_1)
        assert user.invite_code
        assert len(user.invite_code) == 6
        assert user.invite_code.isupper()

    def test_invite_code_is_unique_per_user(self):
        u1 = User.objects.create_user(phone=PHONE_1)
        u2 = User.objects.create_user(phone=PHONE_2)
        assert u1.invite_code != u2.invite_code


# ---------- активация чужого кода ----------


class TestActivateInviteModel:
    def test_can_activate_initially(self):
        u = User.objects.create_user(phone=PHONE_1)
        assert u.can_activate_invite() is True

    def test_successful_activation_sets_fields(self):
        referrer = User.objects.create_user(phone=PHONE_1)
        referral = User.objects.create_user(phone=PHONE_2)

        result = referral.activate_invite(referrer.invite_code)

        assert result == referrer
        referral.refresh_from_db()
        assert referral.referrer_id == referrer.id
        assert referral.activated_invite_code == referrer.invite_code
        assert referral.can_activate_invite() is False

    def test_creates_referral_record(self):
        referrer = User.objects.create_user(phone=PHONE_1)
        referral = User.objects.create_user(phone=PHONE_2)
        referral.activate_invite(referrer.invite_code)
        assert Referral.objects.filter(referrer=referrer, referral=referral).exists()

    def test_cannot_activate_own_code(self):
        u = User.objects.create_user(phone=PHONE_1)
        with pytest.raises(ValueError, match="свой собственный"):
            u.activate_invite(u.invite_code)

    def test_cannot_activate_unknown_code(self):
        u = User.objects.create_user(phone=PHONE_1)
        with pytest.raises(ValueError, match="не найден"):
            u.activate_invite("ZZZZZZ")

    def test_cannot_activate_twice(self):
        referrer1 = User.objects.create_user(phone=PHONE_1)
        referrer2 = User.objects.create_user(phone=PHONE_2)
        referral = User.objects.create_user(phone=PHONE_3)

        referral.activate_invite(referrer1.invite_code)

        with pytest.raises(ValueError, match="уже активировали"):
            referral.activate_invite(referrer2.invite_code)

    def test_code_is_case_insensitive(self):
        referrer = User.objects.create_user(phone=PHONE_1)
        referral = User.objects.create_user(phone=PHONE_2)
        referral.activate_invite(referrer.invite_code.lower())
        referral.refresh_from_db()
        assert referral.activated_invite_code == referrer.invite_code


# ---------- API: профиль ----------


class TestProfileAPI:
    url = "/api/v1/auth/profile/"

    def test_requires_auth(self, api_client):
        assert api_client.get(self.url).status_code == 401

    def test_returns_own_invite_code(self, auth_client, user):
        resp = auth_client.get(self.url)
        assert resp.status_code == 200
        assert resp.json()["invite_code"] == user.invite_code

    def test_returns_empty_invited_list(self, auth_client, user):
        assert auth_client.get(self.url).json()["invited_users"] == []

    def test_returns_invited_users(self, auth_client, user):
        User.objects.create_user(phone=PHONE_2).activate_invite(user.invite_code)
        User.objects.create_user(phone=PHONE_3).activate_invite(user.invite_code)

        invited = auth_client.get(self.url).json()["invited_users"]

        assert len(invited) == 2
        phones = {u["phone"] for u in invited}
        assert phones == {PHONE_2, PHONE_3}

    def test_shows_activated_code_and_referrer(self, api_client, user):
        referrer = User.objects.create_user(phone=PHONE_2)
        user.activate_invite(referrer.invite_code)

        token = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

        body = api_client.get(self.url).json()
        assert body["activated_invite_code"] == referrer.invite_code
        assert body["referrer_phone"] == referrer.phone


# ---------- API: активация чужого кода ----------


class TestActivateInviteAPI:
    url = "/api/v1/auth/profile/activate-invite/"

    def test_requires_auth(self, api_client):
        assert api_client.post(self.url, {"invite_code": "ABCDEF"}).status_code == 401

    def test_successful_activation(self, auth_client, user):
        referrer = User.objects.create_user(phone=PHONE_2)
        resp = auth_client.post(self.url, {"invite_code": referrer.invite_code}, format="json")
        assert resp.status_code == 200
        body = resp.json()
        assert body["activated_invite_code"] == referrer.invite_code
        assert body["referrer_phone"] == referrer.phone

    def test_unknown_code_returns_400(self, auth_client, user):
        resp = auth_client.post(self.url, {"invite_code": "ZZZZZZ"}, format="json")
        assert resp.status_code == 400
        assert "invite_code" in resp.json()

    def test_own_code_returns_400(self, auth_client, user):
        resp = auth_client.post(self.url, {"invite_code": user.invite_code}, format="json")
        assert resp.status_code == 400

    def test_double_activation_returns_400(self, auth_client, user):
        referrer = User.objects.create_user(phone=PHONE_2)
        auth_client.post(self.url, {"invite_code": referrer.invite_code}, format="json")
        referrer2 = User.objects.create_user(phone=PHONE_3)
        resp = auth_client.post(self.url, {"invite_code": referrer2.invite_code}, format="json")
        assert resp.status_code == 400

    def test_code_is_normalized(self, auth_client, user):
        referrer = User.objects.create_user(phone=PHONE_2)
        resp = auth_client.post(
            self.url, {"invite_code": referrer.invite_code.lower()}, format="json"
        )
        assert resp.status_code == 200


# ---------- ТЗ: задержка 1-2 секунды на request-code ----------


class TestRequestCodeDelay:
    url = "/api/v1/auth/request-code/"

    def test_request_code_has_delay(self, client):
        import time

        start = time.monotonic()
        client.post(self.url, {"phone": PHONE_1}, content_type="application/json")
        elapsed = time.monotonic() - start
        # Должно быть не менее 1 секунды (в mock-режиме sleep 1-2 сек)
        assert elapsed >= 0.95, f"Задержка {elapsed:.2f} сек < 1 сек"
