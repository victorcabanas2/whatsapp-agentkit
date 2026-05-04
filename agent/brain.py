# agent/brain.py — Cerebro del agente: conexión con Claude API
# Generado por AgentKit

"""
Lógica de IA del agente Belén.
Lee el system prompt de prompts.yaml y genera respuestas usando Claude API.
"""

import os
import json
import yaml
import logging
import re
from datetime import datetime, timedelta
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from agent.shopify import obtener_stock_producto, obtener_stocks_multiples, cargar_config_shopify
from agent.memory import programar_seguimiento_dinamico
from agent.web_search import scrape_specs

load_dotenv()
logger = logging.getLogger("agentkit")

# Cliente de Anthropic
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Herramienta de búsqueda de specs en sitios oficiales
_TOOL_WEB = [{
    "name": "buscar_specs_producto",
    "description": (
        "Busca especificaciones técnicas en el sitio oficial de la marca (therabody.com, whoop.com, foreo.com). "
        "Usar solo para detalles técnicos (modos, temperaturas, materiales, dimensiones, batería) "
        "no documentados en el prompt. Nunca para precios, stock ni garantías."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL del producto en therabody.com, whoop.com o foreo.com"
            }
        },
        "required": ["url"]
    }
}]

# Keywords que indican pregunta técnica — solo en estos casos se pasa el tool a Claude
_KEYWORDS_SPECS = {
    "como funciona", "cómo funciona", "que hace", "qué hace",
    "para que sirve", "para qué sirve", "como se usa", "cómo se usa",
    "especificaciones", "especificacion", "caracteristicas", "características",
    "modos", "temperatura", "bateria", "batería", "autonomia", "autonomía",
    "dimensiones", "medidas", "peso", "tamaño", "tamano",
    "compatible", "compatibilidad", "materiales", "material",
    "diferencia entre", "diferencias", "que incluye", "qué incluye",
    "frecuencia", "intensidad", "niveles", "ajustes", "configuracion",
    "detalles tecnicos", "detalles técnicos", "specs", "ficha tecnica",
    "waterproof", "resistente", "agua", "ip68", "ip67",
    "sensores", "sensor", "algoritmo", "precision", "precisión",
}


def _necesita_tool_web(mensaje: str) -> bool:
    """Retorna True solo si el mensaje contiene una pregunta técnica sobre specs."""
    msg = mensaje.lower()
    return any(kw in msg for kw in _KEYWORDS_SPECS)


def cargar_config_prompts() -> dict:
    """Lee la configuración completa desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config or {}
    except FileNotFoundError:
        logger.error("❌ config/prompts.yaml no encontrado")
        return {}
    except Exception as e:
        logger.error(f"❌ Error al leer prompts.yaml: {e}")
        return {}


def cargar_stock_actual() -> str:
    """Lee el stock actual del archivo JSON y lo formatea para el prompt."""
    try:
        with open("knowledge/stock_actual.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        stock_texto = "\n  STOCK ACTUAL (EN VIVO, actualizado automáticamente):\n"

        for producto in data.get("productos", {}).values():
            nombre = producto.get("nombre", "Desconocido")
            stock = producto.get("stock", 0)
            disponible = producto.get("disponible", False)

            if disponible:
                stock_texto += f"  {nombre}: {stock} unidades ✅\n"
            else:
                stock_texto += f"  {nombre}: AGOTADO ❌\n"

        return stock_texto
    except Exception as e:
        logger.warning(f"Error leyendo stock: {e}")
        return ""


def cargar_system_prompt() -> str:
    """Retorna el system prompt desde config/prompts.yaml + stock dinámico."""
    config = cargar_config_prompts()
    prompt = config.get("system_prompt", "Eres un asistente útil. Responde en español.")

    # Agregar stock actual dinámico
    stock_dinamico = cargar_stock_actual()
    if stock_dinamico:
        prompt = prompt.replace(
            "STOCK ACTUAL (actualizado cada 5 minutos):",
            stock_dinamico.strip()
        )

    logger.debug(f"✓ Prompt cargado con stock en vivo")
    return prompt


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado."""
    config = cargar_config_prompts()
    mensajes = config.get("fallback_message", {})
    if isinstance(mensajes, dict):
        return mensajes.get("error_message", "Lo siento, estoy teniendo problemas técnicos.")
    return "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos."


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback para entradas inválidas."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


