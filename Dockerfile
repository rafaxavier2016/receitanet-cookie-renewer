FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Sem dependencias externas alem do Playwright (que ja vem na imagem base)
# Copiamos so o script
COPY renew.py /app/renew.py

# Healthcheck simples
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD curl -fs http://localhost:8080/health || exit 1

EXPOSE 8080

# Default: rodar como HTTP server. Pra rodar 1-shot, override CMD com: python renew.py
CMD ["python", "renew.py", "--serve"]
