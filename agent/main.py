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
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException, Cookie
from fastapi.responses import PlainTextResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from sqlalchemy import select, desc, func

from agent.brain import generar_respuesta, detectar_confirmacion_pago
from agent.memory import (
    inicializar_db,
    guardar_mensaje,
    obtener_historial,
    registrar_lead,
    guardar_pedido,
    obtener_ultimo_pedido,
    actualizar_estado_pedido,
    async_session,
    Lead,
    Pedido,
    Mensaje,
)
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

# URL de imagen de datos bancarios para TRANSFERENCIA
IMAGEN_DATOS_BANCARIOS = "https://i.imgur.com/WYPWrdl.png"


def detectar_opcion_pago(respuesta_agente: str) -> str | None:
    """
    Detecta qué método de pago mencionó el agente en la respuesta.

    Returns:
        "transferencia", "pagopar", "qr", "efectivo", o None
    """
    respuesta_lower = respuesta_agente.lower()

    if "transferencia" in respuesta_lower and "ueno" in respuesta_lower:
        return "transferencia"
    elif "pagopar" in respuesta_lower:
        return "pagopar"
    elif "itaú" in respuesta_lower or "qr" in respuesta_lower:
        return "qr"
    elif "efectivo" in respuesta_lower:
        return "efectivo"

    return None


async def enviar_imagen(telefono: str, url_imagen: str) -> bool:
    """
    Envía una imagen al cliente vía WhatsApp usando el proveedor configurado.

    Args:
        telefono: Número del cliente
        url_imagen: URL de la imagen a enviar

    Returns:
        True si se envió exitosamente, False en caso contrario
    """
    try:
        # Usar el método del proveedor si está disponible
        if hasattr(proveedor, 'enviar_imagen'):
            logger.info(f"📸 Enviando imagen a {telefono}")
            return await proveedor.enviar_imagen(telefono, url_imagen)
        else:
            # Si el proveedor no soporta imágenes, log pero no error
            logger.warning(f"⚠️ Proveedor {proveedor.__class__.__name__} no soporta envío de imágenes")
            return False
    except Exception as e:
        logger.error(f"❌ Error enviando imagen a {telefono}: {e}")
        return False


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

# Servir archivos estáticos (admin dashboard)
import os as os_module
if os_module.path.exists("public"):
    app.mount("/static", StaticFiles(directory="public"), name="static")


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
        # Log del payload completo para debugging
        body = await request.json()
        logger.info(f"📨 WEBHOOK PAYLOAD COMPLETO: {body}")

        # Crear un wrapper para pasar el body al proveedor
        class DebugRequest:
            async def json(self):
                return body

        debug_request = DebugRequest()

        # Parsear webhook — el proveedor normaliza el formato
        mensajes = await proveedor.parsear_webhook(debug_request)

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

                # Si el mensaje viene de un anuncio (button/interactive/referral),
                # agregar contexto al inicio del mensaje para que Claude sepa el producto
                mensaje_contextualizado = msg.texto

                # Detectar si es un click desde anuncio y extraer payload
                if msg.payload:
                    # El payload contiene info del anuncio (ej: "depuffing_wand", "theragun_mini", etc)
                    logger.info(f"📢 Mensaje desde anuncio con payload: {msg.payload}")
                    # Prepender el payload al mensaje para que Claude lo entienda
                    mensaje_contextualizado = f"[Vino desde anuncio de: {msg.payload}] {msg.texto}"

                # Generar respuesta con Claude
                logger.debug("Llamando a Claude AI...")
                respuesta = await generar_respuesta(mensaje_contextualizado, historial)

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

                # ═══════════════════════════════════════════════════════════
                # LÓGICA DE PAGOS - Detectar métodos de pago
                # ═══════════════════════════════════════════════════════════

                metodo_pago = detectar_opcion_pago(respuesta)

                if metodo_pago == "transferencia":
                    # Enviar imagen de datos bancarios
                    logger.info(f"💳 Cliente {msg.telefono} eligió TRANSFERENCIA - enviando datos bancarios")
                    await enviar_imagen(msg.telefono, IMAGEN_DATOS_BANCARIOS)

                # ═══════════════════════════════════════════════════════════
                # LÓGICA DE CONFIRMACIÓN - Detectar confirmación de pago
                # ═══════════════════════════════════════════════════════════

                if detectar_confirmacion_pago(msg.texto):
                    logger.info(f"✅ Cliente {msg.telefono} confirmó pago - intentando guardar pedido")

                    # Obtener el último pedido en progreso
                    ultimo_pedido = await obtener_ultimo_pedido(msg.telefono)

                    if ultimo_pedido and ultimo_pedido.estado == "pendiente":
                        # Actualizar estado a pagado
                        await actualizar_estado_pedido(ultimo_pedido.id, "pagado")
                        logger.info(f"💰 Pedido #{ultimo_pedido.id} marcado como PAGADO")
                    else:
                        logger.warning(f"⚠️ No hay pedido pendiente para {msg.telefono} - confirmación sin pedido en BD")

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