def _cargar_ads_yaml() -> dict:
    """Carga el mapa de anuncios desde config/ads.yaml."""
    try:
        with open("config/ads.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("ad_products", {})
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"⚠️ Error cargando ads.yaml: {e}")
        return {}


def mapear_anuncio_a_producto(anuncio_id: str) -> str:
    """
    Mapea un ID o título de anuncio Meta a un producto conocido.

    Orden de búsqueda:
    1. config/ads.yaml — mapping exacto configurado por Victor
    2. Keywords hardcoded — matching por palabras clave en el texto

    Args:
        anuncio_id: ID numérico de Meta, título del anuncio, o cualquier texto del anuncio

    Returns:
        Nombre del producto o el ID original si no se puede mapear
    """
    # PASO 1: Buscar en ads.yaml (exact match primero, luego substring)
    ads_map = _cargar_ads_yaml()
    if ads_map:
        anuncio_lower = anuncio_id.lower()
        # Exact match
        if anuncio_id in ads_map:
            producto = ads_map[anuncio_id]
            logger.info(f"✓ Producto desde ads.yaml (exacto): {anuncio_id} → {producto}")
            return producto
        # Substring match (el ID del anuncio puede aparecer dentro del texto del headline)
        for ad_key, producto in ads_map.items():
            if ad_key.lower() in anuncio_lower or anuncio_lower in ad_key.lower():
                logger.info(f"✓ Producto desde ads.yaml (substring): {anuncio_id} → {producto}")
                return producto

    # PASO 2: Keywords hardcoded — funciona con títulos de anuncios y variaciones
    # Incluye múltiples variaciones para cada producto
    mapeos = {
        # Therabody — Theragun (percutor)
        "theragun_mini": "Theragun Mini 3.0",
        "theragun": "Theragun Mini 3.0",
        "theragun_pro_plus": "Theragun PRO Plus",
        "theragun_pro": "Theragun PRO Plus",

        # Therabody — TheraCup
        "theracup": "TheraCup",
        "thera_cup": "TheraCup",

        # Therabody — WaveSolo
        "wavesolo": "WaveSolo",
        "wave_solo": "WaveSolo",

        # Therabody — JetBoots
        "jetboots_prime": "JetBoots Prime",
        "jetboots_prime": "JetBoots Prime",
        "jetboots_pro_plus": "JetBoots Pro Plus",
        "jetboots_pro": "JetBoots Pro Plus",
        "jetboots": "JetBoots Prime",

        # Therabody — TheraFace
        "theraface_pro": "TheraFace PRO",
        "theraface_mask": "TheraFace Mask",
        "theraface_depuffing": "TheraFace Depuffing Wand",
        "depuffing_wand": "TheraFace Depuffing Wand",
        "depuffing": "TheraFace Depuffing Wand",
        "theraface": "TheraFace PRO",

        # Therabody — SmartGoggles
        "smartgoggles": "SmartGoggles 2.0",
        "smart_goggles": "SmartGoggles 2.0",

        # WHOOP
        "whoop_one": "WHOOP ONE 5.0",
        "whoop_peak": "WHOOP PEAK 5.0",
        "whoop_life": "WHOOP LIFE MG",
        "whoop": "WHOOP ONE 5.0",

        # FOREO
        "foreo_faq_211": "FOREO FAQ™ 211 (Cuello)",
        "foreo_faq": "FOREO FAQ™ 211 (Cuello)",
        "faq_211": "FOREO FAQ™ 211 (Cuello)",
        "faq211": "FOREO FAQ™ 211 (Cuello)",
        "foreo_faq_221": "FOREO FAQ™ 221 (Manos)",
        "faq_221": "FOREO FAQ™ 221 (Manos)",
        "faq221": "FOREO FAQ™ 221 (Manos)",
        "foreo": "FOREO FAQ™ 211 (Cuello)",

        # ThermBack LED — clientes lo llaman "faja", "masajeador de espalda"
        "thermback": "ThermBack LED",
        "therm_back": "ThermBack LED",
        "faja": "ThermBack LED",
        "faja lumbar": "ThermBack LED",
        "masajeador de espalda": "ThermBack LED",
        "masajeador lumbar": "ThermBack LED",
        "espalda led": "ThermBack LED",
        "lumbar": "ThermBack LED",

        # SleepMask
        "sleepmask": "SleepMask",
        "sleep mask": "SleepMask",
        "antifaz": "SleepMask",

        # RecoveryPulse
        "recoverypulse": "RecoveryPulse Calf Sleeve",
        "recovery pulse": "RecoveryPulse Calf Sleeve",
        "manga compresion": "RecoveryPulse Calf Sleeve",
        "manga de compresion": "RecoveryPulse Calf Sleeve",

        # TheraCup
        "theracup": "TheraCup",
        "ventosa": "TheraCup",
    }

    # Buscar coincidencias en el ID del anuncio
    anuncio_lower = anuncio_id.lower()
    for clave, producto in mapeos.items():
        if clave in anuncio_lower:
            logger.info(f"✓ Producto mapeado: {anuncio_id} → {producto}")
            return producto

    # Si no encuentra coincidencia, retornar el ID original (Claude lo interpretará)
    return anuncio_id


