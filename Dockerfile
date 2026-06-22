FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY teslamate_supercharger/ ./teslamate_supercharger/

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "python", "-m", "teslamate_supercharger.main"]
