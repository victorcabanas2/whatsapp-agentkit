# agent/ad_analyzer.py — Analizador de anuncios Meta inteligente
# Identifica productos desde anuncios con 3 capas en cascada

"""
Cuando un cliente llega desde un anuncio Meta (Facebook/Instagram Click-to-WhatsApp),
identifica automáticamente qué producto es usando:

1. Claude Vision — analiza la imagen del anuncio
2. Web scraping — extrae contenido de la URL del anuncio
3. Mapeo hardcoded — fallback con IDs conocidos

El resultado es una identificación robusta sin necesidad de configurar payloads en Meta.
"""

import os
import logging
import httpx
from anthropic import AsyncAnthropic
from bs4 import BeautifulSoup
from agent.brain import mapear_anuncio_a_producto
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


async def analizar_imagen_anuncio(imagen_url: str) -> str | None:
    """
    Usa Claude Vision para identificar qué producto es la imagen del anuncio.

    Args:
        imagen_url: URL de la imagen del anuncio

    Returns:
        Nombre del producto (ej: "TheraCup", "WHOOP PEAK", "FAO™ 211") o None
    """
    if not imagen_url:
        return None

    try:
        logger.debug(f"🔍 Analizando imagen del anuncio con Claude Vision: {imagen_url[:60]}...")

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "url", "url": imagen_url},
                        },
                        {
                            "type": "text",
                            "text": """Eres un experto en productos de bienestar y recuperación muscular (Therabody, WHOOP, FOREO, etc.).

Analiza esta imagen de anuncio de Facebook/Instagram y responde EXACTAMENTE con el nombre del producto.
No expliques. Solo el nombre del producto. Ejemplos: "TheraCup", "WHOOP PEAK", "FOREO FAQ™ 211", "Theragun Mini 3.0".

Si no puedes identificar un producto específico, responde: "DESCONOCIDO"
""",
                        },
                    ],
                }
            ],
        )

        producto = response.content[0].text.strip()

        if producto and producto != "DESCONOCIDO":
            logger.info(f"✓ Claude Vision identificó: {producto}")
            return producto
        else:
            logger.debug("⚠️ Claude Vision no pudo identificar el producto")
            return None

    except Exception as e:
        logger.warning(f"⚠️ Error analizando imagen con Claude Vision: {e}")
        return None


async def scrapear_url(url: str) -> str:
    """
    Hace GET async a la URL del anuncio y retorna el contenido HTML.

    Args:
        url: URL del anuncio en Facebook o rebody.com.py

    Returns:
        Contenido HTML (primeros 5000 caracteres) o string vacío si falla
    """
    if not url:
        return ""

    try:
        logger.debug(f"📄 Scrapeando URL: {url[:60]}...")

        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RebodyBot/1.0)"},
        ) as client_http:
            response = await client_http.get(url)
            response.raise_for_status()

            html = response.text[:5000]  # Limitar a 5000 caracteres para economizar tokens
            logger.debug(f"✓ Obtenido {len(response.text)} caracteres de {url}")
            return html

    except Exception as e:
        logger.warning(f"⚠️ Error scrapeando {url}: {e}")
        return ""


async def analizar_contenido_web(html: str) -> str | None:
    """
    Usa Claude para extraer el nombre del producto del contenido HTML.

    Args:
        html: Contenido HTML de la URL del anuncio

    Returns:
        Nombre del producto o None
    """
    if not html or len(html) < 50:
        return None

    try:
        logger.debug("🔍 Analizando contenido web con Claude...")

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analiza este HTML de un anuncio/página web y extrae el nombre exacto del producto que se vende.

HTML:
{html}

Responde SOLO con el nombre del producto. Ejemplos: "TheraCup", "WHOOP PEAK", "FOREO FAQ™ 211", "Theragun Mini 3.0".
Si no encuentras un producto específico, responde: "DESCONOCIDO"
""",
                }
            ],
        )

        producto = response.content[0].text.strip()

        if producto and producto != "DESCONOCIDO":
            logger.info(f"✓ Análisis web identificó: {producto}")
            return producto
        else:
            logger.debug("⚠️ No se pudo identificar producto del contenido web")
            return None

    except Exception as e:
        logger.warning(f"⚠️ Error analizando contenido web: {e}")
        return None


async def identificar_producto_desde_anuncio(
    imagen_url: str | None = None,
    ad_url: str | None = None,
    payload: str | None = None,
) -> str | None:
    """
    Identifica el producto desde un anuncio usando 3 capas en cascada.

    Orden de prioridad:
    1. Analizar imagen del anuncio (Claude Vision) — más confiable
    2. Scrapear y analizar URL del anuncio (httpx + Claude)
    3. Mapeo hardcoded usando payload/ID (fallback)

    Args:
        imagen_url: URL de la imagen del anuncio
        ad_url: URL del anuncio en Facebook o página de producto
        payload: ID o string del anuncio (para mapeo hardcoded)

    Returns:
        Nombre del producto identificado o None si no se puede identificar
    """

    # ═══════════════════════════════════════════════════════════
    # CAPA 1 — Claude Vision (imagen del anuncio)
    # ═══════════════════════════════════════════════════════════

    if imagen_url:
        logger.info(f"📸 Capa 1: Intentando identificar desde imagen...")
        producto = await analizar_imagen_anuncio(imagen_url)
        if producto:
            return producto

    # ═══════════════════════════════════════════════════════════
    # CAPA 2 — Web scraping + Claude (URL del anuncio)
    # ═══════════════════════════════════════════════════════════

    if ad_url:
        logger.info(f"📄 Capa 2: Intentando identificar desde URL...")
        html = await scrapear_url(ad_url)
        if html:
            producto = await analizar_contenido_web(html)
            if producto:
                return producto

    # ═══════════════════════════════════════════════════════════
    # CAPA 3 — Mapeo hardcoded (fallback)
    # ═══════════════════════════════════════════════════════════

    if payload:
        logger.info(f"🔖 Capa 3: Intentando mapeo hardcoded de payload...")
        producto = mapear_anuncio_a_producto(payload)
        if producto and producto != payload:  # Si mapear_anuncio_a_producto encontró algo
            logger.info(f"✓ Mapeo hardcoded identificó: {producto}")
            return producto

    logger.warning("⚠️ No se pudo identificar el producto desde el anuncio")
    return None
