import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

phone_validator = RegexValidator(
    regex=r"^\+7\d{10}$",
    message="Телефон должен быть в формате +7XXXXXXXXXX (11 цифр после +).",
)

# Алфавит для инвайт-кода: цифры + заглавные латинские буквы (base36)
INVITE_CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
INVITE_CODE_LENGTH = 6


def generate_invite_code() -> str:
    """Генерирует 6-символьный код из цифр и заглавных букв."""
    return "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))


def generate_unique_invite_code(max_attempts: int = 20) -> str:
    """Гарантирует уникальность кода в таблице User."""
    for _ in range(max_attempts):
        code = generate_invite_code()
        if not User.objects.filter(invite_code=code).exists():
            return code
    raise RuntimeError("Не удалось сгенерировать уникальный инвайт-код")


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, phone, password, **extra_fields):
        if not phone:
            raise ValueError("Phone number is required")
        user = self.model(phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField(
        "Номер телефона",
        max_length=12,
        unique=True,
        validators=[phone_validator],
        db_index=True,
        help_text="Формат: +7XXXXXXXXXX",
    )
    first_name = models.CharField("Имя", max_length=150, blank=True)
    last_name = models.CharField("Фамилия", max_length=150, blank=True)

    # --- Реферальная система ---
    invite_code = models.CharField(
        "Свой инвайт-код",
        max_length=INVITE_CODE_LENGTH,
        unique=True,
        db_index=True,
        blank=True,
        null=True,
        help_text="6 символов: A-Z0-9. Генерируется автоматически.",
    )
    activated_invite_code = models.CharField(
        "Активированный чужой код",
        max_length=INVITE_CODE_LENGTH,
        blank=True,
        null=True,
        help_text="Можно активировать только один код.",
    )
    referrer = models.ForeignKey(
        "self",
        verbose_name="Пригласивший",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referrals",
    )

    is_active = models.BooleanField("Активен", default=True)
    is_staff = models.BooleanField("Доступ в админку", default=False)

    date_joined = models.DateTimeField("Дата регистрации", default=timezone.now)
    last_login = models.DateTimeField("Последний вход", null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ("-date_joined",)

    def __str__(self):
        return self.phone

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone

    def get_short_name(self):
        return self.first_name or self.phone

    # ---------- реферальная логика ----------

    def can_activate_invite(self):
        return self.activated_invite_code is None

    @transaction.atomic
    def activate_invite(self, code: str):
        """
        Активирует чужой инвайт-код.
        Возвращает referrer User.
        Бросает ValueError с понятным сообщением при ошибке.
        """
        code = (code or "").strip().upper()

        if not self.can_activate_invite():
            raise ValueError("Вы уже активировали инвайт-код.")
        if code == self.invite_code:
            raise ValueError("Нельзя активировать свой собственный код.")

        try:
            referrer = User.objects.select_for_update().get(invite_code=code)
        except User.DoesNotExist as err:
            raise ValueError("Инвайт-код не найден.") from err

        self.activated_invite_code = referrer.invite_code
        self.referrer = referrer
        self.save(update_fields=["activated_invite_code", "referrer"])

        Referral.objects.get_or_create(referrer=referrer, referral=self)
        return referrer


class Referral(models.Model):
    """Журнал: кто кого привёл."""

    referrer = models.ForeignKey(
        User,
        verbose_name="Пригласивший",
        on_delete=models.CASCADE,
        related_name="referral_records",
    )
    referral = models.ForeignKey(
        User,
        verbose_name="Приглашённый",
        on_delete=models.CASCADE,
        related_name="referred_by_records",
    )
    created_at = models.DateTimeField("Дата активации", auto_now_add=True)

    class Meta:
        verbose_name = "Реферал"
        verbose_name_plural = "Рефералы"
        unique_together = ("referrer", "referral")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.referrer.phone} → {self.referral.phone}"


class SMSCode(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "login", "Авторизация"
        REGISTER = "register", "Регистрация"

    phone = models.CharField(
        "Номер телефона",
        max_length=12,
        validators=[phone_validator],
        db_index=True,
    )
    code = models.CharField("Код", max_length=6)
    purpose = models.CharField(
        "Назначение",
        max_length=16,
        choices=Purpose.choices,
        default=Purpose.LOGIN,
    )
    is_used = models.BooleanField("Использован", default=False)
    attempts = models.PositiveSmallIntegerField("Попыток ввода", default=0)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    expires_at = models.DateTimeField("Истекает", db_index=True)

    class Meta:
        verbose_name = "SMS-код"
        verbose_name_plural = "SMS-коды"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["phone", "is_used", "-created_at"]),
        ]

    def __str__(self):
        state = "used" if self.is_used else "active"
        return f"{self.phone} / {self.code} / {state}"

    @classmethod
    def issue(cls, phone, *, purpose=Purpose.LOGIN, ttl_seconds=None, code_length=None):
        ttl_seconds = ttl_seconds or getattr(settings, "SMS_CODE_TTL_SECONDS", 300)
        code_length = code_length or getattr(settings, "SMS_CODE_LENGTH", 4)
        cls.objects.filter(phone=phone, is_used=False).update(is_used=True)
        code = cls._generate_code(code_length)
        return cls.objects.create(
            phone=phone,
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
        )

    @staticmethod
    def _generate_code(length):
        first = str(secrets.randbelow(9) + 1)
        rest = "".join(str(secrets.randbelow(10)) for _ in range(length - 1))
        return first + rest

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired

    def mark_used(self):
        self.is_used = True
        self.save(update_fields=["is_used"])

    def increment_attempts(self):
        self.attempts += 1
        self.save(update_fields=["attempts"])


# ---------- сигнал: генерируем invite_code при создании юзера ----------


@receiver(post_save, sender=User)
def _ensure_invite_code(sender, instance, created, **kwargs):
    if instance.invite_code:
        return
    # Через queryset.update, чтобы не зациклить сигнал
    code = generate_unique_invite_code()
    User.objects.filter(pk=instance.pk).update(invite_code=code)
    instance.invite_code = code
