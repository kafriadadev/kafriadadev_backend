# The domain tier.
#
# Two stages so the image that runs in staging carries no compiler, no pip cache
# and no build tools — the smaller the image, the smaller the thing to patch.
#
# NOTE: not yet built or run anywhere. Docker is not installed on the machine
# this was written on, so the CI image job is the first thing that will execute
# it. See docs/deploy-runbook.md.

FROM python:3.13-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY pyproject.toml ./
COPY src ./src

# A virtualenv rather than --user, so the whole tree can be copied in one layer.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install .

# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# curl is here for the container healthcheck and for nothing else.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Never root. A remote code execution in a web framework should not also be a
# root shell in the container.
RUN useradd --create-home --uid 10001 kafriada
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
USER kafriada

# 8010 rather than 8000, matching every other environment: a port that differs
# between local and deployed is a support call waiting to happen. A platform that
# assigns the port (Render, Railway, Fly) sets $PORT, and that wins.
ENV PORT=8010
EXPOSE 8010

# Readiness, not liveness: the orchestrator should not send traffic to a process
# that cannot reach its database. Liveness is /healthz and is checked by the
# platform's own restart policy.
HEALTHCHECK --interval=15s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/readyz" || exit 1

# One worker per container; scale by running more containers. Argon2 is CPU work
# with its own concurrency cap inside the process, and two workers on one small
# instance would fight over the same cores.
# Shell form, so $PORT is read when the container starts.
CMD exec uvicorn kafriada.main:app \
     --host 0.0.0.0 --port "${PORT}" \
     --proxy-headers --forwarded-allow-ips "*" \
     --no-server-header --timeout-keep-alive 20