async def detectar_y_programar_seguimiento(
    mensaje_usuario: str,
    respuesta_belén: str,
    telefono: str,
    nombre_cliente: str = None
) -> str:
    """
    Detecta si el usuario pidió un seguimiento dinámico ("escríbeme en 4 minutos").
    Si lo detecta, programa automáticamente el seguimiento y modifica la respuesta.

    Args:
        mensaje_usuario: El mensaje del usuario
        respuesta_belén: La respuesta que generó Belén
        telefono: Número de teléfono del cliente
        nombre_cliente: Nombre del cliente (si se conoce)

    Returns:
        La respuesta de Belén, potencialmente modificada para aclarar que se va a contactar
    """
    try:
        # Palabras clave para detectar solicitud de seguimiento
        palabras_clave = [
            # Escribir/Contactar
            "escríbeme",
            "escribeme",
            "escribí",
            "escribi",
            "me escribís",
            "me escribes",
            "me escriba",

            # Recordar/Avisar
            "recordás",
            "recordas",
            "recordá",
            "recuerda",
            "recordame",
            "me recordas",
            "me recordás",
            "me recuerda",
            "acuerda",

            # Avisar/Contactar
            "me avisa",
            "avisame",
            "avísame",
            "contáctate",
            "contactate",
            "contáctame",
            "contactame",

            # Otros
            "vuelve a escribir",
            "vuelvo",
            "llámame",
            "llamame",
        ]

        # Patrones para detectar tiempo (minutos, horas, etc)
        # Matches: "en 4 minutos", "en 2 horas", "en media hora", "dentro de 30 minutos", etc
        patron_tiempo = r'en\s+(?:(\d+)\s*(minuto|hora|segundo|seg|min|h|hora)s?|media\s+hora|un\s+minuto|una\s+hora)'

        mensaje_lower = mensaje_usuario.lower().strip()
        respuesta_lower = respuesta_belén.lower().strip()

        # Buscar si el usuario pidió un seguimiento
        tiene_palabra_clave = any(palabra in mensaje_lower for palabra in palabras_clave)

        if not tiene_palabra_clave:
            return respuesta_belén  # No hay solicitud de seguimiento

        # Si tiene palabra clave, buscar el tiempo
        match_tiempo = re.search(patron_tiempo, mensaje_lower)

        if not match_tiempo:
            # Tiene palabra clave pero no especifica tiempo exactamente
            # Dejar que Belén maneje la respuesta (podría ser "escríbeme cuando puedas")
            return respuesta_belén

        # Extraer cantidad de tiempo
        cantidad_str = match_tiempo.group(1)
        unidad = match_tiempo.group(2).lower() if match_tiempo.group(2) else "minuto"

        try:
            cantidad = int(cantidad_str) if cantidad_str else 1

            # Convertir a minutos
            if "hora" in unidad or unidad == "h":
                minutos = cantidad * 60
            elif "segundo" in unidad or unidad in ["seg", "s"]:
                minutos = max(1, cantidad // 60)  # Mínimo 1 minuto
            else:  # minuto, min
                minutos = max(1, cantidad)

            # Calcular cuándo enviar
            momento_programado = datetime.utcnow() + timedelta(minutes=minutos)

            logger.info(f"📅 Detectado pedido de seguimiento en {minutos} minutos para {telefono}")

            # Programar el seguimiento
            exito = await programar_seguimiento_dinamico(
                telefono=telefono,
                momento_programado=momento_programado,
                nombre=nombre_cliente,
                contexto={
                    "tipo": "seguimiento_dinamico_cliente",
                    "minutos_solicitados": minutos,
                    "momento_solicitado_en": match_tiempo.group(0),
                    "respuesta_belén_original": respuesta_belén[:100]  # Primeros 100 chars
                }
            )

            if exito:
                logger.info(f"✅ Seguimiento programado exitosamente para {telefono} en {minutos} minutos")
                # Modificar la respuesta para confirmar explícitamente
                # El cliente NECESITA saber que se guardó
                palabra_tiempo = "minuto" if minutos == 1 else "minutos"
                respuesta_modificada = respuesta_belén + f"\n\n✅ Dale, te escribo en {minutos} {palabra_tiempo}. Ya queda anotado 💙"
                return respuesta_modificada
            else:
                logger.error(f"❌ FALLO AL PROGRAMAR SEGUIMIENTO para {telefono}")
                logger.warning(f"⚠️ No se pudo programar seguimiento. Retornando respuesta original.")
                return respuesta_belén

        except (ValueError, AttributeError) as e:
            logger.warning(f"Error parsing tiempo: {e}")
            return respuesta_belén

    except Exception as e:
        logger.error(f"Error en detectar_y_programar_seguimiento: {e}")
        return respuesta_belén  # Retornar respuesta original si hay error


def detectar_confirmacion_pago(mensaje: str) -> bool:
    """
    Detecta si el mensaje es una confirmación de pago.
    Busca palabras clave como: "confirmo", "confirmé", "hice", "transferí", "pagué", etc.

    Args:
        mensaje: El mensaje del usuario

    Returns:
        True si detecta confirmación, False en caso contrario
    """
    palabras_confirmacion = [
        "confirmo",
        "confirmé",
        "confirmado",
        "hice",
        "hice la",
        "transferí",
        "transferencia",
        "pagué",
        "pagado",
        "pague",
        "ya transferí",
        "ya hice",
        "ya pagué",
        "listo",
        "hecho",
        "adelante",
        "ok",
        "okey",
        "dale",
        "si",
        "sí",
        "efectivamente",
        "claro",
    ]

    mensaje_lower = mensaje.lower().strip()

    # Buscar cualquiera de las palabras clave
    for palabra in palabras_confirmacion:
        if palabra in mensaje_lower:
            logger.debug(f"Detectada confirmación de pago: '{palabra}' en mensaje: {mensaje}")
            return True

    return False


async def obtener_contexto_stock() -> str:
    """
    Consulta stocks en Shopify de los 5 productos más populares.
    Retorna un string con el estado de stock para agregar al system prompt.

    NOTA: Temporalmente desactivado por token inválido.
    Descomentar cuando tengas credenciales válidas.
    """
    return ""  # Desactivado por ahora

    # Código original (comentado):
    config = cargar_config_shopify()
    products = config.get("products", {})

    # Productos top para consultar (más vendidos)
    top_productos = [
        "theragun_mini",
        "theragun_pro_plus",
        "theraface_depuffing_wand",
        "jetboots_prime",
        "whoop_peak",
    ]

    stocks = {}
    for nombre in top_productos:
        if nombre in products:
            product_info = products[nombre]
            shopify_id = product_info.get("shopify_id")
            nombre_display = product_info.get("nombre", nombre)

            try:
                stock = await obtener_stock_producto(shopify_id)
                if stock is not None:
                    stocks[nombre_display] = stock
            except Exception as e:
                logger.warning(f"⚠️ Error consultando stock de {nombre}: {e}")

    # Formatear para agregar al prompt
    if stocks:
        stock_info = "**Stock disponible (actualizado):**\n"
        for producto, cantidad in stocks.items():
            stock_info += f"- {producto}: {cantidad} unidades\n"
        return stock_info
    else:
        return ""


# Palabras de producto — si aparecen, la pregunta no es una FAQ simple
_PALABRAS_PRODUCTO = {
    "whoop", "theragun", "jetboots", "foreo", "theraface", "wavesolo",
    "smartgoggles", "sleepmas", "thermback", "theracup", "recovery",
    "wand", "mask", "goggles", "mini", "sense", "prime",
}


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin puntuación."""
    t = texto.lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ü","u"),("ñ","n")]:
        t = t.replace(a, b)
    return "".join(c if c.isalnum() or c == " " else " " for c in t)


def _detectar_faq(mensaje: str) -> str | None:
    """
    Detecta FAQs de primer contacto y retorna respuesta pre-escrita.
    Solo para mensajes cortos sin mención de productos específicos.
    """
    norm = _normalizar(mensaje)
    words = set(norm.split())

    # Si menciona un producto específico, Claude lo maneja mejor
    if words & _PALABRAS_PRODUCTO:
        return None

    # Delivery
    if "delivery" in words or ("hacen" in words and "envio" in words) or ("mandan" in words):
        return "¡Sí hacemos delivery! 😊 Para coordinar necesito: nombre, dirección y nro de contacto. ¿Lo armamos?"

    # Dirección / local
    if (("donde" in words or "ubican" in words or "ubicacion" in words) and ("estan" in words or "esta" in words)) \
            or ("direccion" in words and len(words) <= 5) \
            or ({"tienen", "local"} <= words and len(words) <= 6):
        return "Estamos en Dr. Luis Morquio 447 (Solumedic S.A.), Asunción — barrio Pinoza, cerca del Shopping Asia 📍"

    # Datos bancarios / transferencia
    if ("datos" in words or "cuenta" in words) and ("transferencia" in words or "banco" in words or "pago" in words):
        return "Cuenta: 6192826751 | Banco UENO | RUC: 80023913-0 | Empresa: SOLUMEDIC S.A. 💳"

    # Cuotas
    if "cuotas" in words and len(words) <= 8:
        return "¡Sí! UENO: 12 cuotas sin interés, Banco Familiar: 12 cuotas sin interés, Banco Itaú: 6 cuotas sin interés 😊 ¿Con qué banco pagás?"

    return None


async def generar_respuesta(
    mensaje: str,
    historial: list[dict],
    imagen_url: str | None = None,
    contexto_adicional: str | None = None
) -> str:
    """
    Genera una respuesta usando Claude API.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]
        imagen_url: URL de imagen si el usuario envió una imagen
        contexto_adicional: Contexto extra para situaciones especiales (anuncios, replies, etc)

    Returns:
        La respuesta generada por Claude
    """
    # Validar entrada
    if (not mensaje or len(mensaje.strip()) < 2) and not imagen_url:
        return obtener_mensaje_fallback()

    # Saludos simples sin historial: respuesta pre-escrita sin llamar a Claude
    # Solo aplica en primer contacto (sin historial) — con historial Claude necesita contexto
    SALUDOS = {"hola", "holis", "hi", "hey", "buenas", "buen dia", "buen día",
               "buenos dias", "buenos días", "buenas tardes", "buenas noches", "hello", "ola"}
    mensaje_lower = mensaje.strip().lower().rstrip("!.?,")
    if not historial and not imagen_url and not contexto_adicional and mensaje_lower in SALUDOS:
        logger.info(f"⚡ Saludo sin historial — respuesta pre-escrita (sin llamar a Claude)")
        return "Hola, soy Belén, la agente de Rebody 😊 ¿En qué te puedo ayudar?"

    # FAQs de primer contacto: respuestas pre-escritas para preguntas frecuentes muy simples
    # Solo aplica cuando: sin historial, sin imagen, sin contexto de anuncio, mensaje corto
    if not historial and not imagen_url and not contexto_adicional and len(mensaje) < 80:
        faq = _detectar_faq(mensaje)
        if faq:
            logger.info(f"⚡ FAQ detectada — respuesta pre-escrita (sin llamar a Claude)")
            return faq

    # Cargar system prompt
    system_prompt = cargar_system_prompt()
    if not system_prompt:
        logger.error("❌ No se pudo cargar el system prompt")
        return obtener_mensaje_error()

    # Si hay contexto adicional (anuncio, reply, etc), agregarlo al system prompt
    if contexto_adicional:
        system_prompt += f"\n\n═══════════════════════════════════════════\n"
        system_prompt += f"📌 CONTEXTO ESPECIAL PARA ESTA RESPUESTA:\n"
        system_prompt += f"{contexto_adicional}\n"
        system_prompt += f"═══════════════════════════════════════════\n"
        logger.info(f"📌 Contexto adicional agregado al prompt")

    # Agregar contexto de stock al system prompt
    try:
        contexto_stock = await obtener_contexto_stock()
        if contexto_stock:
            system_prompt += f"\n\n{contexto_stock}"
    except Exception as e:
        logger.warning(f"⚠️ Error obteniendo contexto de stock: {e}")
        # Continuar sin stock info si falla

    # Construir mensajes para la API
    mensajes = []

    # ═══════════════════════════════════════════════════════════
    # PROCESAR HISTORIAL — Extraer imágenes si existen
    # ═══════════════════════════════════════════════════════════

    for msg in historial[-8:]:
        msg_role = msg.get("role", "user")
        msg_content = msg.get("content", "")

        # Imágenes en el historial: reemplazar con placeholder de texto
        # Re-enviar la imagen completa cuesta 1,000-3,000 tokens por mensaje — Belén ya la procesó antes
        if msg_content.startswith("[IMG:"):
            end_img_tag = msg_content.find("]")
            msg_text = msg_content[end_img_tag + 1:].strip() if end_img_tag > 5 else ""
            placeholder = "[imagen enviada anteriormente]"
            if msg_text:
                placeholder += f" {msg_text}"
            mensajes.append({"role": msg_role, "content": placeholder})
        else:
            mensajes.append({"role": msg_role, "content": msg_content})

    # ═══════════════════════════════════════════════════════════
    # PROCESAR MENSAJE ACTUAL
    # ═══════════════════════════════════════════════════════════

    if imagen_url:
        # Si hay imagen, crear un content block con imagen + texto
        content = [
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": imagen_url
                }
            }
        ]
        # Agregar el texto del mensaje si existe
        if mensaje and mensaje.strip():
            content.append({
                "type": "text",
                "text": mensaje
            })
        else:
            # Si no hay texto, pedir que identifique el producto
            content.append({
                "type": "text",
                "text": "¿Qué producto es este? Identifica y dame todos los detalles."
            })

        logger.info(f"📸 Imagen actual detectada: {imagen_url[:60]}...")
    else:
        # Solo texto
        content = mensaje

    # Agregar el mensaje actual
    mensajes.append({
        "role": "user",
        "content": content
    })

    try:
        logger.debug(f"Llamando a Claude con {len(mensajes)} mensajes en contexto (imagen: {'sí' if imagen_url else 'no'})")

        sistema = [{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }]

        usar_tool = _necesita_tool_web(mensaje)
        kwargs = {"tools": _TOOL_WEB} if usar_tool else {}

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=sistema,
            messages=mensajes,
            **kwargs
        )

        # Manejar tool use si Claude solicita buscar specs en la web
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use" and block.name == "buscar_specs_producto":
                    url = block.input.get("url", "")
                    logger.info(f"🔍 Buscando specs en: {url[:70]}")
                    resultado = await scrape_specs(url)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": resultado
                    })

            if tool_results:
                mensajes.append({"role": "assistant", "content": response.content})
                mensajes.append({"role": "user", "content": tool_results})

                response = await client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=sistema,
                    messages=mensajes,
                    **kwargs
                )

        # Extraer texto de la respuesta
        respuesta = ""
        for block in response.content:
            if hasattr(block, "text"):
                respuesta = block.text
                break

        if not respuesta:
            return obtener_mensaje_error()

        # Log de uso con info de caché
        cache_hit = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
        cache_write = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
        logger.info(
            f"✓ Tokens | in:{response.usage.input_tokens} out:{response.usage.output_tokens} "
            f"cache_hit:{cache_hit} cache_write:{cache_write}"
        )

        return respuesta

    except Exception as e:
        logger.error(f"❌ Error en Claude API: {e}")
        return obtener_mensaje_error()


def extraer_imagen_de_respuesta(respuesta: str) -> tuple[str, str | None]:
    """
    Extrae el marcador [IMAGEN:product_id] de la respuesta de Claude si existe.
    Retorna el texto limpio (sin el marcador) y el product_id si se encontró.

    Args:
        respuesta: La respuesta completa de Claude

    Returns:
        Tupla (texto_limpio, product_id_o_None)

    Ejemplo:
        Input: "Mirá el Theragun Mini 3.0... [IMAGEN:9146847002882]"
        Output: ("Mirá el Theragun Mini 3.0...", "9146847002882")
    """
    import re

    # Buscar el patrón [IMAGEN:...] en la respuesta
    match = re.search(r'\[IMAGEN:([^\]]+)\]', respuesta)

    if match:
        product_id = match.group(1).strip()

        # Extraer el texto limpio (sin el marcador)
        texto_limpio = respuesta[:match.start()].strip() + " " + respuesta[match.end():].strip()
        texto_limpio = texto_limpio.strip()

        logger.debug(f"🖼️ Marcador de imagen detectado: product_id={product_id}")
        return texto_limpio, product_id

    # No hay marcador de imagen
    return respuesta, None


async def generar_mensaje_seguimiento_contextual(
    lead,
    historial: list[dict],
    tipo_seguimiento: str = "seguimiento"
) -> str | None:
    """
    Lee el historial de conversación y genera un follow-up personalizado con IA.

    Analiza el contexto real de la conversación para decidir:
    - SI enviar (hay oportunidad de venta pendiente)
    - QUÉ decir (referenciando lo que realmente se habló)

    Returns:
        str — mensaje personalizado a enviar
        None — NO enviar (cliente en lista de espera, ya resolvió, dijo que no, etc.)
    """
    import json

    if not historial and not lead.anuncio_producto:
        return None

    historial_texto = ""
    for msg in historial[-8:]:
        rol = "Cliente" if msg["role"] == "user" else "Belén (bot)"
        historial_texto += f"{rol}: {msg['content']}\n\n"

    if not historial_texto:
        historial_texto = "(Sin mensajes previos registrados en el sistema)"

    descripciones_tipo = {
        "seguimiento_1": "primer seguimiento (3+ horas después del primer mensaje del cliente)",
        "seguimiento_2": "segundo seguimiento (lead no respondió al primero, ~20-24hs después)",
        "seguimiento_3": "tercer y último seguimiento (último intento antes de cerrar el lead)",
        "mismo_dia": "primer seguimiento (3-48hs después del contacto inicial)",
        "1dia": "segundo seguimiento (día siguiente sin respuesta del cliente)",
        "3dias": "tercer contacto (3 días sin respuesta)",
        "domingo": "seguimiento dominical especial",
        "pendiente": "recuperar conversación que nunca recibió seguimiento",
    }
    desc_tipo = descripciones_tipo.get(tipo_seguimiento, tipo_seguimiento)

    user_content = f"""Analiza esta conversación de ventas y decide si enviar un mensaje de seguimiento.

