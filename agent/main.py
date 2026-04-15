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
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException, Cookie
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy import select, desc, func

from agent.brain import generar_respuesta, detectar_confirmacion_pago, mapear_anuncio_a_producto
from agent.ad_analyzer import identificar_producto_desde_anuncio
from agent.stock_panel import router as stock_router
from agent.memory import (
    # Funciones core
    inicializar_db,
    guardar_mensaje,
    obtener_historial,
    registrar_lead,
    guardar_pedido,
    guardar_pedido_atomico,
    obtener_ultimo_pedido,
    actualizar_estado_pedido,
    actualizar_lead_scoring,
    obtener_lead,
    marcar_alerta_vendedor,
    obtener_resumen_cliente,
    # Integridad
    validar_integridad_referencial,
    # Auditoría y errores
    registrar_auditoria,
    obtener_errores_recientes,
    obtener_historial_auditoria_tabla,
    obtener_estadisticas_auditoria,
    # Excepciones custom
    AgentKitError,
    IntegrityViolationError,
    ValidationError,
    AtomicityError,
    DataConsistencyError,
    # Modelos
    async_session,
    Lead,
    Pedido,
    Mensaje,
    Auditoria,
)
from agent.providers import obtener_proveedor
from agent.scheduler import crear_background_tasks, cancelar_background_tasks

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
ADMIN_WHATSAPP = os.getenv("ADMIN_WHATSAPP", "+595986147509")

# Chats silenciados (admin tomó control)
MUTED_CHATS = set()  # {telefono1, telefono2, ...}

# ════════════════════════════════════════════════════════════
# BUFFERING DE MENSAJES — Agrupa mensajes rápidos del mismo cliente
# ════════════════════════════════════════════════════════════
PENDING_MESSAGES: dict[str, list] = {}   # telefono → [MensajeEntrante, ...]
PENDING_TASKS: dict[str, asyncio.Task] = {}  # telefono → asyncio.Task
BUFFER_DELAY = 10.0  # segundos de espera — permite acumular typos/correcciones antes de responder

# ════════════════════════════════════════════════════════════
# TRACKING MENSAJES PROPIOS — Evita doble-guardado de mensajes del bot
# Cuando el bot envía un mensaje, Whapi devuelve un webhook "from_me: true".
# Registramos los últimos textos enviados para ignorar esos ecos.
# Los mensajes "from_me" que NO están aquí son respuestas manuales de Victor.
# ════════════════════════════════════════════════════════════
RECENTLY_SENT_BOT: dict[str, float] = {}  # "{phone}:{text_prefix}" → timestamp enviado


# ════════════════════════════════════════════════════════════
# LEAD SCORING — Detección de intención y urgencia
# ════════════════════════════════════════════════════════════

KEYWORDS_HOT = [
    "compro", "me llevo", "quiero comprarlo", "cómo pago",
    "dale", "cómo hago la transferencia", "cuándo llega", "listo",
    "ya me decide", "adelante con eso", "va", "que sea"
]

# ════════════════════════════════════════════════════════════
# DETECCIÓN DE PRODUCTO EN MENSAJE — Fallback cuando Meta no envía contexto
# ════════════════════════════════════════════════════════════

def detectar_producto_en_mensaje(texto: str) -> str | None:
    """
    Extrae el producto mencionado en el mensaje del cliente por palabras clave.
    Usado como fallback cuando el referral de Meta no viene en el webhook.
    """
    t = texto.lower()

    # JetBoots — "bota", "boot", "jetboots", "therabody boot"
    if any(k in t for k in ["jetboots", "jet boots"]):
        if any(k in t for k in ["pro plus", "proplus", "pro+"]):
            return "JetBoots Pro Plus"
        if "prime" in t:
            return "JetBoots Prime"
        return "JetBoots"
    if any(k in t for k in ["bota", "botas"]):
        if any(k in t for k in ["pro plus", "proplus"]):
            return "JetBoots Pro Plus"
        if "prime" in t:
            return "JetBoots Prime"
        return "JetBoots"  # ambas opciones, Claude decide

    # RecoveryPulse Arm / Calf
    if any(k in t for k in ["recoverypulse", "recovery pulse", "recovery arm", "brazo compresión", "manga compresion", "manga de compresión", "germánico"]):
        return "RecoveryPulse Calf Sleeve"

    # TheraCup
    if any(k in t for k in ["theracup", "thera cup", "ventosa de masaje"]):
        return "TheraCup"

    # Theragun
    if "theragun" in t:
        if "mini" in t:
            return "Theragun Mini 3.0"
        if "sense" in t:
            return "Theragun Sense"
        if any(k in t for k in ["pro plus", "proplus", "pro +"]):
            return "Theragun PRO Plus"
        return "Theragun"

    # WaveSolo
    if any(k in t for k in ["wavesolo", "wave solo"]):
        return "WaveSolo"

    # TheraFace
    if any(k in t for k in ["theraface", "thera face"]):
        if any(k in t for k in ["mask", "máscara", "mascara"]):
            return "TheraFace Mask"
        if "depuff" in t or "ojera" in t:
            return "TheraFace Depuffing Wand"
        return "TheraFace PRO"

    # SmartGoggles
    if any(k in t for k in ["smartgoggles", "smart goggles", "goggle", "lentes de compresión"]):
        return "SmartGoggles 2.0"

    # WHOOP
    if "whoop" in t:
        if "life" in t or " mg" in t:
            return "WHOOP LIFE MG"
        if "peak" in t:
            return "WHOOP PEAK 5.0"
        if "one" in t:
            return "WHOOP ONE 5.0"
        return "WHOOP"

    # FOREO
    if "foreo" in t:
        if "211" in t or "cuello" in t or "neck" in t:
            return "FOREO FAQ 211"
        if "221" in t or "mano" in t or "hand" in t:
            return "FOREO FAQ 221"
        return "FOREO"

    # ThermBack
    if any(k in t for k in ["thermback", "therm back", "manta led", "espalda led"]):
        return "ThermBack LED"

    # SleepMask
    if any(k in t for k in ["sleepmask", "sleep mask", "antifaz"]):
        return "SleepMask"

    return None

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


def _combinar_mensajes(messages: list) -> object:
    """
    Combina múltiples mensajes del mismo cliente en uno solo.
    Descarta typos muy cortos (1-3 chars) si van seguidos de una corrección.
    """
    if len(messages) == 1:
        return messages[0]

    textos_validos = []
    imagen_final = None

    for i, msg in enumerate(messages):
        texto = msg.texto.strip()
        hay_siguiente = i < len(messages) - 1

        # Saltar mensajes muy cortos (posible typo) si hay un mensaje posterior más largo
        if hay_siguiente and 1 <= len(texto) <= 3 and texto.isalpha():
            logger.debug(f"📝 Posible typo ignorado: '{texto}'")
            continue

        if texto:
            textos_validos.append(texto)

        if msg.imagen_url:
            imagen_final = msg.imagen_url

    # Usar el último mensaje como base (metadata más reciente)
    combined = messages[-1]
    if textos_validos:
        combined.texto = "\n".join(textos_validos)
    if imagen_final and not combined.imagen_url:
        combined.imagen_url = imagen_final

    return combined


