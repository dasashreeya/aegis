FROM node:24-alpine AS web
WORKDIR /workspace
COPY package.json package-lock.json* ./
COPY apps/web/package.json apps/web/package.json
RUN npm install
COPY apps/web apps/web
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /workspace
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/api/app services/api/app
RUN pip install --no-cache-dir "./services/api[cloud]"
COPY --from=web /workspace/apps/web/dist apps/web/dist
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --app-dir services/api --host 0.0.0.0 --port ${PORT}"]
