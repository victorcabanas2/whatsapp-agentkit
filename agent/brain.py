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
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from agent.shopify import obtener_stock_producto, obtener_stocks_multiples, cargar_config_shopify

load_dotenv()
logger = logging.getLogger("agentkit")

# Cliente de Anthropic
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


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


def mapear_anuncio_a_producto(anuncio_id: str) -> str:
    """
    Mapea un ID de anuncio Meta a un producto conocido.

    Ejemplo: "theragun_mini_ad_campaign_april_2026" → "Theragun Mini 3.0"

    Args:
        anuncio_id: ID del anuncio de Meta

    Returns:
        Nombre del producto o el ID original si no se puede mapear
    """
    # Mapeo de IDs comunes a productos (este mapeo crece según los anuncios)
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
    }

    # Buscar coincidencias en el ID del anuncio
    anuncio_lower = anuncio_id.lower()
    for clave, producto in mapeos.items():
        if clave in anuncio_lower:
            logger.info(f"✓ Producto mapeado: {anuncio_id} → {producto}")
            return producto

    # Si no encuentra coincidencia, retornar el ID original (Claude lo interpretará)
    return anuncio_id


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

    for msg in historial[-10:]:
        msg_role = msg.get("role", "user")
        msg_content = msg.get("content", "")

        # Detectar si el contenido tiene imagen guardada ([IMG:...])
        if msg_content.startswith("[IMG:"):
            # Extraer URL de imagen
            try:
                end_img_tag = msg_content.find("]")
                if end_img_tag > 5:
                    img_url = msg_content[5:end_img_tag]  # Extraer entre [IMG: y ]
                    msg_text = msg_content[end_img_tag + 1:].strip()  # Resto del contenido

                    # Crear content block con imagen + texto
                    content = [
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": img_url
                            }
                        }
                    ]
                    if msg_text:
                        content.append({
                            "type": "text",
                            "text": msg_text
                        })

                    logger.debug(f"🖼️ Imagen extraída del historial: {img_url[:60]}...")
                    mensajes.append({
                        "role": msg_role,
                        "content": content
                    })
                else:
                    # Si el formato está mal, guardar como texto
                    mensajes.append({
                        "role": msg_role,
                        "content": msg_content
                    })
            except Exception as e:
                logger.warning(f"⚠️ Error extrayendo imagen del historial: {e}")
                mensajes.append({
                    "role": msg_role,
                    "content": msg_content
                })
        else:
            # Mensaje sin imagen, guardar como texto
            mensajes.append({
                "role": msg_role,
                "content": msg_content
            })

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

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=mensajes
        )

        # Extraer la respuesta
        respuesta = response.content[0].text

        # Log de uso
        logger.debug(
            f"✓ Respuesta generada | "
            f"Input: {response.usage.input_tokens} tokens | "
            f"Output: {response.usage.output_tokens} tokens"
        )

        return respuesta

    except Exception as e:
        logger.error(f"❌ Error en Claude API: {e}")
        return obtener_mensaje_error()
