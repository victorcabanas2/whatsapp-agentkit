# Dockerfile — Imagen Docker para AgentKit
# Generado por AgentKit

FROM python:3.14-slim

WORKDIR /app

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código
COPY . .

# Exponer puerto
EXPOSE 8000

# Variables por defecto
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Comando de inicio
CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
