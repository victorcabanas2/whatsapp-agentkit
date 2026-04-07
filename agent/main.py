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
    """Página del dashboard con leads, pedidos y analytics."""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel Admin - Belén</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        h1 { margin: 20px 0; font-size: 28px; }
        h2 { margin: 30px 0 15px 0; font-size: 18px; }
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
        .refresh { text-align: right; margin: 20px 0; font-size: 12px; color: #94a3b8; }
        .loading { text-align: center; padding: 40px; }
        .copy-btn { background: none; border: none; color: #3b82f6; cursor: pointer; font-size: 12px; padding: 0; }
        .copy-btn:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Panel Admin - Belén</h1>
            <div style="font-size: 12px; color: #94a3b8;">Auto-refresh cada 30s</div>
        </div>

        <div class="stats" id="stats">
            <div style="grid-column: 1/-1; text-align: center;">Cargando...</div>
        </div>

        <h2>🔥 Leads HOT (Score alto)</h2>
        <table id="hot-leads-table">
            <thead><tr>
                <th>Teléfono</th><th>Nombre</th><th>Producto</th><th>Score</th><th>Intención</th><th>Último Msg</th><th>Acción</th>
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

    <script>
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

                document.getElementById('stats').innerHTML = `
                    <div class="stat-card"><div class="stat-number">${stats.total_leads}</div><div class="stat-label">Total Leads</div></div>
                    <div class="stat-card"><div class="stat-number">${stats.leads_hoy}</div><div class="stat-label">Leads Hoy</div></div>
                    <div class="stat-card hot"><div class="stat-number">${stats.hot_leads}</div><div class="stat-label">🔥 Hot Leads</div></div>
                    <div class="stat-card"><div class="stat-number">${stats.conversion_pct}%</div><div class="stat-label">Conversión</div></div>
                    <div class="stat-card pending"><div class="stat-number">${stats.pedidos_pendientes}</div><div class="stat-label">Pedidos Pendientes</div></div>
                    <div class="stat-card"><div class="stat-number">${stats.sin_respuesta_2h}</div><div class="stat-label">Sin Respuesta >2h</div></div>
                `;

                // Hot leads
                const hotRes = await fetch('/api/admin/leads?estado=hot&limite=5');
                const hotLeads = await hotRes.json();
                document.querySelector('#hot-leads-table tbody').innerHTML = hotLeads.length > 0 ?
                    hotLeads.map(l => `<tr>
                        <td><a onclick="copyPhone('${l.telefono}')" title="Copiar">${l.telefono}</a></td>
                        <td>${l.nombre}</td>
                        <td>${l.producto_preferido}</td>
                        <td>${l.score}</td>
                        <td>${getBadgeIntention(l.intencion)}</td>
                        <td>${new Date(l.ultimo_mensaje).toLocaleTimeString('es-PY')}</td>
                        <td><a href="https://wa.me/${l.telefono}" target="_blank">📱</a></td>
                    </tr>`).join('') : '<tr><td colspan="7">Sin leads hot</td></tr>';

                // All leads
                const leadsRes = await fetch('/api/admin/leads');
                const leads = await leadsRes.json();
                document.querySelector('#leads-table tbody').innerHTML = leads.length > 0 ?
                    leads.map(l => `<tr>
                        <td><a onclick="copyPhone('${l.telefono}')">${l.telefono}</a></td>
                        <td>${l.nombre}</td>
                        <td>${l.producto_preferido}</td>
                        <td>${l.score}</td>
                        <td>${getBadgeIntention(l.intencion)}</td>
                        <td>${new Date(l.ultimo_mensaje).toLocaleTimeString('es-PY')}</td>
                        <td>${l.fue_cliente ? '<span class="badge badge-success">✓ Cliente</span>' : '<span class="badge badge-pending">Lead</span>'}</td>
                    </tr>`).join('') : '<tr><td colspan="7">Sin leads</td></tr>';

                // Sin respuesta
                const sinRespRes = await fetch('/api/admin/sin-respuesta?horas=2');
                const sinResp = await sinRespRes.json();
                document.querySelector('#sin-respuesta-table tbody').innerHTML = sinResp.length > 0 ?
                    sinResp.map(l => `<tr>
                        <td><a onclick="copyPhone('${l.telefono}')">${l.telefono}</a></td>
                        <td>${l.nombre}</td>
                        <td>${l.horas_sin_respuesta}h</td>
                        <td>${l.score}</td>
                        <td>${l.ultimo_mensaje}</td>
                        <td><a href="https://wa.me/${l.telefono}" target="_blank">📱 Escribir</a></td>
                    </tr>`).join('') : '<tr><td colspan="6">Todos respondidos</td></tr>';

                // Pedidos
                const pedidosRes = await fetch('/api/admin/pedidos');
                const pedidos = await pedidosRes.json();
                document.querySelector('#pedidos-table tbody').innerHTML = pedidos.length > 0 ?
                    pedidos.map(p => `<tr>
                        <td><a onclick="copyPhone('${p.telefono}')">${p.telefono}</a></td>
                        <td>${p.producto}</td>
                        <td>${p.precio}</td>
                        <td>${p.metodo_pago}</td>
                        <td>${p.estado === 'pagado' ? '<span class="badge badge-success">✓ Pagado</span>' : '<span class="badge badge-danger">⏳ Pendiente</span>'}</td>
                        <td>${new Date(p.fecha_pedido).toLocaleString('es-PY')}</td>
                    </tr>`).join('') : '<tr><td colspan="6">Sin pedidos</td></tr>';

            } catch (e) {
                console.error('Error:', e);
            }
        }

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