async def _handle_admin_command(msg) -> bool:
    """
    Procesa comandos de admin (/takeover, /release).
    Retorna True si fue un comando admin y fue manejado.
    """
    if msg.telefono != ADMIN_WHATSAPP:
        return False

    if msg.texto.startswith("/takeover"):
        parts = msg.texto.split()
        if len(parts) > 1:
            target = parts[1]
            from agent.memory import tomar_control
            exito = await tomar_control(target)
            if exito:
                MUTED_CHATS.add(target)
                await proveedor.enviar_mensaje(msg.telefono, f"✅ Chat {target} silenciado. Bot no responderá.")
                logger.info(f"🔇 Admin silencia chat {target}")
            else:
                await proveedor.enviar_mensaje(msg.telefono, f"❌ No encontré el lead {target}")
        return True

    if msg.texto.startswith("/release"):
        parts = msg.texto.split()
        if len(parts) > 1:
            target = parts[1]
            from agent.memory import liberar_control
            exito = await liberar_control(target)
            if exito:
                MUTED_CHATS.discard(target)
                await proveedor.enviar_mensaje(msg.telefono, f"✅ Chat {target} activado. Bot responderá nuevamente.")
                logger.info(f"🔊 Admin reactiva chat {target}")
            else:
                await proveedor.enviar_mensaje(msg.telefono, f"❌ No encontré el lead {target}")
        return True

    return False


