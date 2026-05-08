# Dockerfile — Imagen Docker para AgentKit
# Generado por AgentKit

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

RUN chmod +x /app/docker-entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["/app/docker-entrypoint.sh"]
