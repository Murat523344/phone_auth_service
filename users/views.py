import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from .models import SMSCode
from .serializers import PhoneSerializer, UserSerializer, VerifyCodeSerializer

logger = logging.getLogger(__name__)


class RequestCodeView(APIView):
    """
    POST /api/v1/auth/request-code/
    body: {"phone": "+79991234567"}
    Отправляет SMS-код (в mock-режиме возвращает код в ответе).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        sms = SMSCode.issue(phone)
        logger.info("Issued SMS code for %s (id=%s)", phone, sms.id)

        # --- Отправка SMS ---
        # Здесь должен быть вызов провайдера. В mock-режиме просто логируем.
        provider = getattr(settings, "SMS_PROVIDER", "mock")
        payload = {
            "detail": "Код отправлен.",
            "expires_in": settings.SMS_CODE_TTL_SECONDS,
        }
        if provider == "mock" or settings.DEBUG:
            payload["debug_code"] = sms.code

        return Response(payload, status=status.HTTP_200_OK)


class VerifyCodeView(APIView):
    """
    POST /api/v1/auth/verify-code/
    body: {"phone": "+79991234567", "code": "1234"}
    Возвращает пару access/refresh + профиль пользователя.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return Response(data, status=status.HTTP_200_OK)


class MeView(APIView):
    """GET /api/v1/auth/me/ — профиль текущего пользователя."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RefreshView(TokenRefreshView):
    """POST /api/v1/auth/refresh/ — обновление access-токена."""

    permission_classes = [AllowAny]
    authentication_classes = []
