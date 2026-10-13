# SOURCE-ONLY candidate. No workflow references this recipe; build/install/runtime
# require separate exact reviews and admission. Documentary image is unchanged.
FROM --platform=linux/amd64 python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
ARG REVISION
LABEL org.opencontainers.image.source="https://github.com/u2giants/theoracle" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.title="Oracle analytical source-only candidate"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg
WORKDIR /app
COPY dev/oracle2/analytics/requirements.lock /app/dev/oracle2/analytics/requirements.lock
# Intact hash-verified wheels retain every bundled PuLP CBC binary and notice.
# No editable install, compiler, unpinned resolver, pruning or solver substitution.
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes --no-deps -r /app/dev/oracle2/analytics/requirements.lock
COPY services/oracle-brain/oracle_brain /app/services/oracle-brain/oracle_brain
COPY dev/oracle2/analytics/source-manifest.json /app/dev/oracle2/analytics/source-manifest.json
COPY dev/oracle2/analytics/Dockerfile /app/dev/oracle2/analytics/Dockerfile
COPY dev/oracle2/analytics/Dockerfile.dockerignore /app/dev/oracle2/analytics/Dockerfile.dockerignore
COPY scripts/oracle2/validate_analytical_packet.py /app/scripts/oracle2/validate_analytical_packet.py
RUN groupadd --gid 10002 oracle-analytics && useradd --uid 10002 --gid 10002 --no-create-home --shell /usr/sbin/nologin oracle-analytics
USER 10002:10002
# This candidate exposes no service/API or analytics operation. Default validation
# refuses unavailable qualification/delivery; installation never confers admission.
ENTRYPOINT ["python", "/app/scripts/oracle2/validate_analytical_packet.py"]
