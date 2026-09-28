.PHONY: install dev test lint fmt migrate migration password secret db-up preview

install:            ## install Chirp with dev tools
	pip install -e ".[dev]"

dev:                ## run the dashboard locally with reload
	uvicorn app.main:app --reload

test:               ## run all tests
	pytest -q

lint:               ## check style
	ruff check . && ruff format --check .

fmt:                ## auto-format
	ruff check --fix . && ruff format .

db-up:              ## local Postgres with pgvector (Docker)
	docker run -d --name chirp-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=chirp -p 5432:5432 pgvector/pgvector:pg16

migration:          ## autogenerate a migration: make migration m="message"
	alembic revision --autogenerate -m "$(m)"

migrate:            ## apply migrations
	alembic upgrade head

password:           ## hash a dashboard password
	chirp password

secret:             ## generate a random secret
	chirp secret

preview:            ## build a single-file offline preview of the dashboard
	python scripts/build_preview.py
