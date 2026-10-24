# syntax=docker/dockerfile:1.7
# Single image: Oxidized + Oxidized UI + Caddy + supervisord.
# The multi-container Dockerfile remains available as the hardened deployment.

FROM node:22-alpine AS frontend

RUN npm install --global pnpm@10.33.0
WORKDIR /build
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/.npmrc ./
RUN pnpm install --frozen-lockfile --prefer-offline
RUN pnpm rebuild esbuild
COPY frontend/ ./
RUN pnpm build

FROM oxidized/oxidized:0.37.0 AS python-deps

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip build-essential libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
WORKDIR /build
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN /opt/venv/bin/pip install --no-cache-dir .

FROM oxidized/oxidized:0.37.0

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    UI_DOMAIN=oxidized.local \
    UI_HTTPS_PORT=443 \
    STATIC_DIR=/app/static \
    LOCALES_DIR=/app/locales \
    DATA_DIR=/data \
    OXIDIZED_CONFIG_DIR=/oxidized-config \
    HOME=/home/oxidized \
    TMPDIR=/tmp

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 supervisor caddy openssh-client git tzdata curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app /data /oxidized-config /var/lib/oxidized /var/log/supervisor \
    && chown -R 30000:30000 /data /oxidized-config /var/lib/oxidized

COPY --from=python-deps /opt/venv /opt/venv
WORKDIR /app
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY --from=frontend /build/dist ./static
COPY --from=frontend /build/public/locales ./locales
COPY docker/Caddyfile.single /etc/caddy/Caddyfile
COPY docker/single/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/single/entrypoint.sh /usr/local/bin/oxidized-single-entrypoint
COPY docker/single/oxidized-run.sh /usr/local/bin/oxidized-single-run

RUN sed -i 's/\r$//' /usr/local/bin/oxidized-single-entrypoint /usr/local/bin/oxidized-single-run \
    && chmod 0755 /usr/local/bin/oxidized-single-entrypoint /usr/local/bin/oxidized-single-run \
    && chmod -R a+rX /app

EXPOSE 80 443 8080 8888
HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=5 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3).read()"

ENTRYPOINT ["/usr/local/bin/oxidized-single-entrypoint"]
