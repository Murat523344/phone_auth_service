import logging
import random
import time

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from .models import SMSCode
from .serializers import (
    ActivateInviteSerializer,
    PhoneSerializer,
    ProfileSerializer,
    UserSerializer,
    VerifyCodeSerializer,
)

logger = logging.getLogger(__name__)


class RequestCodeView(APIView):
    """
    POST /api/v1/auth/request-code/
    body: {"phone": "+79991234567"}
    Отправляет SMS-код (в mock-режиме возвращает код в ответе).
    Имитирует задержку отправки SMS 1-2 секунды.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["auth"],
        summary="Запросить SMS-код",
        description="Отправляет 4-значный код на указанный номер. В debug-режиме возвращает debug_code.",
        request=PhoneSerializer,
        responses={
            200: OpenApiResponse(description="Код отправлен"),
            400: OpenApiResponse(description="Неверный формат телефона"),
        },
    )
    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        # Требование ТЗ: имитация задержки отправки SMS 1-2 секунды
        time.sleep(random.uniform(1.0, 2.0))

        sms = SMSCode.issue(phone)
        logger.info("Issued SMS code for %s (id=%s)", phone, sms.id)

        provider = getattr(settings, "SMS_PROVIDER", "mock")
        payload = {
            "detail": "Код отправлен.",
            "expires_in": settings.SMS_CODE_TTL_SECONDS,
        }
        if provider == "mock" or settings.DEBUG:
            payload["debug_code"] = sms.code

        return Response(payload, status=status.HTTP_200_OK)


class VerifyCodeView(APIView):
    """POST /api/v1/auth/verify-code/ — подтверждение кода, выдача JWT."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["auth"],
        summary="Подтвердить SMS-код",
        description="Проверяет код, создаёт пользователя при необходимости, возвращает JWT и профиль.",
        request=VerifyCodeSerializer,
        responses={
            200: OpenApiResponse(description="JWT выдан"),
            400: OpenApiResponse(description="Неверный или истёкший код"),
        },
    )
    def post(self, request):
        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return Response(data, status=status.HTTP_200_OK)


class MeView(APIView):
    """GET /api/v1/auth/me/ — краткая информация о текущем пользователе."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary="Краткий профиль",
        responses={200: UserSerializer},
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ProfileView(APIView):
    """
    GET /api/v1/auth/profile/
    Полный профиль: свой код, активированный чужой, список приглашённых.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["profile"],
        summary="Полный профиль с рефералами",
        description="Возвращает свой invite_code, активированный чужой код и список приглашённых пользователей.",
        responses={200: ProfileSerializer},
    )
    def get(self, request):
        return Response(ProfileSerializer(request.user).data)


class ActivateInviteView(APIView):
    """
    POST /api/v1/auth/profile/activate-invite/
    body: {"invite_code": "ABC123"}
    Активирует чужой инвайт-код. Только один раз.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["profile"],
        summary="Активировать чужой инвайт-код",
        description="Можно активировать только один раз. Нельзя активировать свой собственный код.",
        request=ActivateInviteSerializer,
        responses={
            200: OpenApiResponse(description="Код активирован"),
            400: OpenApiResponse(description="Код не найден / уже активирован / свой собственный"),
        },
    )
    def post(self, request):
        serializer = ActivateInviteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        referrer = serializer.save()
        logger.info("User %s activated invite from %s", request.user.phone, referrer.phone)
        return Response(
            {
                "detail": "Инвайт-код активирован.",
                "activated_invite_code": referrer.invite_code,
                "referrer_phone": referrer.phone,
            },
            status=status.HTTP_200_OK,
        )


class RefreshView(TokenRefreshView):
    """POST /api/v1/auth/refresh/ — обновление access-токена."""

    permission_classes = [AllowAny]
    authentication_classes = []
