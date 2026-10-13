import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import SMSCode

logger = logging.getLogger(__name__)
User = get_user_model()

ACCESS_COOKIE = getattr(settings, "JWT_ACCESS_COOKIE", "tb4_access")
REFRESH_COOKIE = getattr(settings, "JWT_REFRESH_COOKIE", "tb4_refresh")


def _set_jwt_cookies(response, user):
    refresh = RefreshToken.for_user(user)
    response.set_cookie(
        ACCESS_COOKIE,
        str(refresh.access_token),
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
    )
    response.set_cookie(
        REFRESH_COOKIE,
        str(refresh),
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
    )


def _clear_jwt_cookies(response):
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE)


def _get_user_from_cookies(request):
    token = request.COOKIES.get(ACCESS_COOKIE)
    if not token:
        return None
    try:
        access = AccessToken(token)
        user_id = access["user_id"]
        return User.objects.filter(pk=user_id, is_active=True).first()
    except Exception:
        return None


# ---------- UI views ----------


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        phone = (request.POST.get("phone") or "").strip()
        if not phone.startswith("+7") or len(phone) != 12 or not phone[1:].isdigit():
            messages.error(request, "Неверный формат. Пример: +79991234567")
            return render(request, "users/login.html", {"phone": phone})

        sms = SMSCode.issue(phone)
        logger.info("UI: issued SMS code for %s", phone)
        debug_code = sms.code if (settings.DEBUG or settings.SMS_PROVIDER == "mock") else None
        if debug_code:
            messages.success(request, f"Код отправлен. В режиме отладки: {debug_code}")
        return render(request, "users/verify.html", {"phone": phone})

    return render(request, "users/login.html")


@require_http_methods(["POST"])
def verify_view(request):
    phone = (request.POST.get("phone") or "").strip()
    code = (request.POST.get("code") or "").strip()

    sms = SMSCode.objects.filter(phone=phone, is_used=False).order_by("-created_at").first()
    if sms is None or sms.is_expired:
        messages.error(request, "Код истёк или не найден. Запросите новый.")
        return render(request, "users/verify.html", {"phone": phone})

    if sms.code != code:
        sms.increment_attempts()
        messages.error(request, "Неверный код.")
        return render(request, "users/verify.html", {"phone": phone})

    sms.mark_used()

    user, _ = User.objects.get_or_create(phone=phone)
    if not user.invite_code:
        from .models import generate_unique_invite_code

        user.invite_code = generate_unique_invite_code()
        user.save(update_fields=["invite_code"])

    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    response = redirect("ui:profile")
    _set_jwt_cookies(response, user)
    messages.success(request, "Вы вошли в систему.")
    return response


@require_http_methods(["GET"])
def profile_view(request):
    user = _get_user_from_cookies(request)
    if not user:
        messages.error(request, "Сессия истекла. Войдите заново.")
        return redirect("ui:login")

    invited_users = (
        User.objects.filter(referrer=user).only("phone", "date_joined").order_by("-date_joined")
    )

    return render(
        request,
        "users/profile.html",
        {"user": user, "invited_users": invited_users},
    )


@require_http_methods(["POST"])
def activate_invite_view(request):
    user = _get_user_from_cookies(request)
    if not user:
        messages.error(request, "Сессия истекла.")
        return redirect("ui:login")

    code = (request.POST.get("invite_code") or "").strip().upper()
    try:
        referrer = user.activate_invite(code)
        messages.success(request, f"Код активирован. Вас пригласил {referrer.phone}.")
    except ValueError as err:
        messages.error(request, str(err))
    return redirect("ui:profile")


@require_http_methods(["GET", "POST"])
def logout_view(request):
    response = redirect("ui:login")
    _clear_jwt_cookies(response)
    return response
