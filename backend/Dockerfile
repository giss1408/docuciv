FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir . \
    && groupadd --system docuciv \
    && useradd --system --gid docuciv --no-create-home --shell /usr/sbin/nologin docuciv \
    && chown -R docuciv:docuciv /app

# Non-root container user (docs/security.md §10 "durcissement infra").
USER docuciv

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
