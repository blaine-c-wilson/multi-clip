# Builds the multi-clip web app into a container image.
# Images are pinned to digests so every build starts from identical bytes;
# Dependabot opens PRs when newer images are published.

# AWS Lambda Web Adapter: lets this ordinary web server run on AWS Lambda.
FROM public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1 AS lambda-adapter

FROM python:3.14-slim@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8

# Don't write .pyc files, flush logs immediately, and keep pip quiet and cache-free.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies before copying the code, so this slow layer is reused
# from cache whenever only the code changes. pip is then removed: it's only
# needed at build time, and its bundled libraries add vulnerabilities.
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt \
 && pip uninstall --yes pip

COPY app ./app

# On Lambda, the adapter runs as an extension and forwards requests to the app
# on port 8000 once /health responds. Outside Lambda it's never started.
COPY --from=lambda-adapter /lambda-adapter /opt/extensions/lambda-adapter
ENV AWS_LWA_PORT=8000 \
    AWS_LWA_READINESS_CHECK_PATH=/health

# Run as an unprivileged user rather than root.
RUN useradd --uid 10001 --no-create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
