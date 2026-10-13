import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from users.models import SMSCode

User = get_user_model()

PHONE = "+79991234567"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone=PHONE)


@pytest.fixture
def sms_code(db):
    return SMSCode.issue(PHONE)


@pytest.fixture
def auth_client(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    token = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return api_client
