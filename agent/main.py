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
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
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
    actualizar_lead_scoring,
    obtener_lead,
    marcar_alerta_vendedor,
    obtener_resumen_cliente,
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

# Número del vendedor para alertas (desde .env)
VENDEDOR_WHATSAPP = os.getenv("VENDEDOR_WHATSAPP", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


# ════════════════════════════════════════════════════════════
# LEAD SCORING — Detección de intención y urgencia
# ════════════════════════════════════════════════════════════

KEYWORDS_HOT = [
    "compro", "me llevo", "quiero comprarlo", "cómo pago",
    "dale", "cómo hago la transferencia", "cuándo llega", "listo",
    "ya me decide", "adelante con eso", "va", "que sea"
]

KEYWORDS_WARM = [
    "precio", "cuánto", "cuánto cuesta", "cuánto vale", "qué incluye",
    "garantía", "envío", "disponible", "stock", "características",
    "diferencia entre", "cuál es mejor"
]

KEYWORDS_URGENCY = [
    "urgente", "hoy", "ya", "lo necesito ahora", "para mañana",
    "esta semana", "rápido", "apurado", "ASAP"
]

KEYWORDS_OBJECTION = [
    "muy caro", "caro", "lo pienso", "después", "no me interesa",
    "voy a pensar", "es mucho", "es bastante", "otro momento",
    "no tengo presupuesto", "está caro"
]


async def calcular_lead_score(telefono: str, mensaje_usuario: str, lead: Lead | None = None):
    """
    Calcula el score del lead basado en palabras clave.
    Actualiza en la BD: score, intencion, urgencia, objeciones.

    Scoring:
    - Base: 20 puntos
    - +30 si algún keyword HOT → intencion = "hot"
    - +15 si algún keyword WARM → intencion = "warm"
    - +20 si urgency keyword → urgencia = "alta"
    - +5 por cada mensaje del cliente → engagement
    - -10 si keyword de objeción → guardar en objeciones
    """
    if not lead:
        lead = await obtener_lead(telefono)
    if not lead:
        return

    mensaje_lower = mensaje_usuario.lower()

    # Lógica de scoring
    nuevo_score = 20  # Base
    nueva_intencion = "cold"
    nueva_urgencia = "baja"
    nuevas_objeciones = lead.objeciones or ""

    # Detectar keywords HOT
    if any(keyword in mensaje_lower for keyword in KEYWORDS_HOT):
        nuevo_score += 30
        nueva_intencion = "hot"
    # Si no es hot, detectar WARM
    elif any(keyword in mensaje_lower for keyword in KEYWORDS_WARM):
        nuevo_score += 15
        nueva_intencion = "warm"

    # Detectar urgencia
    if any(keyword in mensaje_lower for keyword in KEYWORDS_URGENCY):
        nuevo_score += 20
        nueva_urgencia = "alta"
    elif nueva_intencion == "warm":
        nueva_urgencia = "media"

    # Detectar objeciones
    for objecion in KEYWORDS_OBJECTION:
        if objecion in mensaje_lower:
            nuevo_score -= 10
            if objecion not in nuevas_objeciones:
                nuevas_objeciones += f", {objecion}" if nuevas_objeciones else objecion
            break

    # Actualizar en BD
    await actualizar_lead_scoring(
        telefono,
        score=nuevo_score,
        intencion=nueva_intencion,
        urgencia=nueva_urgencia,
        objeciones=nuevas_objeciones if nuevas_objeciones else None
    )

    logger.debug(f"📊 Score {telefono}: {nuevo_score} ({nueva_intencion}), urgencia: {nueva_urgencia}")


async def enviar_alerta_vendedor(tipo: str, telefono: str, detalle: str = ""):
    """
    Envía alerta al vendedor vía WhatsApp.

    Tipos: "nuevo_lead", "hot_lead", "pago_confirmado", "sin_respuesta"
    """
    if not VENDEDOR_WHATSAPP:
        logger.warning("⚠️ VENDEDOR_WHATSAPP no configurado - alertas deshabilitadas")
        return

    try:
        mensajes_alerta = {
            "nuevo_lead": f"🆕 Nuevo lead: {detalle}",
            "hot_lead": f"🔥 LEAD CALIENTE:\n{detalle}",
            "pago_confirmado": f"✅ PAGO CONFIRMADO:\n{detalle}",
            "sin_respuesta": f"⚠️ Sin respuesta (>4h):\n{detalle}"
        }

        mensaje = mensajes_alerta.get(tipo, detalle)

        logger.info(f"📢 Enviando alerta al vendedor: {tipo}")
        exito = await proveedor.enviar_mensaje(VENDEDOR_WHATSAPP, mensaje)

        if exito:
            logger.info(f"✓ Alerta enviada al vendedor")
        else:
            logger.error(f"✗ Fallo al enviar alerta al vendedor")

    except Exception as e:
        logger.error(f"❌ Error enviando alerta: {e}")


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
                lead = await registrar_lead(msg.telefono)

                # DETECTAR NUEVO LEAD (primera vez que contacta)
                es_nuevo_lead = (datetime.utcnow() - lead.primer_contacto).total_seconds() < 60  # Hace menos de 1 min

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

                # ═══════════════════════════════════════════════════════════
                # LEAD SCORING — Clasificar cliente por potencial
                # ═══════════════════════════════════════════════════════════

                score_anterior = lead.score
                intencion_anterior = lead.intencion

                await calcular_lead_score(msg.telefono, msg.texto, lead)

                # Recargar lead para obtener nuevos valores
                lead = await obtener_lead(msg.telefono)

                # ═══════════════════════════════════════════════════════════
                # ALERTAS AL VENDEDOR
                # ═══════════════════════════════════════════════════════════

                # ALERT 1: Nuevo lead
                if es_nuevo_lead and not lead.alerta_vendedor_enviada:
                    nombre = lead.nombre or msg.telefono
                    await enviar_alerta_vendedor(
                        "nuevo_lead",
                        msg.telefono,
                        f"{nombre} ({msg.telefono})\nDice: '{msg.texto[:80]}...'"
                    )
                    await marcar_alerta_vendedor(msg.telefono)

                # ALERT 2: Lead pasó de warm/cold a hot
                if (score_anterior < 50 or intencion_anterior != "hot") and lead.intencion == "hot":
                    nombre = lead.nombre or msg.telefono
                    await enviar_alerta_vendedor(
                        "hot_lead",
                        msg.telefono,
                        f"{nombre} ({msg.telefono})\nScore: {lead.score}/100\nDice: '{msg.texto[:80]}...'"
                    )

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

                        # ALERT 3: Pago confirmado
                        nombre = lead.nombre or msg.telefono
                        await enviar_alerta_vendedor(
                            "pago_confirmado",
                            msg.telefono,
                            f"{nombre} ({msg.telefono})\nProducto: {ultimo_pedido.producto}\nPrecio: {ultimo_pedido.precio} Gs"
                        )

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

def get_login_html():
    """Página de login para el dashboard."""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Acceso Admin - Belén</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-container { background: #1e293b; border-radius: 8px; padding: 40px; max-width: 400px; width: 100%; }
        .login-container h1 { text-align: center; margin-bottom: 30px; font-size: 24px; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; color: #94a3b8; font-weight: 500; }
        .form-group input { width: 100%; padding: 10px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; border-radius: 4px; font-size: 14px; }
        .form-group input:focus { outline: none; border-color: #3b82f6; }
        .btn { width: 100%; padding: 12px; background: #3b82f6; color: white; border: none; border-radius: 4px; font-weight: 600; cursor: pointer; font-size: 14px; }
        .btn:hover { background: #2563eb; }
        .error { color: #ef4444; font-size: 12px; text-align: center; }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>🔒 Acceso Admin</h1>
        <form onsubmit="login(event)">
            <div class="form-group">
                <label>Contraseña</label>
                <input type="password" id="pwd" placeholder="Ingresa la contraseña" required>
            </div>
            <button type="submit" class="btn">Acceder</button>
        </form>
    </div>
    <script>
        function login(e) {
            e.preventDefault();
            const pwd = document.getElementById('pwd').value;
            window.location.href = '/admin?pwd=' + encodeURIComponent(pwd);
        }
    </script>
</body>
</html>"""


def get_dashboard_html():
    """Página del dashboard completo con leads, pedidos, campañas y control de bot."""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel Admin Completo - Belén</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        h1 { margin: 20px 0; font-size: 28px; }
        h2 { margin: 30px 0 15px 0; font-size: 18px; border-bottom: 1px solid #334155; padding-bottom: 10px; }
        h3 { margin: 15px 0 10px 0; font-size: 14px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #1e293b; border-radius: 8px; padding: 16px; border-left: 4px solid #10b981; }
        .stat-card.hot { border-left-color: #ef4444; }
        .stat-card.pending { border-left-color: #f59e0b; }
        .stat-number { font-size: 28px; font-weight: bold; color: #10b981; }
        .stat-card.hot .stat-number { color: #ef4444; }
        .stat-card.pending .stat-number { color: #f59e0b; }
        .stat-label { color: #94a3b8; font-size: 12px; margin-top: 4px; }
        table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; margin: 20px 0; }
        th { background: #0f172a; padding: 10px; text-align: left; font-weight: 600; font-size: 12px; border-bottom: 1px solid #334155; }
        td { padding: 10px; border-bottom: 1px solid #334155; font-size: 13px; }
        tr:hover { background: #334155; }
        a { color: #3b82f6; text-decoration: none; cursor: pointer; }
        a:hover { text-decoration: underline; }
        .badge { display: inline-block; padding: 3px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; }
        .badge-hot { background: #ef4444; color: white; }
        .badge-warm { background: #f59e0b; color: black; }
        .badge-cold { background: #6b7280; color: white; }
        .badge-success { background: #10b981; color: black; }
        .badge-danger { background: #ef4444; color: white; }
        .badge-pending { background: #f59e0b; color: black; }
        .badge-bot { background: #3b82f6; color: white; }
        .badge-human { background: #8b5cf6; color: white; }
        .loading { text-align: center; padding: 40px; }

        /* Tabs */
        .tabs { display: flex; gap: 10px; margin: 20px 0; border-bottom: 2px solid #334155; }
        .tab-btn { padding: 10px 20px; background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 14px; border-bottom: 2px solid transparent; }
        .tab-btn.active { color: #3b82f6; border-bottom-color: #3b82f6; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        /* Forms */
        .form-group { margin: 15px 0; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: 600; }
        .form-group input, .form-group textarea { width: 100%; padding: 8px; background: #1e293b; border: 1px solid #334155; color: #e2e8f0; border-radius: 4px; font-family: inherit; }
        .form-group button { padding: 10px 20px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; }
        .form-group button:hover { background: #2563eb; }
        .form-group button.danger { background: #ef4444; }
        .form-group button.danger:hover { background: #dc2626; }

        /* Pagination */
        .pagination { display: flex; gap: 5px; margin: 20px 0; }
        .pagination a, .pagination span { padding: 5px 10px; background: #1e293b; border: 1px solid #334155; border-radius: 4px; cursor: pointer; }
        .pagination a.active { background: #3b82f6; color: white; }

        /* Search */
        .search-box { margin: 15px 0; }
        .search-box input { padding: 10px; background: #1e293b; border: 1px solid #334155; color: #e2e8f0; border-radius: 4px; width: 300px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Panel Admin Completo - Belén</h1>
            <div style="font-size: 12px; color: #94a3b8;">Auto-refresh cada 30s</div>
        </div>

        <!-- ESTADÍSTICAS -->
        <div class="stats" id="stats">
            <div style="grid-column: 1/-1; text-align: center;">Cargando...</div>
        </div>

        <!-- TABS -->
        <div class="tabs">
            <button class="tab-btn active" onclick="mostrarTab('leads')">👥 Leads</button>
            <button class="tab-btn" onclick="mostrarTab('campanas')">📢 Campañas</button>
            <button class="tab-btn" onclick="mostrarTab('control')">🎮 Control Bot</button>
            <button class="tab-btn" onclick="mostrarTab('importados')">📥 Clientes Importados</button>
        </div>

        <!-- TAB 1: LEADS -->
        <div id="tab-leads" class="tab-content active">
            <h2>🔥 Leads HOT (Score alto)</h2>
            <table id="hot-leads-table">
                <thead><tr>
                    <th>Teléfono</th><th>Nombre</th><th>Producto</th><th>Score</th><th>Intención</th><th>Último Msg</th><th>Acciones</th>
                </tr></thead>
                <tbody><tr><td colspan="7" class="loading">Cargando...</td></tr></tbody>
            </table>

            <h2>👥 Todos los Leads</h2>
            <table id="leads-table">
                <thead><tr>
                    <th>Teléfono</th><th>Nombre</th><th>Producto</th><th>Score</th><th>Intención</th><th>Último Msg</th><th>Estado</th>
                </tr></thead>
                <tbody><tr><td colspan="7" class="loading">Cargando...</td></tr></tbody>
            </table>

            <h2>⏳ Sin Respuesta (>2h)</h2>
            <table id="sin-respuesta-table">
                <thead><tr>
                    <th>Teléfono</th><th>Nombre</th><th>Desde hace</th><th>Score</th><th>Último Msg</th><th>Acción</th>
                </tr></thead>
                <tbody><tr><td colspan="6" class="loading">Cargando...</td></tr></tbody>
            </table>

            <h2>📦 Pedidos Recientes</h2>
            <table id="pedidos-table">
                <thead><tr>
                    <th>Teléfono</th><th>Producto</th><th>Precio</th><th>Método</th><th>Estado</th><th>Fecha</th>
                </tr></thead>
                <tbody><tr><td colspan="6" class="loading">Cargando...</td></tr></tbody>
            </table>
        </div>

        <!-- TAB 2: CAMPAÑAS & BROADCASTS -->
        <div id="tab-campanas" class="tab-content">
            <h2>📢 Envío Masivo de Mensajes</h2>

            <div style="background: #1e293b; padding: 20px; border-radius: 8px;">
                <h3>Enviar Texto Masivo</h3>
                <div class="form-group">
                    <label>Mensaje de texto:</label>
                    <textarea id="broadcast-texto" placeholder="Escribe el mensaje que quieres enviar a todos los clientes..." style="height: 100px;"></textarea>
                </div>
                <button onclick="enviarBroadcast()" style="background: #10b981;">📤 Enviar a Todos</button>
                <button onclick="limpiarBroadcast()">🗑️ Limpiar</button>
                <div id="broadcast-resultado" style="margin-top: 10px; color: #10b981;"></div>
            </div>

            <div style="background: #1e293b; padding: 20px; border-radius: 8px; margin-top: 20px;">
                <h3>Enviar Imagen a Cliente Individual</h3>
                <div class="form-group">
                    <label>Teléfono del cliente:</label>
                    <input type="text" id="imagen-telefono" placeholder="595991234567">
                </div>
                <div class="form-group">
                    <label>URL de la imagen:</label>
                    <input type="text" id="imagen-url" placeholder="https://ejemplo.com/imagen.jpg">
                </div>
                <div class="form-group">
                    <label>Texto (opcional):</label>
                    <input type="text" id="imagen-caption" placeholder="Escribe un texto para acompañar la imagen">
                </div>
                <button onclick="enviarImagen()" style="background: #f59e0b;">🖼️ Enviar Imagen</button>
                <div id="imagen-resultado" style="margin-top: 10px;"></div>
            </div>
        </div>

        <!-- TAB 3: CONTROL DEL BOT -->
        <div id="tab-control" class="tab-content">
            <h2>🎮 Control de Conversación</h2>
            <div style="background: #1e293b; padding: 20px; border-radius: 8px;">
                <h3>Tomar o Liberar Control</h3>
                <p style="margin-bottom: 15px; color: #94a3b8;">Usa estos botones para pausar el bot y tomar control de la conversación manualmente, o para reactivar el bot.</p>

                <div class="form-group">
                    <label>Teléfono del cliente:</label>
                    <input type="text" id="control-telefono" placeholder="595991234567">
                </div>

                <button onclick="tomarControl()" style="background: #ef4444; margin-right: 10px;">⏸️ Tomar Control (Pausa Bot)</button>
                <button onclick="liberarControl()" style="background: #10b981;">▶️ Liberar Control (Reactiva Bot)</button>

                <div id="control-resultado" style="margin-top: 10px;"></div>
            </div>
        </div>

        <!-- TAB 4: CLIENTES IMPORTADOS -->
        <div id="tab-importados" class="tab-content">
            <h2>📥 Clientes Importados del Excel</h2>

            <div style="background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <button onclick="importarExcel()" style="background: #10b981; margin-right: 10px;">📥 Importar desde Excel</button>
                <div id="import-resultado" style="margin-top: 10px;"></div>
            </div>

            <div class="search-box">
                <input type="text" id="clientes-busqueda" placeholder="Buscar por nombre o teléfono..." onkeyup="buscarClientesImportados()">
            </div>

            <table id="clientes-importados-table">
                <thead><tr>
                    <th>Teléfono</th><th>Nombre</th><th>Productos Comprados</th><th>Historial</th><th>Acción</th>
                </tr></thead>
                <tbody><tr><td colspan="5" class="loading">Cargando...</td></tr></tbody>
            </table>

            <div id="paginacion-importados" class="pagination"></div>
        </div>
    </div>

    <script>
        let paginaActual = 1;

        function mostrarTab(tab) {
            // Ocultar todos los tabs
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

            // Mostrar el tab seleccionado
            document.getElementById('tab-' + tab).classList.add('active');
            event.target.classList.add('active');

            // Cargar datos del tab específico
            if (tab === 'importados') {
                cargarClientesImportados(1);
            }
        }

        function getBadgeIntention(intencion) {
            const badges = {
                'hot': '<span class="badge badge-hot">🔥 Hot</span>',
                'warm': '<span class="badge badge-warm">⚡ Warm</span>',
                'cold': '<span class="badge badge-cold">❄️ Cold</span>'
            };
            return badges[intencion] || intencion;
        }

        function copyPhone(tel) {
            navigator.clipboard.writeText(tel);
            alert('Copiado: ' + tel);
        }

        async function cargarDatos() {
            try {
                // Stats
                const statsRes = await fetch('/api/admin/stats');
                const stats = await statsRes.json();

                document.getElementById('stats').innerHTML =
                    '<div class="stat-card"><div class="stat-number">' + stats.total_leads + '</div><div class="stat-label">Total Leads</div></div>' +
                    '<div class="stat-card"><div class="stat-number">' + stats.leads_hoy + '</div><div class="stat-label">Leads Hoy</div></div>' +
                    '<div class="stat-card hot"><div class="stat-number">' + stats.hot_leads + '</div><div class="stat-label">🔥 Hot Leads</div></div>' +
                    '<div class="stat-card"><div class="stat-number">' + stats.conversion_pct + '%</div><div class="stat-label">Conversión</div></div>' +
                    '<div class="stat-card pending"><div class="stat-number">' + stats.pedidos_pendientes + '</div><div class="stat-label">Pedidos Pendientes</div></div>' +
                    '<div class="stat-card"><div class="stat-number">' + stats.sin_respuesta_2h + '</div><div class="stat-label">Sin Respuesta >2h</div></div>';

                // Hot leads
                const hotRes = await fetch('/api/admin/leads?estado=hot&limite=5');
                const hotLeads = await hotRes.json();
                document.querySelector('#hot-leads-table tbody').innerHTML = hotLeads.length > 0 ?
                    hotLeads.map(l => '<tr><td><a onclick="copyPhone(' + JSON.stringify(l.telefono) + ')" title="Copiar">' + l.telefono + '</a></td><td>' + l.nombre + '</td><td>' + l.producto_preferido + '</td><td>' + l.score + '</td><td>' + getBadgeIntention(l.intencion) + '</td><td>' + new Date(l.ultimo_mensaje).toLocaleTimeString('es-PY') + '</td><td><a href="https://wa.me/' + l.telefono + '" target="_blank">📱</a></td></tr>').join('') : '<tr><td colspan="7">Sin leads hot</td></tr>';

                // All leads
                const leadsRes = await fetch('/api/admin/leads');
                const leads = await leadsRes.json();
                document.querySelector('#leads-table tbody').innerHTML = leads.length > 0 ?
                    leads.map(l => '<tr><td><a onclick="copyPhone(' + JSON.stringify(l.telefono) + ')">' + l.telefono + '</a></td><td>' + l.nombre + '</td><td>' + l.producto_preferido + '</td><td>' + l.score + '</td><td>' + getBadgeIntention(l.intencion) + '</td><td>' + new Date(l.ultimo_mensaje).toLocaleTimeString('es-PY') + '</td><td>' + (l.fue_cliente ? '<span class="badge badge-success">✓ Cliente</span>' : '<span class="badge badge-pending">Lead</span>') + '</td></tr>').join('') : '<tr><td colspan="7">Sin leads</td></tr>';

                // Sin respuesta
                const sinRespRes = await fetch('/api/admin/sin-respuesta?horas=2');
                const sinResp = await sinRespRes.json();
                document.querySelector('#sin-respuesta-table tbody').innerHTML = sinResp.length > 0 ?
                    sinResp.map(l => '<tr><td><a onclick="copyPhone(' + JSON.stringify(l.telefono) + ')">' + l.telefono + '</a></td><td>' + l.nombre + '</td><td>' + l.horas_sin_respuesta + 'h</td><td>' + l.score + '</td><td>' + l.ultimo_mensaje + '</td><td><a href="https://wa.me/' + l.telefono + '" target="_blank">📱 Escribir</a></td></tr>').join('') : '<tr><td colspan="6">Todos respondidos</td></tr>';

                // Pedidos
                const pedidosRes = await fetch('/api/admin/pedidos');
                const pedidos = await pedidosRes.json();
                document.querySelector('#pedidos-table tbody').innerHTML = pedidos.length > 0 ?
                    pedidos.map(p => '<tr><td><a onclick="copyPhone(' + JSON.stringify(p.telefono) + ')">' + p.telefono + '</a></td><td>' + p.producto + '</td><td>' + p.precio + '</td><td>' + p.metodo_pago + '</td><td>' + (p.estado === 'pagado' ? '<span class="badge badge-success">✓ Pagado</span>' : '<span class="badge badge-danger">⏳ Pendiente</span>') + '</td><td>' + new Date(p.fecha_pedido).toLocaleString('es-PY') + '</td></tr>').join('') : '<tr><td colspan="6">Sin pedidos</td></tr>';

            } catch (e) {
                console.error('Error:', e);
            }
        }

        // FUNCIONES DE CAMPAÑAS
        async function enviarBroadcast() {
            const texto = document.getElementById('broadcast-texto').value;
            if (!texto) {
                alert('Escribe un mensaje');
                return;
            }

            document.getElementById('broadcast-resultado').innerText = 'Enviando...';
            const res = await fetch('/api/admin/enviar-masivo?mensaje=' + encodeURIComponent(texto), {method: 'POST'});
            const data = await res.json();
            document.getElementById('broadcast-resultado').innerText = '✓ Enviados: ' + data.exitosos + ' | ✗ Fallidos: ' + data.fallidos;
        }

        function limpiarBroadcast() {
            document.getElementById('broadcast-texto').value = '';
            document.getElementById('broadcast-resultado').innerText = '';
        }

        async function enviarImagen() {
            const tel = document.getElementById('imagen-telefono').value;
            const url = document.getElementById('imagen-url').value;
            const caption = document.getElementById('imagen-caption').value;

            if (!tel || !url) {
                alert('Teléfono e imagen son requeridos');
                return;
            }

            document.getElementById('imagen-resultado').innerText = 'Enviando...';
            const res = await fetch('/api/admin/enviar-imagen?telefono=' + tel + '&imagen_url=' + encodeURIComponent(url) + '&caption=' + encodeURIComponent(caption), {method: 'POST'});
            const data = await res.json();
            document.getElementById('imagen-resultado').innerText = data.exito ? '✓ ' + data.mensaje : '✗ ' + data.mensaje;
        }

        // FUNCIONES DE CONTROL
        async function tomarControl() {
            const tel = document.getElementById('control-telefono').value;
            if (!tel) {
                alert('Escribe un teléfono');
                return;
            }

            const res = await fetch('/api/admin/tomar-control?telefono=' + tel, {method: 'POST'});
            const data = await res.json();
            document.getElementById('control-resultado').innerText = data.exito ? '✓ ' + data.mensaje : '✗ ' + data.mensaje;
        }

        async function liberarControl() {
            const tel = document.getElementById('control-telefono').value;
            if (!tel) {
                alert('Escribe un teléfono');
                return;
            }

            const res = await fetch('/api/admin/liberar-control?telefono=' + tel, {method: 'POST'});
            const data = await res.json();
            document.getElementById('control-resultado').innerText = data.exito ? '✓ ' + data.mensaje : '✗ ' + data.mensaje;
        }

        // FUNCIONES DE CLIENTES IMPORTADOS
        async function cargarClientesImportados(pagina) {
            paginaActual = pagina;
            const res = await fetch('/api/admin/clientes-importados?pagina=' + pagina + '&por_pagina=20');
            const data = await res.json();

            const tbody = document.querySelector('#clientes-importados-table tbody');
            tbody.innerHTML = data.clientes && data.clientes.length > 0 ?
                data.clientes.map(c => '<tr><td><a onclick="copyPhone(' + JSON.stringify(c.telefono) + ')" title="Copiar">' + c.telefono + '</a></td><td>' + c.nombre + '</td><td>' + c.productos_comprados + '</td><td>' + c.historial + '</td><td><a href="https://wa.me/' + c.telefono + '" target="_blank">📱</a></td></tr>').join('') : '<tr><td colspan="5">Sin clientes importados</td></tr>';

            // Paginación
            let html = '';
            for (let i = 1; i <= data.total_paginas; i++) {
                if (i === pagina) {
                    html += '<span class="active">' + i + '</span>';
                } else {
                    html += '<a onclick="cargarClientesImportados(' + i + ')">' + i + '</a>';
                }
            }
            document.getElementById('paginacion-importados').innerHTML = html;
        }

        async function buscarClientesImportados() {
            const q = document.getElementById('clientes-busqueda').value;
            if (!q) {
                cargarClientesImportados(1);
                return;
            }

            const res = await fetch('/api/admin/clientes-importados?q=' + encodeURIComponent(q));
            const data = await res.json();

            const tbody = document.querySelector('#clientes-importados-table tbody');
            tbody.innerHTML = data.clientes && data.clientes.length > 0 ?
                data.clientes.map(c => '<tr><td><a onclick="copyPhone(' + JSON.stringify(c.telefono) + ')">' + c.telefono + '</a></td><td>' + c.nombre + '</td><td>' + c.productos_comprados + '</td><td>' + c.historial + '</td><td><a href="https://wa.me/' + c.telefono + '" target="_blank">📱</a></td></tr>').join('') : '<tr><td colspan="5">No encontrado</td></tr>';

            document.getElementById('paginacion-importados').innerHTML = '';
        }

        async function importarExcel() {
            if (!confirm('¿Importar clientes desde el archivo Excel?')) return;

            document.getElementById('import-resultado').innerText = 'Importando...';
            const res = await fetch('/api/admin/importar-excel', {method: 'POST'});
            const data = await res.json();

            if (data.error) {
                document.getElementById('import-resultado').innerText = '✗ Error: ' + data.error;
            } else {
                document.getElementById('import-resultado').innerText = '✓ Importados: ' + data.exitosos + ' | Duplicados: ' + data.duplicados + ' | Errores: ' + data.errores;
                cargarClientesImportados(1);
            }
        }

        // Cargar datos al inicio y cada 30s
        cargarDatos();
        setInterval(cargarDatos, 30000);
    </script>
</body>
</html>"""


@app.get("/admin")
async def admin_dashboard(pwd: str = ""):
    """Retorna dashboard HTML con autenticación por password."""
    # Verificar password
    if pwd != ADMIN_PASSWORD:
        return HTMLResponse(get_login_html())

    return HTMLResponse(get_dashboard_html())


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


@app.get("/api/admin/sin-respuesta")
async def admin_sin_respuesta(horas: int = 2):
    """Leads sin respuesta hace más de X horas."""
    from agent.admin_api import obtener_mensajes_sin_respuesta
    return await obtener_mensajes_sin_respuesta(horas)


@app.post("/api/admin/enviar-masivo")
async def admin_enviar_masivo(mensaje: str = "", imagen_url: str = ""):
    """
    Envía un mensaje masivo (broadcast) a todos los leads.

    Args:
        mensaje: Texto del mensaje
        imagen_url: URL de imagen opcional

    Returns:
        {"exitosos": int, "fallidos": int, "total": int}
    """
    from agent.admin_api import enviar_broadcast

    if not mensaje and not imagen_url:
        return {"error": "Debe proporcionar al menos un mensaje o imagen"}

    resultado = await enviar_broadcast(mensaje, imagen_url, proveedor)
    return resultado


@app.post("/api/admin/enviar-imagen")
async def admin_enviar_imagen(telefono: str = "", imagen_url: str = "", caption: str = ""):
    """
    Envía una imagen a un cliente específico.

    Args:
        telefono: Número del cliente
        imagen_url: URL de la imagen
        caption: Texto que acompaña la imagen

    Returns:
        {"exito": bool, "mensaje": str}
    """
    if not telefono or not imagen_url:
        return {"exito": False, "mensaje": "Teléfono e imagen_url son requeridos"}

    try:
        exito = await proveedor.enviar_imagen(telefono, imagen_url, caption)
        return {
            "exito": exito,
            "mensaje": "Imagen enviada" if exito else "Error al enviar imagen"
        }
    except Exception as e:
        logger.error(f"Error al enviar imagen a {telefono}: {e}")
        return {"exito": False, "mensaje": str(e)}


@app.get("/api/admin/clientes-importados")
async def admin_clientes_importados(pagina: int = 1, por_pagina: int = 20, q: str = ""):
    """
    Obtiene clientes importados con paginación y búsqueda opcional.

    Args:
        pagina: Número de página (1-based)
        por_pagina: Cantidad de registros por página
        q: Texto de búsqueda (nombre o teléfono)

    Returns:
        {"clientes": [...], "total": int, "pagina": int, "total_paginas": int}
    """
    from agent.admin_api import obtener_clientes_importados, buscar_clientes_importados

    if q:
        # Búsqueda
        clientes = await buscar_clientes_importados(q)
        return {"clientes": clientes, "total": len(clientes), "pagina": 1, "total_paginas": 1}
    else:
        # Paginación
        resultado = await obtener_clientes_importados(pagina, por_pagina)
        return resultado


@app.post("/api/admin/tomar-control")
async def admin_tomar_control(telefono: str = ""):
    """
    Pausa el bot para un cliente específico — un humano toma control.

    Args:
        telefono: Número del cliente

    Returns:
        {"exito": bool, "mensaje": str}
    """
    from agent.memory import tomar_control

    if not telefono:
        return {"exito": False, "mensaje": "Teléfono requerido"}

    try:
        exito = await tomar_control(telefono)
        return {
            "exito": exito,
            "mensaje": "Bot pausado - Humano en control" if exito else "No se pudo pausar"
        }
    except Exception as e:
        logger.error(f"Error pausando bot para {telefono}: {e}")
        return {"exito": False, "mensaje": str(e)}


@app.post("/api/admin/liberar-control")
async def admin_liberar_control(telefono: str = ""):
    """
    Reactiva el bot para un cliente específico.

    Args:
        telefono: Número del cliente

    Returns:
        {"exito": bool, "mensaje": str}
    """
    from agent.memory import liberar_control

    if not telefono:
        return {"exito": False, "mensaje": "Teléfono requerido"}

    try:
        exito = await liberar_control(telefono)
        return {
            "exito": exito,
            "mensaje": "Bot reactivado" if exito else "No se pudo reactivar"
        }
    except Exception as e:
        logger.error(f"Error reactivando bot para {telefono}: {e}")
        return {"exito": False, "mensaje": str(e)}


@app.post("/api/admin/importar-excel")
async def admin_importar_excel():
    """
    Importa clientes desde el archivo Excel default.
    Archivo: knowledge/clientes rebody importado.xlsx

    Returns:
        {"exitosos": int, "errores": int, "total": int, ...}
    """
    from agent.excel_parser import importar_clientes_de_archivo_default

    try:
        resultado = await importar_clientes_de_archivo_default()
        return resultado
    except Exception as e:
        logger.error(f"Error importando Excel: {e}")
        return {"error": str(e)}
