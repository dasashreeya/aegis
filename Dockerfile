FROM node:24-alpine AS web
WORKDIR /workspace
COPY package.json package-lock.json* ./
COPY apps/web/package.json apps/web/package.json
RUN npm install
COPY apps/web apps/web
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080
WORKDIR /workspace

COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/api/app services/api/app
# The deployed fleet is the real one: ADK orchestration, Gemini on Vertex,
# hosted Model Armor and Cloud Trace. Without these extras the image still
# runs, on the in-process runtime.
RUN pip install --no-cache-dir "./services/api[cloud,agents,telemetry,armor]"

COPY --from=web /workspace/apps/web/dist apps/web/dist

RUN useradd --create-home --uid 1001 aegis && chown -R aegis /workspace
USER aegis

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --app-dir services/api --host 0.0.0.0 --port ${PORT}"]
