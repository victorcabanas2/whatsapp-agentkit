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

# Run as non-root user (CN-010)
RUN useradd --system --no-create-home --uid 1001 appuser && \
    chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
