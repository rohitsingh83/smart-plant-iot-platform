# Multi-stage production Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Runtime Image
FROM python:3.11-slim AS runner

WORKDIR /app

# Create unprivileged user for security
RUN groupadd -r plantcare && useradd -r -g plantcare -d /app plantcare

COPY --from=builder /root/.local /home/plantcare/.local
ENV PATH=/home/plantcare/.local/bin:$PATH

COPY --chown=plantcare:plantcare . /app

USER plantcare

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
