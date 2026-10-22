# One image for both the API and the grading worker (deploy/docker-compose.yml picks the command).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
# PyPI is slow from mainland servers; the Tencent Cloud mirror is reachable from Lighthouse.
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY migrations ./migrations
COPY data ./data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