TIPO: {desc_tipo}
CLIENTE: {lead.nombre or "Sin nombre"} | PRODUCTO ANUNCIO: {lead.anuncio_producto or "No identificado"}

CONVERSACIÓN:
{historial_texto}

Responde SOLO con JSON válido (sin bloques de código, sin texto extra):
Si SÍ: {{"enviar": true, "razon": "motivo breve", "mensaje": "texto del mensaje"}}
Si NO: {{"enviar": false, "razon": "motivo breve", "mensaje": null}}

══════════════════════════════════════════════════
REGLA PRINCIPAL — ¿Se estableció una acción concreta entre las partes?

NO ENVIAR si cualquiera de estos aplica:
• Nosotros prometimos contactarlos: lista de espera, avisar cuando llegue stock, consultar y volver a escribir
• El cliente dijo que él/ella nos avisa cuando decida ("te aviso", "yo te escribo", "te contacto")
• El cliente dijo explícitamente que no quiere comprar o no le interesa
• El cliente ya compró

SÍ ENVIAR si ninguno de los anteriores aplica:
• No respondió nada desde el primer mensaje
• Respuesta vaga: "gracias", "voy a revisar", "lo pienso", "quizás", "después veo"
• Mostró interés, preguntó precio/stock, pero nunca tomó ninguna acción concreta
══════════════════════════════════════════════════

