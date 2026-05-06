FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

WORKDIR /app

# CJK fonts are needed by Pillow when rendering /api/og/* card images.
# fonts-noto-cjk is ~80MB; fonts-noto-cjk-extra would be 300MB+ (skipped).
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder (no build-essential in final image)
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd -r -s /usr/sbin/nologin app
USER app

COPY --chown=app:app . .

EXPOSE 8000

CMD ["sh", "entrypoint.sh"]
