# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente Belén de Rebody.
- Recibe webhooks de WhatsApp via Whapi.cloud
- Procesa mensajes con Claude AI
- Mantiene historial de conversaciones en SQLite
- Envía respuestas de vuelta a WhatsApp
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, registrar_lead
from agent.providers import obtener_proveedor
from agent.scheduler import inicializar_scheduler, detener_scheduler

# Cargar variables de entorno
load_dotenv()

# Configuración
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
PORT = int(os.getenv("PORT", 8000))
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO

# Setup de logging
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("agentkit")

# Obtener proveedor de WhatsApp
proveedor = obtener_proveedor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa recursos al arrancar el servidor."""
    logger.info("━" * 60)
    logger.info("🚀 Iniciando AgentKit — WhatsApp AI Agent")
    logger.info("━" * 60)

    # Inicializar base de datos
    await inicializar_db()
    logger.info("✓ Base de datos inicializada")

    # Inicializar scheduler de seguimientos
    inicializar_scheduler()
    logger.info("✓ Scheduler de seguimientos iniciado")

    logger.info(f"✓ Proveedor WhatsApp: {proveedor.__class__.__name__}")
    logger.info(f"✓ Modo: {ENVIRONMENT}")
    logger.info(f"✓ Puerto: {PORT}")
    logger.info("━" * 60)
    logger.info("✓ Servidor listo. Esperando mensajes...")
    logger.info("━" * 60)

    yield

    logger.info("🛑 Deteniendo scheduler...")
    detener_scheduler()
    logger.info("🛑 Servidor detenido")


# Crear aplicación FastAPI
app = FastAPI(
    title="AgentKit — Belén Rebody Bot",
    description="Agente de WhatsApp AI para Rebody",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    """Endpoint de salud para monitoreo."""
    return {
        "status": "ok",
        "service": "agentkit-belen",
        "proveedor": proveedor.__class__.__name__
    }


@app.get("/webhook")
async def webhook_get_verification(request: Request):
    """
    Verificación GET del webhook (requerido por Meta Cloud API).
    Para Whapi.cloud, simplemente retorna OK.
    """
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return JSONResponse({"status": "ok"})


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp desde el proveedor configurado.
    Procesa cada mensaje con Claude AI y envía respuesta.
    """
    try:
        # Parsear webhook — el proveedor normaliza el formato
        mensajes = await proveedor.parsear_webhook(request)

        if not mensajes:
            logger.debug("No hay mensajes en el webhook")
            return {"status": "ok"}

        # Procesar cada mensaje
        for msg in mensajes:
            # Ignorar mensajes propios
            if msg.es_propio:
                logger.debug(f"Ignorando mensaje propio de {msg.telefono}")
                continue

            # Validar contenido
            if not msg.texto or not msg.texto.strip():
                logger.debug(f"Mensaje vacío de {msg.telefono}")
                continue

            logger.info(f"📨 Mensaje recibido de {msg.telefono}")
            logger.debug(f"   Contenido: {msg.texto[:100]}...")

            try:
                # Registrar lead automáticamente (si no existe, lo crea; si existe, actualiza último mensaje)
                await registrar_lead(msg.telefono)

                # Obtener historial anterior (sin el mensaje actual)
                historial = await obtener_historial(msg.telefono)

                # Generar respuesta con Claude
                logger.debug("Llamando a Claude AI...")
                respuesta = await generar_respuesta(msg.texto, historial)

                # Guardar mensaje del usuario
                await guardar_mensaje(msg.telefono, "user", msg.texto)

                # Guardar respuesta del agente
                await guardar_mensaje(msg.telefono, "assistant", respuesta)

                # Enviar respuesta por WhatsApp
                exito = await proveedor.enviar_mensaje(msg.telefono, respuesta)

                if exito:
                    logger.info(f"✓ Respuesta enviada a {msg.telefono}")
                    logger.debug(f"   Respuesta: {respuesta[:100]}...")
                else:
                    logger.error(f"✗ Fallo al enviar respuesta a {msg.telefono}")

            except Exception as e:
                logger.error(f"✗ Error procesando mensaje de {msg.telefono}: {e}")
                # Intentar enviar mensaje de error
                try:
                    await proveedor.enviar_mensaje(
                        msg.telefono,
                        "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos."
                    )
                except Exception as send_error:
                    logger.error(f"✗ No se pudo enviar mensaje de error: {send_error}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"✗ Error crítico en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Endpoint de health para Railway/monitoreo."""
    return {"status": "healthy", "service": "agentkit"}
