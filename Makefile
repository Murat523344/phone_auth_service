.PHONY: help install migrate test lint fmt up down

help:
	@echo "make install  — установить зависимости"
	@echo "make migrate  — применить миграции"
	@echo "make test     — прогнать тесты"
	@echo "make lint     — ruff check"
	@echo "make fmt      — ruff format + fix"
	@echo "make up       — docker compose up --build"
	@echo "make down     — docker compose down"

install:
	pip install -r requirements.txt

migrate:
	python manage.py migrate

test:
	pytest -v

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff check --fix .
	ruff format .

up:
	docker compose up --build

down:
	docker compose down
