# Documentary native profile; analytical extra remains separately unadmitted.
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS build
ARG REVISION
LABEL org.opencontainers.image.source="https://github.com/u2giants/theoracle" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.title="Oracle isolated documentary native runtime"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    GRAPHITI_TELEMETRY_ENABLED=false ORACLE2_TELEMETRY_MODE=off \
    UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never HNSWLIB_NO_NATIVE=1 \
    PATH="/app/services/oracle-brain/.venv/bin:${PATH}"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir 'uv==0.12.19'
COPY services/oracle-brain/pyproject.toml services/oracle-brain/uv.lock services/oracle-brain/README.md /app/services/oracle-brain/
RUN uv sync --project services/oracle-brain --frozen --no-dev --no-install-project --no-editable
COPY services/oracle-brain/oracle_brain /app/services/oracle-brain/oracle_brain
COPY services/oracle-brain/sql /app/services/oracle-brain/sql
RUN uv sync --project services/oracle-brain --frozen --no-dev --no-editable \
    && python -c "import importlib.util; assert importlib.util.find_spec('pm4py') is None; assert importlib.util.find_spec('pulp') is None" \
    && python -m compileall -q services/oracle-brain/oracle_brain \
    && python -c "from oracle_brain.hosting.gateway import OpaqueGateway; from oracle_brain.operating_model.semantic_runtime import verify_ledger_semantic_acceptance" \
    && rm -rf /root/.cache
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime
ARG REVISION
LABEL org.opencontainers.image.source="https://github.com/u2giants/theoracle" org.opencontainers.image.revision="${REVISION}"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 GRAPHITI_TELEMETRY_ENABLED=false ORACLE2_TELEMETRY_MODE=off PATH="/app/services/oracle-brain/.venv/bin:${PATH}"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=build /app /app
RUN groupadd --gid 10001 oracle-native && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin oracle-native
USER 10001:10001
# Keep the complete stock SDK and native ANN operations qualified in the shipped profile.
RUN python -m oracle_brain.hosting.verify_native_ann
ENTRYPOINT ["python", "-m", "oracle_brain.hosting.runtime"]
CMD ["validate"]
