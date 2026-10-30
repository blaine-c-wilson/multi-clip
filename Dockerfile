# Builds the multi-clip web app into a container image.
# The base image is pinned to a digest so every build starts from identical bytes;
# Dependabot opens PRs when a newer image is published.
FROM python:3.14-slim@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8

# Don't write .pyc files, flush logs immediately, and keep pip quiet and cache-free.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies before copying the code, so this slow layer is reused
# from cache whenever only the code changes.
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt

COPY app ./app

# Run as an unprivileged user rather than root.
RUN useradd --uid 10001 --no-create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