async def _enviar_respuesta_audio(telefono: str):
    """Responde amablemente cuando el cliente envía un audio."""
    respuesta = "Disculpá, por el momento no puedo escuchar audios 🙏 ¿Me podés escribir tu consulta?"
    try:
        await proveedor.enviar_mensaje(telefono, respuesta)
        await guardar_mensaje(telefono, "user", "[Audio enviado — no procesado]")
        await guardar_mensaje(telefono, "assistant", respuesta)
        logger.info(f"🎵 Respuesta de audio enviada a {telefono}")
    except Exception as e:
        logger.error(f"Error enviando respuesta de audio a {telefono}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa recursos al arrancar el servidor."""
    logger.info("━" * 60)
    logger.info("🚀 Iniciando AgentKit — WhatsApp AI Agent")
    logger.info("━" * 60)

    # Inicializar base de datos
    await inicializar_db()
    logger.info("✓ Base de datos inicializada")

    # Sincronizar MUTED_CHATS desde BD (chats pausados)
    async with async_session() as session:
        query = select(Lead).where(Lead.en_manos_humanas == True)
        result = await session.execute(query)
        pausados = result.scalars().all()
        for lead in pausados:
            MUTED_CHATS.add(lead.telefono)
        if pausados:
            logger.info(f"✓ Sincronizados {len(pausados)} chats pausados desde BD")

    # Inicializar background tasks (100% async, sin APScheduler)
    background_tasks = crear_background_tasks()
    logger.info(f"✓ {len(background_tasks)} tareas de background iniciadas (async)")

    # Sincronizar imágenes de productos desde Shopify
    try:
        from agent.shopify import sincronizar_imagenes_productos
        logger.info("📸 Sincronizando imágenes de productos desde Shopify...")
        imagenes = await sincronizar_imagenes_productos()
        logger.info(f"✓ Sincronización de imágenes completada ({len(imagenes)} productos)")
    except Exception as e:
        logger.warning(f"⚠️ Error sincronizando imágenes: {e}")

    logger.info(f"✓ Proveedor WhatsApp: {proveedor.__class__.__name__}")
    logger.info(f"✓ Modo: {ENVIRONMENT}")
    logger.info(f"✓ Puerto: {PORT}")
    logger.info("━" * 60)
    logger.info("✓ Servidor listo. Esperando mensajes...")
    logger.info("━" * 60)

    yield

    logger.info("🛑 Cancelando tareas de background...")
    cancelar_background_tasks(background_tasks)
    logger.info("🛑 Servidor detenido")


# Crear aplicación FastAPI
app = FastAPI(
    title="AgentKit — Belén Rebody Bot",
    description="Agente de WhatsApp AI para Rebody",
    version="1.0.0",
    lifespan=lifespan
)

# Habilitar CORS para peticiones del dashboard local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agregar routers
app.include_router(stock_router)

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


async def _procesar_mensaje_individual(msg):
    """
    Procesa un mensaje (ya combinado si hubo varios del mismo cliente).
    Maneja contexto, Claude, respuesta, scoring y alertas.
    """
    telefono = msg.telefono

    # ── AUDIO: responder con mensaje polite y salir ─────────
    if msg.texto.startswith(("[AUDIO_RECIBIDO", "[AUDIO_SIN_TRANSCRIBIR")):
        await _enviar_respuesta_audio(telefono)
        return

    logger.info(f"📨 Procesando mensaje de {telefono}: {msg.texto[:80]}...")

    try:
        # Registrar lead
        lead = await registrar_lead(telefono)
        es_nuevo_lead = (datetime.utcnow() - lead.primer_contacto).total_seconds() < 60

        # Historial
        historial = await obtener_historial(telefono, limite=100)
        logger.info(f"✓ Historial cargado: {len(historial)} mensajes")

        # ── CONTEXTUALIZACIÓN: Anuncios + Replies ──────────
        mensaje_contextualizado = msg.texto
        contexto_sistema = []

        logger.info(f"🔍 DEBUG ANUNCIO - anuncio_id: {msg.anuncio_id}")
        logger.info(f"🔍 payload: {msg.payload}")
        logger.info(f"🔍 contexto_anuncio: {msg.contexto_anuncio}")
        logger.info(f"🔍 imagen_url: {msg.imagen_url}")

        es_cliente_nuevo = len(historial) == 0
        es_mensaje_corto = len(msg.texto) < 150
        tiene_palabras_clave = any(
            palabra in msg.texto.lower()
            for palabra in ["quiero", "información", "precio", "más info", "porfa", "me interesa",
                            "consulta", "info", "promo", "anuncio", "vi", "interesa"]
        )
        viene_de_anuncio_probablemente = es_cliente_nuevo and es_mensaje_corto and tiene_palabras_clave

        if viene_de_anuncio_probablemente:
            logger.info(f"🎯 CLIENTE NUEVO + MENSAJE GENÉRICO → Probablemente viene de anuncio")

        # CASO 1: Anuncio Meta Ads (referral viene en el webhook)
        if msg.anuncio_id or msg.payload or msg.contexto_anuncio or viene_de_anuncio_probablemente:
            anuncio_info = msg.anuncio_id or msg.payload or (msg.contexto_anuncio.get("payload") if msg.contexto_anuncio else None)
            ad_url = msg.contexto_anuncio.get("ad_url") if msg.contexto_anuncio else None
            headline = msg.contexto_anuncio.get("headline") if msg.contexto_anuncio else None

            logger.info(f"📢 CLIENTE VIENE DE ANUNCIO: {anuncio_info} | headline: {headline}")

            producto_identificado = await identificar_producto_desde_anuncio(
                imagen_url=msg.imagen_url,
                ad_url=ad_url,
                payload=anuncio_info,
                headline=headline,
            )

            if not producto_identificado:
                producto_identificado = mapear_anuncio_a_producto(anuncio_info) if anuncio_info else None

            tiene_contexto_real = bool(msg.anuncio_id or msg.payload or msg.contexto_anuncio)

            # CAPA EXTRA: Si aún no identificamos el producto, buscarlo en el texto del mensaje
            if not producto_identificado:
                producto_en_texto = detectar_producto_en_mensaje(msg.texto)
                if producto_en_texto:
                    producto_identificado = producto_en_texto
                    logger.info(f"🔍 Producto detectado en texto del mensaje: {producto_en_texto}")

            if not producto_identificado and viene_de_anuncio_probablemente and not tiene_contexto_real:
                # Último recurso: no hay datos del anuncio NI en el texto → preguntar brevemente
                contexto_sistema.append(f"🎯 CONTEXTO: Este cliente probablemente viene de un anuncio de Instagram/Facebook.")
                contexto_sistema.append(f"✅ El cliente escribió: \"{msg.texto}\"")
                contexto_sistema.append(f"✅ No podemos identificar el producto exacto desde el anuncio.")
                contexto_sistema.append(f"✅ Pregunta de forma breve y cálida: '¿Sobre qué producto es tu consulta?' — UNA SOLA pregunta.")
                contexto_sistema.append(f"✅ NO listes productos ni hagas preguntas largas. Solo esa pregunta corta.")
                mensaje_contextualizado = f"[CLIENTE DE ANUNCIO - NO SE PUDO IDENTIFICAR PRODUCTO] {msg.texto}"
            else:
                nombre_producto = producto_identificado or headline or anuncio_info or "el producto del anuncio"
                contexto_sistema.append(f"🎯 CONTEXTO CRÍTICO: Este cliente hizo clic en un anuncio de Meta Ads.")
                if headline:
                    contexto_sistema.append(f"Anuncio: \"{headline}\"")
                contexto_sistema.append(f"Producto identificado: {nombre_producto}")
                contexto_sistema.append(f"✅ YA SABÉS qué producto es. NO preguntes 'de qué producto es tu consulta'.")
                contexto_sistema.append(f"✅ Respondé DIRECTAMENTE con info completa sobre: {nombre_producto}")
                contexto_sistema.append(f"✅ Incluí: precio, stock actual, beneficios principales y link de compra.")
                mensaje_contextualizado = f"[CLIENTE VIENE DE ANUNCIO DE: {nombre_producto}] {msg.texto}"

        # CASO 1.5: Cliente nuevo menciona un producto en su mensaje (sin ser detectado como "anuncio")
        # Esto cubre el caso: "Escribo por la promo de la bota therabody"
        elif es_cliente_nuevo and not contexto_sistema:
            producto_en_texto = detectar_producto_en_mensaje(msg.texto)
            if producto_en_texto:
                logger.info(f"🔍 Producto en mensaje de cliente nuevo: {producto_en_texto}")
                contexto_sistema.append(f"🎯 CONTEXTO: El cliente nuevo menciona '{producto_en_texto}' en su mensaje.")
                contexto_sistema.append(f"✅ Respondé DIRECTAMENTE sobre {producto_en_texto} — precio, stock, beneficios, link.")
                contexto_sistema.append(f"✅ NO preguntes de qué producto es — ya lo mencionó.")
                mensaje_contextualizado = f"[CLIENTE PREGUNTA POR: {producto_en_texto}] {msg.texto}"

        # CASO 2: Reply a mensaje anterior
        if msg.reply_a_texto:
            logger.info(f"↩️ CLIENTE RESPONDE A MENSAJE: {msg.reply_a_texto[:60]}...")
            contexto_sistema.append(f"↩️ CONTEXTO DE REPLY: El cliente está respondiendo a este mensaje:")
            contexto_sistema.append(f"Mensaje al que responde: \"{msg.reply_a_texto[:200]}\"")
            contexto_sistema.append(f"✅ INTERPRETA la respuesta en ese contexto.")
            contexto_sistema.append(f"✅ Si el mensaje es de Victor (el dueño), reconocé que ya hubo conversación previa.")
            contexto_sistema.append(f"✅ NO saludés de cero si ya hay contexto anterior.")
            mensaje_contextualizado = f"[Reply a: '{msg.reply_a_texto[:100]}'] {msg.texto}"

        if contexto_sistema:
            logger.debug(f"📌 Contexto especial:\n" + "\n".join(contexto_sistema))

        # ── MUTE CHECK ──────────────────────────────────────
        lead_check = await obtener_lead(telefono)
        if lead_check and lead_check.en_manos_humanas:
            logger.info(f"🔇 Chat {telefono} en manos humanas. Bot no responde.")
            return

        if telefono in MUTED_CHATS:
            logger.info(f"🔇 Chat {telefono} silenciado.")
            return

        # ── GENERAR RESPUESTA CON CLAUDE ────────────────────
        logger.debug("Llamando a Claude AI...")
        respuesta_raw = await generar_respuesta(
            mensaje_contextualizado,
            historial,
            imagen_url=msg.imagen_url,
            contexto_adicional="\n".join(contexto_sistema) if contexto_sistema else None
        )

        from agent.brain import extraer_imagen_de_respuesta, obtener_url_imagen, detectar_y_programar_seguimiento
        respuesta_limpia, product_id = extraer_imagen_de_respuesta(respuesta_raw)
        url_imagen_producto = obtener_url_imagen(product_id) if product_id else None

        # ── SEGUIMIENTOS DINÁMICOS ──────────────────────────
        respuesta_limpia = await detectar_y_programar_seguimiento(
            mensaje_usuario=msg.texto,
            respuesta_belén=respuesta_limpia,
            telefono=telefono,
            nombre_cliente=lead.nombre
        )

        # ── GUARDAR MENSAJES ────────────────────────────────
        content_a_guardar = f"[IMG:{msg.imagen_url}]\n{msg.texto}" if msg.imagen_url else msg.texto
        if msg.imagen_url:
            logger.info(f"📸 Guardando mensaje con imagen: {msg.imagen_url[:60]}...")
        await guardar_mensaje(telefono, "user", content_a_guardar)

        # ── LEAD SCORING ────────────────────────────────────
        score_anterior = lead.score
        intencion_anterior = lead.intencion
        await calcular_lead_score(telefono, msg.texto, lead)
        lead = await obtener_lead(telefono)

        # ── ALERTAS AL VENDEDOR ─────────────────────────────
        if es_nuevo_lead and not lead.alerta_vendedor_enviada:
            nombre = lead.nombre or telefono
            await enviar_alerta_vendedor(
                "nuevo_lead", telefono,
                f"{nombre} ({telefono})\nDice: '{msg.texto[:80]}...'"
            )
            await marcar_alerta_vendedor(telefono)

        if (score_anterior < 50 or intencion_anterior != "hot") and lead.intencion == "hot":
            nombre = lead.nombre or telefono
            await enviar_alerta_vendedor(
                "hot_lead", telefono,
                f"{nombre} ({telefono})\nScore: {lead.score}/100\nDice: '{msg.texto[:80]}...'"
            )

        # ── ENVIAR RESPUESTA ────────────────────────────────
        await guardar_mensaje(telefono, "assistant", respuesta_limpia)
        # Registrar texto enviado para evitar doble-guardado cuando Whapi envía el eco "from_me"
        _bot_key = f"{telefono}:{respuesta_limpia[:80]}"
        RECENTLY_SENT_BOT[_bot_key] = datetime.utcnow().timestamp()
        exito = await proveedor.enviar_mensaje(telefono, respuesta_limpia)

        if exito:
            logger.info(f"✓ Respuesta enviada a {telefono}")
            logger.debug(f"   Respuesta: {respuesta_limpia[:100]}...")
        else:
            logger.error(f"✗ Fallo al enviar respuesta a {telefono}")

        if url_imagen_producto:
            await asyncio.sleep(1)
            exito_img = await enviar_imagen(telefono, url_imagen_producto)
            if exito_img:
                logger.info(f"📸 Imagen enviada a {telefono} (product_id: {product_id})")
            else:
                logger.warning(f"⚠️ Error enviando imagen a {telefono}")

        # ── PAGOS ───────────────────────────────────────────
        metodo_pago = detectar_opcion_pago(respuesta_limpia)
        if metodo_pago == "transferencia":
            logger.info(f"💳 {telefono} eligió TRANSFERENCIA — enviando datos bancarios")
            await enviar_imagen(telefono, IMAGEN_DATOS_BANCARIOS)

        if detectar_confirmacion_pago(msg.texto):
            logger.info(f"✅ {telefono} confirmó pago")
            ultimo_pedido = await obtener_ultimo_pedido(telefono)
            if ultimo_pedido and ultimo_pedido.estado == "pendiente":
                await actualizar_estado_pedido(ultimo_pedido.id, "pagado")
                logger.info(f"💰 Pedido #{ultimo_pedido.id} marcado como PAGADO")
                nombre = lead.nombre or telefono
                await enviar_alerta_vendedor(
                    "pago_confirmado", telefono,
                    f"{nombre} ({telefono})\nProducto: {ultimo_pedido.producto}\nPrecio: {ultimo_pedido.precio} Gs"
                )
            else:
                logger.warning(f"⚠️ No hay pedido pendiente para {telefono}")

    except Exception as e:
        logger.error(f"✗ Error procesando mensaje de {telefono}: {e}")
        try:
            await proveedor.enviar_mensaje(
                telefono,
                "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos."
            )
        except Exception as send_error:
            logger.error(f"✗ No se pudo enviar mensaje de error: {send_error}")


async def _esperar_y_procesar(telefono: str):
    """
    Espera BUFFER_DELAY segundos acumulando mensajes del mismo cliente,
    luego los combina y procesa como uno solo.
    Si llega otro mensaje antes, esta tarea se cancela y se reprograma.
    """
    try:
        await asyncio.sleep(BUFFER_DELAY)
    except asyncio.CancelledError:
        logger.debug(f"⏳ Buffer cancelado para {telefono} (llegó otro mensaje)")
        return

    messages = PENDING_MESSAGES.pop(telefono, [])
    PENDING_TASKS.pop(telefono, None)

    if not messages:
        return

    if len(messages) > 1:
        logger.info(f"📦 Agrupando {len(messages)} mensajes de {telefono} en uno")

    msg = _combinar_mensajes(messages)
    await _procesar_mensaje_individual(msg)


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp. Bufferiza por cliente (3.5s) para agrupar
    mensajes enviados rápido y procesarlos como uno solo.
    """
    try:
        body = await request.json()
        logger.info(f"📨 WEBHOOK PAYLOAD COMPLETO: {body}")

        class DebugRequest:
            async def json(self):
                return body

        mensajes = await proveedor.parsear_webhook(DebugRequest())

        if not mensajes:
            logger.debug("No hay mensajes en el webhook")
            return {"status": "ok"}

        for msg in mensajes:
            if msg.es_propio:
                # Distinguir ecos del bot vs mensajes manuales de Victor
                _key = f"{msg.telefono}:{msg.texto[:80]}"
                _now = datetime.utcnow().timestamp()
                _is_bot_echo = _key in RECENTLY_SENT_BOT and (_now - RECENTLY_SENT_BOT[_key]) < 90
                if _is_bot_echo:
                    RECENTLY_SENT_BOT.pop(_key, None)
                    logger.debug(f"Eco del bot ignorado: {msg.telefono}")
                elif msg.texto and msg.texto.strip():
                    # Mensaje manual de Victor — guardar en historial para que Belén tenga contexto
                    await guardar_mensaje(msg.telefono, "assistant", msg.texto)
                    logger.info(f"💾 Mensaje manual de Victor guardado para contexto: {msg.telefono} → {msg.texto[:50]}...")
                continue

            if not msg.texto or not msg.texto.strip():
                logger.debug(f"Mensaje vacío de {msg.telefono}")
                continue

            # Comandos admin — procesar de inmediato, sin buffer
            if await _handle_admin_command(msg):
                continue

            # Audio — responder de inmediato sin buffer
            if msg.texto.startswith(("[AUDIO_RECIBIDO", "[AUDIO_SIN_TRANSCRIBIR")):
                asyncio.create_task(_enviar_respuesta_audio(msg.telefono))
                continue

            # Agregar al buffer del cliente
            PENDING_MESSAGES.setdefault(msg.telefono, []).append(msg)
            logger.debug(f"📥 Buffer de {msg.telefono}: {len(PENDING_MESSAGES[msg.telefono])} mensaje(s)")

            # Cancelar tarea anterior y reprogramar
            old_task = PENDING_TASKS.get(msg.telefono)
            if old_task and not old_task.done():
                old_task.cancel()

            PENDING_TASKS[msg.telefono] = asyncio.create_task(
                _esperar_y_procesar(msg.telefono)
            )

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

        # ✅ USAR GUARDAR ATÓMICO: actualiza lead + pedido en UNA transacción
        pedido = await guardar_pedido_atomico(
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

        logger.info(f"✅ Pedido guardado (atómico): {pedido}")

        return {
            "status": "ok",
            "pedido_id": pedido.id,
            "mensaje": f"Pedido #{pedido.id} guardado correctamente"
        }

    except ValidationError as e:
        logger.warning(f"⚠️ Validación rechazada: {e}")
        raise HTTPException(status_code=422, detail=f"Validación fallida: {str(e)}")

    except IntegrityViolationError as e:
        logger.error(f"❌ Violación de integridad: {e}")
        raise HTTPException(status_code=409, detail=f"Integridad comprometida: {str(e)}")

    except AtomicityError as e:
        logger.error(f"❌ Error de atomicidad (ROLLBACK): {e}")
        raise HTTPException(status_code=500, detail=f"Transacción fallida: {str(e)}")

    except AgentKitError as e:
        logger.error(f"❌ Error de AgentKit: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.critical(f"❌ Error inesperado creando pedido: {e}")
        # Registrar en auditoría el error inesperado
        await registrar_auditoria(
            tabla="pedidos",
            operacion="INSERT",
            usuario="api",
            error=True,
            mensaje_error=f"Error inesperado: {str(e)}"
        )
        raise HTTPException(status_code=500, detail="Error interno del servidor")


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
                    <th>Teléfono</th><th>Nombre</th><th>Producto</th><th>Score</th><th>Intención</th><th>Último Msg</th><th>Estado</th><th>Control</th>
                </tr></thead>
                <tbody><tr><td colspan="8" class="loading">Cargando...</td></tr></tbody>
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
                <h3>Enviar Texto Masivo (+ Imagen Opcional)</h3>
                <div class="form-group">
                    <label>Mensaje de texto:</label>
                    <textarea id="broadcast-texto" placeholder="Escribe el mensaje que quieres enviar a todos los clientes..." style="height: 100px;"></textarea>
                </div>
                <div class="form-group">
                    <label>Imagen (opcional):</label>
                    <input type="file" id="broadcast-imagen" accept="image/*">
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
                    <label>Imagen:</label>
                    <input type="file" id="imagen-archivo" accept="image/*">
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
            <h2>📥 Clientes Importados</h2>

            <!-- IMPORT FROM EXCEL -->
            <div style="background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #10b981;">
                <h3 style="margin-bottom: 15px;">📊 Desde Excel</h3>
                <div class="form-group">
                    <label>Archivo Excel (.xlsx):</label>
                    <input type="file" id="excel-archivo" accept=".xlsx">
                </div>
                <button onclick="importarExcel()" style="background: #10b981; margin-right: 10px;">📥 Importar desde Excel</button>
                <div id="import-resultado" style="margin-top: 10px;"></div>
            </div>

            <!-- IMPORT FROM META -->
            <div style="background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #8b5cf6;">
                <h3 style="margin-bottom: 15px;">💬 Desde Meta/Facebook</h3>
                <details style="margin-bottom: 15px; cursor: pointer;">
                    <summary style="color: #94a3b8; font-size: 12px; font-weight: 500;">ℹ️ ¿Cómo obtener los datos de Meta?</summary>
                    <div style="margin-top: 10px; padding: 10px; background: #0f172a; border-radius: 4px; font-size: 12px; color: #cbd5e1;">
                        <p><strong>Paso 1:</strong> En Meta/Facebook, copia tus conversaciones de WhatsApp</p>
                        <p><strong>Paso 2:</strong> El formato debe ser tab-separado con columnas:</p>
                        <code style="display: block; background: #1e293b; padding: 8px; margin: 8px 0; border-left: 2px solid #8b5cf6;">
contact_info    message_content    message_timestamp    profile_image
                        </code>
                        <p><strong>Paso 3:</strong> Cada fila debe tener: nombre (y opcionalmente teléfono), mensaje, hora</p>
                        <p style="color: #7c3aed; margin-top: 8px;">💡 El parser extraerá automáticamente teléfonos, nombres y productos mencionados</p>
                    </div>
                </details>
                <div class="form-group">
                    <label>Datos Meta (tab-separados o archivo .txt):</label>
                    <textarea id="meta-datos" placeholder="Pega aquí los datos exportados de Meta, o carga un archivo .txt" style="width: 100%; height: 120px; padding: 10px; background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 4px; font-family: monospace; font-size: 12px;"></textarea>
                </div>
                <div style="margin-bottom: 15px;">
                    <button onclick="importarMeta()" style="background: #8b5cf6; margin-right: 10px;">💬 Importar desde Meta</button>
                    <button onclick="document.getElementById('meta-archivo').click()" style="background: #6366f1; margin-right: 10px;">📁 Cargar archivo .txt</button>
                    <input type="file" id="meta-archivo" accept=".txt" style="display: none;" onchange="leerArchivoMeta()">
                </div>
                <div id="meta-resultado" style="margin-top: 10px;"></div>
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

                // Cargar estado de control para cada lead
                const leadsConControl = await Promise.all(
                    leads.map(async (l) => {
                        const controlRes = await fetch('/api/admin/chat-status?telefono=' + encodeURIComponent(l.telefono));
                        const controlData = await controlRes.json();
                        return { ...l, control: controlData.control };
                    })
                );

                document.querySelector('#leads-table tbody').innerHTML = leadsConControl.length > 0 ?
                    leadsConControl.map(l => {
                        const controlBadge = l.control === 'admin' ?
                            '<span class="badge" style="background: #ef4444;">🔇 Admin</span>' :
                            '<span class="badge badge-success">🤖 Bot</span>';
                        const toggleBtn = '<button onclick="toggleControl(' + JSON.stringify(l.telefono) + ')" style="padding: 5px 10px; font-size: 12px; background: ' + (l.control === 'admin' ? '#10b981' : '#ef4444') + ';">' + (l.control === 'admin' ? '▶️ Activar' : '⏸️ Pausar') + '</button>';
                        return '<tr><td><a onclick="copyPhone(' + JSON.stringify(l.telefono) + ')">' + l.telefono + '</a></td><td>' + l.nombre + '</td><td>' + l.producto_preferido + '</td><td>' + l.score + '</td><td>' + getBadgeIntention(l.intencion) + '</td><td>' + new Date(l.ultimo_mensaje).toLocaleTimeString('es-PY') + '</td><td>' + (l.fue_cliente ? '<span class="badge badge-success">✓ Cliente</span>' : '<span class="badge badge-pending">Lead</span>') + '</td><td>' + controlBadge + ' ' + toggleBtn + '</td></tr>';
                    }).join('') : '<tr><td colspan="8">Sin leads</td></tr>';

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
            const archivoInput = document.getElementById('broadcast-imagen');
            if (!texto && (!archivoInput.files || archivoInput.files.length === 0)) {
                alert('Escribe un mensaje o carga una imagen');
                return;
            }

            document.getElementById('broadcast-resultado').innerText = 'Enviando...';
            const formData = new FormData();
            formData.append('mensaje', texto);
            if (archivoInput.files && archivoInput.files.length > 0) {
                formData.append('imagen', archivoInput.files[0]);
            }

            const res = await fetch('/api/admin/enviar-masivo', {method: 'POST', body: formData});
            const data = await res.json();
            document.getElementById('broadcast-resultado').innerText = '✓ Enviados: ' + data.exitosos + ' | ✗ Fallidos: ' + data.fallidos;
        }

        function limpiarBroadcast() {
            document.getElementById('broadcast-texto').value = '';
            document.getElementById('broadcast-imagen').value = '';
            document.getElementById('broadcast-resultado').innerText = '';
        }

        async function enviarImagen() {
            const tel = document.getElementById('imagen-telefono').value;
            const archivoInput = document.getElementById('imagen-archivo');
            const caption = document.getElementById('imagen-caption').value;

            if (!tel) {
                alert('Teléfono requerido');
                return;
            }
            if (!archivoInput.files || archivoInput.files.length === 0) {
                alert('Carga una imagen');
                return;
            }

            document.getElementById('imagen-resultado').innerText = 'Enviando...';
            const formData = new FormData();
            formData.append('telefono', tel);
            formData.append('imagen', archivoInput.files[0]);
            formData.append('caption', caption);

            const res = await fetch('/api/admin/enviar-imagen', {method: 'POST', body: formData});
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

        async function toggleControl(telefono) {
            try {
                const res = await fetch('/api/admin/toggle-control?telefono=' + encodeURIComponent(telefono), {method: 'POST'});
                const data = await res.json();
                console.log('Toggle:', data);
                // Recargar tabla
                await cargarDashboard();
            } catch (e) {
                console.error('Error toggling control:', e);
                alert('Error al cambiar control: ' + e);
            }
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
            const archivoInput = document.getElementById('excel-archivo');
            if (!archivoInput.files || archivoInput.files.length === 0) {
                alert('Carga un archivo Excel');
                return;
            }
            if (!confirm('¿Importar clientes desde el archivo Excel?')) return;

            document.getElementById('import-resultado').innerText = 'Importando...';
            const formData = new FormData();
            formData.append('archivo', archivoInput.files[0]);

            const res = await fetch('/api/admin/importar-excel', {method: 'POST', body: formData});
            const data = await res.json();

            if (data.error) {
                document.getElementById('import-resultado').innerText = '✗ Error: ' + data.error;
            } else {
                document.getElementById('import-resultado').innerText = '✓ Importados: ' + data.exitosos + ' | Duplicados: ' + data.duplicados + ' | Errores: ' + data.errores;
                cargarClientesImportados(1);
            }
        }

        function leerArchivoMeta() {
            const archivoInput = document.getElementById('meta-archivo');
            if (!archivoInput.files || archivoInput.files.length === 0) return;

            const file = archivoInput.files[0];
            const reader = new FileReader();
            reader.onload = (e) => {
                document.getElementById('meta-datos').value = e.target.result;
            };
            reader.readAsText(file);
        }

        async function importarMeta() {
            const datosText = document.getElementById('meta-datos').value.trim();
            if (!datosText) {
                alert('Ingresa datos de Meta o carga un archivo');
                return;
            }
            if (!confirm('¿Importar clientes desde Meta?')) return;

            document.getElementById('meta-resultado').innerText = 'Importando...';
            const formData = new FormData();
            formData.append('datos', datosText);

            const res = await fetch('/api/admin/importar-meta', {method: 'POST', body: formData});
            const data = await res.json();

            if (data.error) {
                document.getElementById('meta-resultado').innerText = '✗ Error: ' + data.error;
            } else {
                document.getElementById('meta-resultado').innerText = '✓ Importados: ' + data.exitosos + ' | Duplicados: ' + data.duplicados + ' | Errores: ' + data.errores;
                document.getElementById('meta-datos').value = '';
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
    try:
        from agent.admin_api import obtener_stats
        stats = await obtener_stats()
        return stats
    except Exception as e:
        logger.error(f"Error en admin_stats: {e}", exc_info=True)
        return {"error": str(e), "total_leads": 0, "leads_hoy": 0, "hot_leads": 0, "conversion_pct": 0, "pedidos_totales": 0, "pedidos_hoy": 0, "pedidos_pendientes": 0, "sin_respuesta_2h": 0}


@app.get("/api/admin/leads")
async def admin_leads(estado: str = "todos"):
    """Leads filtrados."""
    try:
        from agent.admin_api import obtener_leads
        return await obtener_leads(estado)
    except Exception as e:
        logger.error(f"Error en admin_leads: {e}", exc_info=True)
        return []


@app.get("/api/admin/pedidos")
async def admin_pedidos(estado: str = "todos"):
    """Pedidos filtrados."""
    try:
        from agent.admin_api import obtener_pedidos
        return await obtener_pedidos(estado)
    except Exception as e:
        logger.error(f"Error en admin_pedidos: {e}", exc_info=True)
        return []


@app.get("/api/admin/sin-respuesta")
async def admin_sin_respuesta(horas: int = 2):
    """Leads sin respuesta hace más de X horas."""
    try:
        from agent.admin_api import obtener_mensajes_sin_respuesta
        return await obtener_mensajes_sin_respuesta(horas)
    except Exception as e:
        logger.error(f"Error en admin_sin_respuesta: {e}", exc_info=True)
        return []


@app.get("/api/admin/chat-status")
async def get_chat_status(telefono: str):
    """Retorna si un chat está bajo control de admin o bot (desde BD)."""
    try:
        lead = await obtener_lead(telefono)
        if not lead:
            return {"telefono": telefono, "control": "desconocido", "en_manos_humanas": False}

        estado = "admin" if lead.en_manos_humanas else "bot"
        return {"telefono": telefono, "control": estado, "en_manos_humanas": lead.en_manos_humanas}
    except Exception as e:
        logger.error(f"Error en get_chat_status: {e}")
        return {"telefono": telefono, "control": "error", "en_manos_humanas": False}


@app.post("/api/admin/enviar-masivo")
async def enviar_masivo(telefonos: list, mensaje: str):
    """Envía mensaje a múltiples teléfonos."""
    try:
        proveedor = obtener_proveedor()
        resultados = []

        for telefono in telefonos:
            exito = await proveedor.enviar_mensaje(telefono, mensaje)
            resultados.append({"telefono": telefono, "exito": exito})
            logger.info(f"📤 Masivo a {telefono}: {'✅' if exito else '❌'}")

        return {
            "total": len(telefonos),
            "exitosos": sum(1 for r in resultados if r["exito"]),
            "fallidos": sum(1 for r in resultados if not r["exito"]),
            "resultados": resultados
        }
    except Exception as e:
        logger.error(f"Error envío masivo: {e}")
        return {"error": str(e)}


@app.post("/api/admin/toggle-control")
async def toggle_control(telefono: str):
    """Toggle: silencia/reactiva un chat guardando en BD."""
    try:
        lead = await obtener_lead(telefono)
        if not lead:
            return {"error": "Lead no encontrado", "telefono": telefono}

        if lead.en_manos_humanas:
            # Reactivar bot
            from agent.memory import liberar_control
            exito = await liberar_control(telefono)
            if exito:
                MUTED_CHATS.discard(telefono)
                logger.info(f"🟢 Bot reactivado para {telefono}")
                return {"telefono": telefono, "control": "bot", "action": "reactivado", "exito": True}
        else:
            # Pausar bot
            from agent.memory import tomar_control
            exito = await tomar_control(telefono)
            if exito:
                MUTED_CHATS.add(telefono)
                logger.info(f"🔴 Bot pausado para {telefono}")
                return {"telefono": telefono, "control": "admin", "action": "silenciado", "exito": True}

        return {"error": "No se pudo cambiar estado", "telefono": telefono}
    except Exception as e:
        logger.error(f"Error en toggle_control: {e}", exc_info=True)
        return {"error": str(e), "telefono": telefono}


@app.post("/api/admin/enviar-masivo")
async def admin_enviar_masivo(request: Request):
    """
    Envía un mensaje masivo (broadcast) a todos los leads.
    Acepta: mensaje (texto) e imagen (archivo, opcional)

    Returns:
        {"exitosos": int, "fallidos": int, "total": int}
    """
    try:
        from agent.admin_api import enviar_broadcast
        import base64

        form = await request.form()
        mensaje = form.get('mensaje', '')
        imagen_file = form.get('imagen')

        imagen_base64 = None
        if imagen_file:
            imagen_bytes = await imagen_file.read()
            imagen_base64_raw = base64.b64encode(imagen_bytes).decode()

            # Detectar MIME type del nombre del archivo
            filename = imagen_file.filename.lower()
            if filename.endswith('.png'):
                mime_type = 'image/png'
            elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
                mime_type = 'image/jpeg'
            elif filename.endswith('.gif'):
                mime_type = 'image/gif'
            elif filename.endswith('.webp'):
                mime_type = 'image/webp'
            else:
                mime_type = 'image/jpeg'  # default

            # Agregar prefijo data: para que el proveedor reconozca como base64 con MIME
            imagen_base64 = f"data:{mime_type};base64,{imagen_base64_raw}"

        resultado = await enviar_broadcast(mensaje, imagen_base64, proveedor)
        return resultado
    except Exception as e:
        logger.error(f"Error en enviar_masivo: {e}", exc_info=True)
        return {"exitosos": 0, "fallidos": 0, "total": 0, "error": str(e)}


@app.post("/api/admin/enviar-a-numeros")
async def admin_enviar_a_numeros(request: Request):
    """Envía mensaje a números específicos (JSON)."""
    try:
        body = await request.json()
        mensaje = body.get('mensaje', '')
        telefonos_list = body.get('telefonos', [])

        if not telefonos_list or not mensaje:
            return {"exitosos": 0, "fallidos": len(telefonos_list), "total": len(telefonos_list)}

        proveedor = obtener_proveedor()
        exitosos, fallidos = 0, 0

        for telefono in telefonos_list:
            try:
                exito = await proveedor.enviar_mensaje(telefono.strip(), mensaje)
                if exito:
                    exitosos += 1
                else:
                    fallidos += 1
            except:
                fallidos += 1

        return {"exitosos": exitosos, "fallidos": fallidos, "total": len(telefonos_list)}
    except Exception as e:
        logger.error(f"Error enviar_a_numeros: {e}")
        return {"exitosos": 0, "fallidos": 1, "total": 1}


@app.post("/api/admin/enviar-imagen")
async def admin_enviar_imagen(request: Request):
    """
    Envía una imagen a un cliente específico.
    Acepta: telefono, imagen (archivo), caption (texto, opcional)

    Returns:
        {"exito": bool, "mensaje": str}
    """
    try:
        import base64
        form = await request.form()
        telefono = form.get('telefono', '')
        imagen_file = form.get('imagen')
        caption = form.get('caption', '')

        if not telefono or not imagen_file:
            return {"exito": False, "mensaje": "Teléfono e imagen son requeridos"}

        imagen_bytes = await imagen_file.read()
        imagen_base64_raw = base64.b64encode(imagen_bytes).decode()

        # Detectar MIME type del nombre del archivo
        filename = imagen_file.filename.lower()
        if filename.endswith('.png'):
            mime_type = 'image/png'
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            mime_type = 'image/jpeg'
        elif filename.endswith('.gif'):
            mime_type = 'image/gif'
        elif filename.endswith('.webp'):
            mime_type = 'image/webp'
        else:
            mime_type = 'image/jpeg'  # default

        # Agregar prefijo data: para que el proveedor reconozca como base64 con MIME
        imagen_base64 = f"data:{mime_type};base64,{imagen_base64_raw}"

        exito = await proveedor.enviar_imagen(telefono, imagen_base64, caption)
        return {
            "exito": exito,
            "mensaje": "Imagen enviada" if exito else "Error al enviar imagen"
        }
    except Exception as e:
        logger.error(f"Error al enviar imagen: {e}", exc_info=True)
        return {"exito": False, "mensaje": str(e)}


@app.post("/api/admin/enviar-mensaje")
async def admin_enviar_mensaje(request: Request):
    """
    Envía un mensaje de texto a un cliente específico (sin imagen).
    Acepta: telefono (str), mensaje (str)

    Returns:
        {"exito": bool, "mensaje": str}
    """
    try:
        form = await request.form()
        telefono = form.get('telefono', '')
        mensaje_texto = form.get('mensaje', '')

        if not telefono or not mensaje_texto:
            return {"exito": False, "mensaje": "Teléfono y mensaje son requeridos"}

        exito = await proveedor.enviar_mensaje(telefono, mensaje_texto)
        return {
            "exito": exito,
            "mensaje": "Mensaje enviado" if exito else "Error al enviar mensaje"
        }
    except Exception as e:
        logger.error(f"Error en enviar_mensaje: {e}", exc_info=True)
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
    try:
        from agent.admin_api import obtener_clientes_importados, buscar_clientes_importados

        if q:
            # Búsqueda
            clientes = await buscar_clientes_importados(q)
            return {"clientes": clientes, "total": len(clientes), "pagina": 1, "total_paginas": 1}
        else:
            # Paginación
            resultado = await obtener_clientes_importados(pagina, por_pagina)
            return resultado
    except Exception as e:
        logger.error(f"Error en admin_clientes_importados: {e}", exc_info=True)
        return {"clientes": [], "total": 0, "pagina": pagina, "total_paginas": 0}


@app.post("/api/admin/tomar-control")
async def admin_tomar_control(telefono: str = ""):
    """
    Pausa el bot para un cliente específico — un humano toma control.

    Args:
        telefono: Número del cliente

    Returns:
        {"exito": bool, "mensaje": str}
    """
    if not telefono:
        return {"exito": False, "mensaje": "Teléfono requerido"}

    try:
        from agent.memory import tomar_control
        exito = await tomar_control(telefono)
        if exito:
            # Caché en memoria para respuesta rápida
            MUTED_CHATS.add(telefono)
            logger.info(f"✓ Bot pausado para {telefono} (en manos humanas)")
        return {
            "exito": exito,
            "mensaje": "Bot pausado - Humano en control" if exito else "No se pudo pausar"
        }
    except Exception as e:
        logger.error(f"Error pausando bot para {telefono}: {e}", exc_info=True)
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
    if not telefono:
        return {"exito": False, "mensaje": "Teléfono requerido"}

    try:
        from agent.memory import liberar_control
        exito = await liberar_control(telefono)
        if exito:
            # Remover de caché en memoria
            MUTED_CHATS.discard(telefono)
            logger.info(f"✓ Bot reactivado para {telefono} (bot en control)")
        return {
            "exito": exito,
            "mensaje": "Bot reactivado" if exito else "No se pudo reactivar"
        }
    except Exception as e:
        logger.error(f"Error reactivando bot para {telefono}: {e}", exc_info=True)
        return {"exito": False, "mensaje": str(e)}


@app.post("/api/admin/importar-excel")
async def admin_importar_excel(request: Request):
    """
    Importa clientes desde archivo Excel cargado.

    Returns:
        {"exitosos": int, "errores": int, "total": int, ...}
    """
    try:
        import tempfile
        from agent.excel_parser import cargar_clientes_desde_excel

        form = await request.form()
        archivo = form.get('archivo')
        if not archivo:
            return {"error": "Archivo requerido", "exitosos": 0, "errores": 0, "duplicados": 0}

        contenido = await archivo.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(contenido)
            tmp_path = tmp.name

        try:
            resultado = await cargar_clientes_desde_excel(tmp_path)
            return resultado
        finally:
            import os
            os.unlink(tmp_path)
    except Exception as e:
        logger.error(f"Error importando Excel: {e}", exc_info=True)
        return {"error": str(e), "exitosos": 0, "errores": 0, "duplicados": 0}


@app.post("/api/admin/importar-meta")
async def admin_importar_meta(request: Request):
    """
    Importa clientes desde exportación de Meta/Facebook.
    Acepta datos tab-separados en formato texto.

    Body (form-data):
        datos: texto con formato tab-separado
               o archivo .txt con la exportación

    Returns:
        {"exitosos": int, "errores": int, "duplicados": int, ...}
    """
    try:
        from agent.meta_parser import importar_desde_meta

        form = await request.form()

        # Aceptar datos como texto directo O como archivo
        datos_texto = form.get('datos', '')
        archivo = form.get('archivo')

        if isinstance(datos_texto, str):
            datos_texto = datos_texto.strip()

        # Si hay archivo, leer su contenido
        if archivo:
            contenido_archivo = await archivo.read()
            datos_texto = contenido_archivo.decode('utf-8').strip()

        if not datos_texto:
            return {
                "error": "Datos requeridos — ingresa datos tab-separados o carga un archivo",
                "exitosos": 0,
                "errores": 0,
                "duplicados": 0,
                "total": 0
            }

        # Procesar importación
        resultado = await importar_desde_meta(datos_texto)
        logger.info(f"Meta import result: {resultado}")
        return resultado

    except Exception as e:
        logger.error(f"Error importando datos Meta: {e}", exc_info=True)
        return {
            "error": str(e),
            "exitosos": 0,
            "errores": 0,
            "duplicados": 0,
            "total": 0
        }


@app.get("/api/admin/integridad")
async def admin_validar_integridad():
    """
    ✅ Valida la integridad referencial de la base de datos.

    Detecta:
    - Mensajes sin lead correspondiente
    - Pedidos sin lead
    - Satisfacciones sin pedido
    - Datos huérfanos

    Returns:
        {"valido": bool, "errores": [...], "timestamp": datetime}
    """
    try:
        resultado = await validar_integridad_referencial()
        status_code = 200 if resultado["valido"] else 206  # 206 Partial Content

        if resultado["valido"]:
            logger.info("✅ Validación de integridad: OK")
        else:
            logger.warning(f"⚠️ Problemas de integridad detectados: {resultado['errores']}")

        return resultado

    except Exception as e:
        logger.error(f"Error validando integridad: {e}", exc_info=True)
        return {
            "valido": False,
            "errores": [f"Error al validar: {str(e)}"],
            "timestamp": datetime.utcnow()
        }


@app.post("/api/admin/reparar-integridad")
async def admin_reparar_integridad():
    """
    ⚠️ EXPERIMENTAL: Intenta reparar problemas de integridad referencial.

    ADVERTENCIA: Esta operación puede modificar datos.
    Solo usar si se detectaron problemas de integridad.

    Returns:
        {"status": str, "accionesRealizadas": int, "errores": [...]}
    """
    try:
        # Validar primero
        estado_actual = await validar_integridad_referencial()
        if estado_actual["valido"]:
            return {
                "status": "ok",
                "accionesRealizadas": 0,
                "mensaje": "✅ Base de datos en estado íntegro, no hay nada que reparar"
            }

        # Si hay problemas, loguear para revisión manual
        logger.critical(f"⚠️ Reparación de integridad iniciada. Problemas: {estado_actual['errores']}")

        # Por ahora, solo reportar. La reparación manual es más segura.
        return {
            "status": "warning",
            "accionesRealizadas": 0,
            "errores": estado_actual["errores"],
            "mensaje": "Se detectaron problemas. Contacta al administrador para reparación manual."
        }

    except Exception as e:
        logger.error(f"Error reparando integridad: {e}", exc_info=True)
        return {
            "status": "error",
            "accionesRealizadas": 0,
            "errores": [str(e)]
        }


@app.get("/api/admin/errores")
async def admin_errores(horas: int = 24, limite: int = 50):
    """
    ✅ ANTI-ERROR-SILENCIOSO: Ver todos los errores de las últimas X horas.

    Args:
        horas: Cuántas horas atrás buscar (default: 24)
        limite: Máximo de registros (default: 50)

    Returns:
        Lista de errores registrados en auditoría
    """
    try:
        errores = await obtener_errores_recientes(horas=horas, limite=limite)

        return {
            "status": "ok",
            "total_errores": len(errores),
            "horas": horas,
            "errores": [
                {
                    "id": e.id,
                    "tabla": e.tabla,
                    "operacion": e.operacion,
                    "mensaje": e.mensaje_error[:200] if e.mensaje_error else "",
                    "timestamp": str(e.timestamp),
                    "usuario": e.usuario
                }
                for e in errores
            ]
        }

    except Exception as e:
        logger.error(f"Error obteniendo errores: {e}", exc_info=True)
        return {
            "status": "error",
            "total_errores": 0,
            "errores": [],
            "error_message": str(e)
        }


@app.get("/api/admin/auditoria/{tabla}")
async def admin_auditoria_tabla(tabla: str, horas: int = 24, limite: int = 100):
    """
    ✅ ANTI-ERROR-SILENCIOSO: Ver historial de cambios de una tabla.

    Args:
        tabla: Nombre de la tabla (leads, pedidos, mensajes, etc)
        horas: Cuántas horas atrás (default: 24)
        limite: Máximo de registros (default: 100)

    Returns:
        Historial de cambios auditados
    """
    try:
        registros = await obtener_historial_auditoria_tabla(tabla=tabla, horas=horas, limite=limite)

        return {
            "status": "ok",
            "tabla": tabla,
            "total_cambios": len(registros),
            "horas": horas,
            "cambios": [
                {
                    "id": r.id,
                    "operacion": r.operacion,
                    "registro_id": r.registro_id,
                    "usuario": r.usuario,
                    "razon": r.razon,
                    "error": r.error,
                    "timestamp": str(r.timestamp),
                    "datos_anteriores": r.datos_anteriores[:100] if r.datos_anteriores else None,
                    "datos_nuevos": r.datos_nuevos[:100] if r.datos_nuevos else None
                }
                for r in registros
            ]
        }

    except Exception as e:
        logger.error(f"Error obteniendo auditoría de {tabla}: {e}", exc_info=True)
        return {
            "status": "error",
            "tabla": tabla,
            "total_cambios": 0,
            "cambios": [],
            "error_message": str(e)
        }


@app.get("/api/admin/estadisticas-auditoria")
async def admin_estadisticas_auditoria():
    """
    ✅ ANTI-ERROR-SILENCIOSO: Estadísticas generales de auditoría.

    Retorna:
    - Total de operaciones registradas
    - Total de errores detectados
    - Tasa de error (%)
    - Breakdown por tabla y operación

    Returns:
        {"total_operaciones": int, "total_errores": int, "tasa_error": float, ...}
    """
    try:
        stats = await obtener_estadisticas_auditoria()

        return {
            "status": "ok",
            "estadisticas": stats,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de auditoría: {e}", exc_info=True)
        return {
            "status": "error",
            "estadisticas": {},
            "error_message": str(e)
        }


@app.post("/sync/imagenes")
async def sincronizar_imagenes():
    """
    Sincroniza las imágenes de productos desde Shopify API.
    Útil para re-sincronizar manualmente sin reiniciar el servidor.
    """
    try:
        from agent.shopify import sincronizar_imagenes_productos
        logger.info("📸 Sincronización manual de imágenes iniciada...")
        imagenes = await sincronizar_imagenes_productos()
        return {
            "status": "ok",
            "mensaje": f"✅ {len(imagenes)} imágenes sincronizadas desde Shopify",
            "total_productos": len(imagenes)
        }
    except Exception as e:
        logger.error(f"Error sincronizando imágenes: {e}")
        return {
            "status": "error",
            "mensaje": f"❌ Error en sincronización: {str(e)}"
        }
