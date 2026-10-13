from django.conf import settings
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import SMSCode, generate_unique_invite_code

User = get_user_model()

PHONE_REGEX = r"^\+7\d{10}$"


class PhoneSerializer(serializers.Serializer):
    """Запрос SMS-кода: только телефон."""

    phone = serializers.RegexField(
        PHONE_REGEX,
        error_messages={"invalid": "Телефон должен быть в формате +7XXXXXXXXXX."},
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

        if not user.invite_code:
            user.invite_code = generate_unique_invite_code()
            user.save(update_fields=["invite_code"])

        refresh = RefreshToken.for_user(user)
        return {
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "phone", "first_name", "last_name", "invite_code", "date_joined")
        read_only_fields = ("id", "phone", "invite_code", "date_joined")


class ReferralUserSerializer(serializers.ModelSerializer):
    """Краткая информация о юзере для списка рефералов."""

    class Meta:
        model = User
        fields = ("id", "phone", "date_joined")
        read_only_fields = fields


class ProfileSerializer(serializers.ModelSerializer):
    """Полный профиль: свой код, активированный чужой, список приглашённых."""

    invited_users = serializers.SerializerMethodField()
    referrer_phone = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "phone",
            "first_name",
            "last_name",
            "invite_code",
            "activated_invite_code",
            "referrer_phone",
            "invited_users",
            "date_joined",
        )
        read_only_fields = fields

    @extend_schema_field(ReferralUserSerializer(many=True))
    def get_invited_users(self, obj):
        qs = (
            User.objects.filter(referrer=obj)
            .only("id", "phone", "date_joined")
            .order_by("-date_joined")
        )
        return ReferralUserSerializer(qs, many=True).data

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_referrer_phone(self, obj):
        return obj.referrer.phone if obj.referrer_id else None


class ActivateInviteSerializer(serializers.Serializer):
    """Активация чужого инвайт-кода."""

    invite_code = serializers.CharField(min_length=6, max_length=6)

    def validate_invite_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        user = self.context["request"].user
        code = attrs["invite_code"]

        if not user.can_activate_invite():
            raise serializers.ValidationError({"invite_code": "Вы уже активировали инвайт-код."})
        if code == user.invite_code:
            raise serializers.ValidationError(
                {"invite_code": "Нельзя активировать свой собственный код."}
            )
        if not User.objects.filter(invite_code=code).exists():
            raise serializers.ValidationError({"invite_code": "Инвайт-код не найден."})
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        referrer = user.activate_invite(self.validated_data["invite_code"])
        return referrer