# ═══════════════════════════════════════════════════════════
# ENDPOINTS DE PEDIDOS (ADMIN/DEBUG)
# ═══════════════════════════════════════════════════════════

@app.post("/pedidos")
async def crear_pedido(request: Request):
    """
    Endpoint para crear un pedido manualmente.
    Usado para guardar pedidos cuando se completa el flujo de compra.

    JSON esperado:
    {
        "telefono": "595...",
        "producto": "Theragun PRO PLUS",
        "precio": "5,799,000",
        "metodo_pago": "transferencia",
        "nombre_cliente": "Juan Pérez",
        "direccion_envio": "Av. Mariscal Lopez 123",
        "ciudad_departamento": "Asunción",
        "telefono_contacto": "595991234567",
        "ruc_cedula": "1234567",
        "razon_social": "Particular"
    }
    """
    try:
        data = await request.json()

        pedido = await guardar_pedido(
            telefono=data.get("telefono"),
            producto=data.get("producto"),
            precio=data.get("precio"),
            metodo_pago=data.get("metodo_pago"),
            nombre_cliente=data.get("nombre_cliente", ""),
            direccion_envio=data.get("direccion_envio", ""),
            ciudad_departamento=data.get("ciudad_departamento", ""),
            telefono_contacto=data.get("telefono_contacto", ""),
            ruc_cedula=data.get("ruc_cedula", ""),
            razon_social=data.get("razon_social", ""),
        )

        logger.info(f"💾 Pedido guardado: {pedido}")

        return {
            "status": "ok",
            "pedido_id": pedido.id,
            "mensaje": f"Pedido #{pedido.id} guardado correctamente"
        }

    except Exception as e:
        logger.error(f"Error creando pedido: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/pedidos/{telefono}")
async def obtener_pedidos(telefono: str):
    """
    Obtiene todos los pedidos de un cliente.

    Args:
        telefono: Número de teléfono del cliente
    """
    try:
        pedidos = await obtener_ultimo_pedido(telefono)

        if not pedidos:
            return {"status": "ok", "pedidos": [], "total": 0}

        return {
            "status": "ok",
            "telefono": telefono,
            "pedidos": [
                {
                    "id": p.id,
                    "producto": p.producto,
                    "precio": p.precio,
                    "metodo_pago": p.metodo_pago,
                    "estado": p.estado,
                    "fecha_pedido": str(p.fecha_pedido),
                }
                for p in ([pedidos] if pedidos else [])
            ],
            "total": 1 if pedidos else 0
        }

    except Exception as e:
        logger.error(f"Error obteniendo pedidos: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════
# ENDPOINTS DE DEBUG SHOPIFY
# ═══════════════════════════════════════════════════════════

@app.get("/debug/shopify")
async def debug_shopify():
    """
    Endpoint de debug para verificar conexión con Shopify.
    Intenta obtener stock de los primeros productos.
    """
    from agent.shopify import (
        obtener_credenciales_shopify,
        cargar_config_shopify,
        obtener_stock_producto,
    )

    try:
        credenciales = obtener_credenciales_shopify()
        config = cargar_config_shopify()

        if not credenciales:
            return {
                "status": "error",
                "mensaje": "Credenciales Shopify no configuradas",
            }

        shop_name, token = credenciales

        return {
            "status": "ok",
            "shop": shop_name,
            "token_configured": "Sí" if token else "No",
            "products_mapped": len(config.get("products", {})),
            "mensaje": "Credenciales OK. Intenta /debug/shopify/test-producto para verificar un ID específico",
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/debug/shopify/test/{product_id}")
async def debug_shopify_test(product_id: str):
    """
    Testa obtener stock de un producto específico.
    Ej: /debug/shopify/test/9157820449026
    """
    from agent.shopify import obtener_stock_producto

    try:
        stock = await obtener_stock_producto(product_id)
        return {
            "status": "ok",
            "product_id": product_id,
            "stock": stock,
        }
    except Exception as e:
        return {"status": "error", "product_id": product_id, "error": str(e)}


# ═══════════════════════════════════════════════════════════
# ADMIN DASHBOARD ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/admin")
async def admin_dashboard():
    """Retorna dashboard HTML."""
    return FileResponse("public/admin.html")


@app.get("/api/admin/stats")
async def admin_stats():
    """Estadísticas generales."""
    from agent.admin_api import obtener_stats
    return await obtener_stats()


@app.get("/api/admin/leads")
async def admin_leads(estado: str = "todos"):
    """Leads filtrados."""
    from agent.admin_api import obtener_leads
    return await obtener_leads(estado)


@app.get("/api/admin/pedidos")
async def admin_pedidos(estado: str = "todos"):
    """Pedidos filtrados."""
    from agent.admin_api import obtener_pedidos
    return await obtener_pedidos(estado)
