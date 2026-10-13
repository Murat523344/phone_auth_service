from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import SMSCode

User = get_user_model()


PHONE_REGEX = r"^\+7\d{10}$"


class PhoneSerializer(serializers.Serializer):
    """Запрос SMS-кода: только телефон."""

    phone = serializers.RegexField(
        PHONE_REGEX,
        error_messages={
            "invalid": "Телефон должен быть в формате +7XXXXXXXXXX.",
        },
    )


class VerifyCodeSerializer(serializers.Serializer):
    """Подтверждение кода + телефон. Возвращает JWT."""

    phone = serializers.RegexField(
        PHONE_REGEX,
        error_messages={"invalid": "Телефон должен быть в формате +7XXXXXXXXXX."},
    )
    code = serializers.CharField(min_length=4, max_length=6)

    def validate(self, attrs):
        phone = attrs["phone"]
        code = attrs["code"]

        sms = SMSCode.objects.filter(phone=phone, is_used=False).order_by("-created_at").first()
        if sms is None:
            raise serializers.ValidationError({"code": "Код не найден. Запросите новый."})

        if sms.is_expired:
            raise serializers.ValidationError({"code": "Код истёк. Запросите новый."})

        max_attempts = getattr(settings, "SMS_CODE_MAX_ATTEMPTS", 5)
        if sms.attempts >= max_attempts:
            raise serializers.ValidationError(
                {"code": "Превышено число попыток. Запросите новый код."}
            )

        if sms.code != code:
            sms.increment_attempts()
            raise serializers.ValidationError({"code": "Неверный код."})

        attrs["sms_code"] = sms
        return attrs

    def create(self, validated_data):
        phone = validated_data["phone"]
        sms = validated_data["sms_code"]

        sms.mark_used()

        user, _ = User.objects.get_or_create(phone=phone)
        user.last_login = user.last_login  # placeholder, real update via SimpleJWT

        refresh = RefreshToken.for_user(user)
        return {
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "phone", "first_name", "last_name", "date_joined")
        read_only_fields = ("id", "phone", "date_joined")
