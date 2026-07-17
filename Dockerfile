FROM node:22-bookworm-slim AS web-build

WORKDIR /src/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS api-build

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

RUN python -m venv "${VIRTUAL_ENV}"
WORKDIR /src/api
COPY api/pyproject.toml ./
COPY api/app ./app
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM python:3.12-slim

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV STRMLINE_STATIC_DIR=/app/static

WORKDIR /app
RUN mkdir -p /config/logs /library \
    && chown -R 1000:1000 /config /library
COPY --from=api-build /opt/venv /opt/venv
COPY api/alembic.ini ./alembic.ini
COPY api/alembic ./alembic
COPY --from=web-build /src/web/build ./static

EXPOSE 45733

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:45733/api/health', timeout=3).read()"

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 45733"]
