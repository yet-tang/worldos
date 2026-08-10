FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.13-slim AS runtime

ARG VCS_REF="unknown"
ARG VERSION="dev"
LABEL org.opencontainers.image.title="WorldOS" \
      org.opencontainers.image.description="Event-sourced deterministic world simulation runtime" \
      org.opencontainers.image.source="https://github.com/yet-tang/worldos" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$VERSION"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORLDOS_DB=/data/world.db \
    WORLDOS_HOST=0.0.0.0 \
    WORLDOS_PORT=8765 \
    WORLDOS_VCS_REF=$VCS_REF \
    WORLDOS_VERSION=$VERSION

RUN groupadd --gid 10001 worldos \
    && useradd --uid 10001 --gid worldos --create-home --shell /usr/sbin/nologin worldos \
    && mkdir -p /data /backups \
    && chown -R worldos:worldos /data /backups

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels
COPY docker/entrypoint.sh /usr/local/bin/worldos-entrypoint
RUN chmod 0755 /usr/local/bin/worldos-entrypoint

USER worldos
WORKDIR /home/worldos
EXPOSE 8765
VOLUME ["/data", "/backups"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/' % os.environ.get('WORLDOS_PORT','8765'), timeout=3).read(1)" || exit 1

ENTRYPOINT ["worldos-entrypoint"]
CMD ["inspector"]