REGLAS DEL MENSAJE (solo si enviar=true):
- SIEMPRE empezar con: "Hola, ¿qué tal?" seguido del mensaje
- Menciona el PRODUCTO O TEMA EXACTO que se habló (nunca genérico)
- Máximo 3 oraciones, una sola pregunta o CTA al final
- Tono cálido, no presionante
- Español paraguayo (tuteo), sin "che" """

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system="Eres un analizador de conversaciones de ventas. Responde SOLO con JSON válido, sin explicaciones, sin bloques de código.",
            messages=[{"role": "user", "content": user_content}]
        )

        texto = response.content[0].text.strip()

        # Limpiar posibles wrappers de bloque de código
        if "```" in texto:
            start = texto.find("{")
            end = texto.rfind("}") + 1
            if start >= 0 and end > start:
                texto = texto[start:end]

        data = json.loads(texto)

        if not data.get("enviar", False):
            logger.info(f"🚫 Seguimiento omitido [{tipo_seguimiento}] para {lead.telefono}: {data.get('razon', 'sin razón')}")
            return None

        mensaje = data.get("mensaje")
        if mensaje:
            logger.info(f"✅ Seguimiento contextual generado [{tipo_seguimiento}] para {lead.telefono}: {data.get('razon', '')}")
            return str(mensaje)

        return None

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ JSON inválido en seguimiento contextual para {lead.telefono}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error generando seguimiento contextual para {lead.telefono}: {e}")
        return None


def obtener_url_imagen(product_id: str) -> str | None:
    """
    Obtiene la URL de imagen de un producto desde el catálogo local.
    Usa el archivo knowledge/imagenes_productos.json generado por shopify.py.

    Args:
        product_id: ID del producto en Shopify (string numérico)

    Returns:
        URL de la imagen, o None si no existe

    Nota:
        Esta es una función wrapper que delega a shopify.obtener_url_imagen_producto()
    """
    from agent.shopify import obtener_url_imagen_producto

    return obtener_url_imagen_producto(product_id)
