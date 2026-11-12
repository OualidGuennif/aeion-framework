# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.15.2-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
FROM ${PYTHON_IMAGE} AS dependencies
COPY AxiomSpec/qa/requirements-qa.txt /tmp/qa.txt
COPY server/requirements.txt server/constraints.txt /tmp/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --only-binary=:all: -c /tmp/constraints.txt -r /tmp/qa.txt -r /tmp/requirements.txt \
    && /opt/venv/bin/pip check

FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="AxiomSpec FastAPI service" \
      org.opencontainers.image.version="1.1.3" \
      org.opencontainers.image.source="https://github.com/OualidGuennif/aeion-framework" \
      org.opencontainers.image.licenses="MIT"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/server" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AXIOM_PORT=8787 \
    AXIOM_MAX_INFLIGHT=8
RUN groupadd --gid 10001 axiom \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin axiom \
    && mkdir /data && chown 10001:10001 /data
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY AxiomSpec /app/AxiomSpec
COPY server/axiom_service /app/server/axiom_service
COPY LICENSE /app/LICENSE
USER 10001:10001
EXPOSE 8787
VOLUME ["/data"]
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('AXIOM_PORT','8787')+'/health/ready',timeout=2).read()"]
ENTRYPOINT ["python", "-m", "axiom_service"]
CMD ["--store", "/data", "--mode", "organization", "--host", "0.0.0.0"]
