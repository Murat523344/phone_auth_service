# TB4 — Сервис авторизации по номеру телефона с реферальной системой

Дипломный проект: REST API для авторизации по номеру телефона с одноразовыми SMS-кодами, JWT-аутентификацией и реферальной системой.

[![CI](https://github.com/Murat523344/phone_auth_service/actions/workflows/ci.yml/badge.svg)](https://github.com/Murat523344/phone_auth_service/actions/workflows/ci.yml)

---

## Возможности

### Авторизация по номеру телефона
- Ввод телефона в формате `+7XXXXXXXXXX`
- Отправка одноразового 4-значного кода с имитацией задержки 1–2 секунды
- Инвалидация предыдущих активных кодов при выпуске нового
- Ограничение количества попыток ввода (по умолчанию 5)
- TTL кода — 5 минут
- Автоматическая регистрация пользователя при первом успешном входе
- Выдача пары JWT: access (15 мин) + refresh (7 дней)

### Реферальная система
- Свой 6-символьный инвайт-код (A-Z0-9, генерируется криптографически стойко)
- Активация чужого инвайт-кода — только один раз
- Проверка существования чужого кода и запрет на активацию собственного
- В профиле: свой invite_code, активированный чужой код, список приглашённых
- Журнал рефералов в отдельной таблице Referral

### UI на Django Templates
- /ui/login/ — ввод телефона
- /ui/verify/ — ввод SMS-кода
- /ui/profile/ — профиль, активация чужого кода, список приглашённых
- JWT хранится в HTTP-only cookie

### API-документация
- ReDoc: /api/redoc/
- Swagger UI: /api/docs/
- OpenAPI-схема: /api/schema/

### Инфраструктура
- Docker / Docker Compose (PostgreSQL 16 + Django)
- GitHub Actions: lint (ruff) + tests (pytest)
- 53 теста, покрытие 94%

---

## Стек

| Слой | Технология |
|---|---|
| Язык | Python 3.12 |
| Web-фреймворк | Django 5.2 |
| API | Django REST Framework 3.15 |
| JWT | djangorestframework-simplejwt 5.3 |
| БД | PostgreSQL 16 |
| Драйвер БД | psycopg 3 |
| Документация API | drf-spectacular 0.27 |
| Линтер | ruff 0.4 |
| Тесты | pytest 8, pytest-django, pytest-cov |
| Контейнеризация | Docker, Docker Compose |
| CI | GitHub Actions |

---

## API

Базовый префикс: `/api/v1/auth/`

### 1. POST /request-code/

Запрос одноразового SMS-кода. Имитирует задержку 1–2 секунды.

Request: `{ "phone": "+79991234567" }`

Response 200: `{ "detail": "Код отправлен.", "expires_in": 300, "debug_code": "4371" }`

### 2. POST /verify-code/

Request: `{ "phone": "+79991234567", "code": "4371" }`

Response 200: `{ "user": {...}, "access": "...", "refresh": "..." }`

### 3. POST /refresh/

Request: `{ "refresh": "<token>" }` → Response: `{ "access": "<new_token>" }`

### 4. GET /me/

Краткая информация о текущем пользователе. Требует `Authorization: Bearer <access>`.

### 5. GET /profile/

Полный профиль: `invite_code`, `activated_invite_code`, `referrer_phone`, `invited_users`.

### 6. POST /profile/activate-invite/

Request: `{ "invite_code": "ABC123" }` — активирует чужой код (только один раз).

---

## Быстрый старт (Docker)

```bash
cp .env.template .env
docker compose up --build
```

- API: http://localhost:8000/api/v1/auth/
- UI: http://localhost:8000/ui/login/
- ReDoc: http://localhost:8000/api/redoc/
- Swagger: http://localhost:8000/api/docs/
- Админка: http://localhost:8000/admin/

---

## Быстрый старт (локально)

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
python manage.py migrate
python manage.py runserver
```

---

## Тесты

```bash
pytest -v
pytest --cov=users --cov-report=term-missing
```

Покрытие: 94% (требование ТЗ ≥75%).

---

## Postman-коллекция

Файл `postman_collection.json` в корне проекта. Импорт: Postman → Import → File.

---

## Лицензия

Учебный проект.
