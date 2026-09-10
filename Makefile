.PHONY: help install up down migrate seed api worker beat test lint fmt

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

install:  ## install package + dev deps
	pip install -e ".[dev]"

up:       ## start infra containers (pg, redis, qdrant, mailhog)
	docker compose up -d postgres redis qdrant mailhog

down:     ## stop all containers
	docker compose down

migrate:  ## run alembic migrations
	alembic upgrade head

seed:     ## load demo data
	python scripts/seed_data.py

api:      ## run the API with reload
	uvicorn app.main:app --reload

worker:   ## run a celery worker
	celery -A app.workers.celery_app worker -l info

beat:     ## run celery beat
	celery -A app.workers.celery_app beat -l info

test:     ## run tests
	pytest -q

lint:     ## ruff + mypy
	ruff check app tests && mypy app

fmt:      ## ruff format + import sort
	ruff format app tests && ruff check --fix app tests
