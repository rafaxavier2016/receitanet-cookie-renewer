FROM python:3.11-slim

WORKDIR /app

# Dependencias do sistema necessarias pro Chromium do Playwright + curl pro healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates wget \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    libx11-6 libxcb1 libxext6 fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

# Instala Playwright + baixa Chromium
RUN pip install --no-cache-dir playwright==1.50.0 \
 && playwright install chromium

COPY renew.py /app/renew.py

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD curl -fs http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["python", "renew.py", "--serve"]
