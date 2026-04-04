# agent/shopify.py — Integración con Shopify para consultar stock
# Lee stock en tiempo real de la tienda Shopify

import os
import yaml
import logging
import httpx
from datetime import datetime, timedelta
from functools import lru_cache

logger = logging.getLogger("agentkit")

# Caché en memoria: { product_id: (stock, timestamp) }
_stock_cache = {}


def cargar_config_shopify() -> dict:
    """Lee la configuración de Shopify desde config/shopify.yaml."""
    try:
        with open("config/shopify.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("❌ config/shopify.yaml no encontrado")
        return {}
    except Exception as e:
        logger.error(f"❌ Error al leer shopify.yaml: {e}")
        return {}


def obtener_credenciales_shopify() -> tuple[str, str] | None:
    """Retorna (shop_name, access_token) o None si faltan."""
    config = cargar_config_shopify()
    shop_name = config.get("shop_name")
    access_token = config.get("access_token")

    if not shop_name or not access_token:
        logger.error("❌ Credenciales de Shopify incompletas en config/shopify.yaml")
        return None

    return shop_name, access_token


async def obtener_stock_producto(shopify_product_id: str) -> int | None:
    """
    Consulta el stock de un producto en Shopify usando REST API.

    Args:
        shopify_product_id: ID del producto en Shopify (números)

    Returns:
        Cantidad en stock, o None si falla
    """
    credenciales = obtener_credenciales_shopify()
    if not credenciales:
        logger.warning("⚠️ No se pueden consultar stocks sin credenciales Shopify")
        return None

    shop_name, access_token = credenciales

    # Verificar caché
    cache_ttl = cargar_config_shopify().get("cache_ttl_seconds", 300)
    if shopify_product_id in _stock_cache:
        stock, timestamp = _stock_cache[shopify_product_id]
        age = (datetime.utcnow() - timestamp).total_seconds()
        if age < cache_ttl:
            logger.debug(f"📦 Stock en caché para {shopify_product_id}: {stock} (edad: {age}s)")
            return stock

    # Consultar REST API de Shopify
    try:
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

        # Shopify REST API - obtener producto y sus variantes
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{shop_name}/admin/api/2024-01/products/{shopify_product_id}.json",
                headers=headers,
                timeout=10.0,
            )

            if response.status_code == 404:
                logger.warning(f"⚠️ Producto {shopify_product_id} no encontrado en Shopify (404)")
                return None
            elif response.status_code != 200:
                logger.error(f"❌ Error Shopify API ({response.status_code}): {response.text}")
                return None

            data = response.json()
            product = data.get("product")

            if not product:
                logger.warning(f"⚠️ No se encontró producto {shopify_product_id}")
                return None

            # Sumar stock de todas las variantes
            variants = product.get("variants", [])
            if not variants:
                logger.warning(f"⚠️ Producto {shopify_product_id} sin variantes")
                return None

            # Calcular stock total (suma de todas las variantes)
            stock_total = sum(v.get("inventory_quantity", 0) for v in variants)

            logger.info(f"📦 Stock Shopify para {shopify_product_id}: {stock_total} unidades")

            # Guardar en caché
            _stock_cache[shopify_product_id] = (stock_total, datetime.utcnow())

            return stock_total

    except Exception as e:
        logger.error(f"❌ Error consultando stock en Shopify: {e}")
        return None


async def obtener_stocks_multiples(shopify_ids: list[str]) -> dict[str, int]:
    """
    Consulta stocks de múltiples productos en una sola llamada.

    Args:
        shopify_ids: Lista de IDs de productos en Shopify

    Returns:
        Dict { shopify_id: stock }
    """
    stocks = {}
    for product_id in shopify_ids:
        stock = await obtener_stock_producto(product_id)
        if stock is not None:
            stocks[product_id] = stock
    return stocks


def obtener_stock_por_nombre_producto(nombre_producto: str) -> int | None:
    """
    Obtiene el stock usando el nombre del producto (ej: 'theragun_mini').
    NOTA: Esta es síncrona, usa obtener_stock_producto para async.

    Args:
        nombre_producto: Nombre interno del producto (ej: 'theragun_mini')

    Returns:
        Stock si existe, None en caso contrario
    """
    config = cargar_config_shopify()
    products = config.get("products", {})

    if nombre_producto not in products:
        logger.warning(f"⚠️ Producto '{nombre_producto}' no mapeado en shopify.yaml")
        return None

    product_info = products[nombre_producto]
    shopify_id = product_info.get("shopify_id")

    if not shopify_id:
        logger.warning(f"⚠️ Producto '{nombre_producto}' sin shopify_id")
        return None

    # Buscar en caché
    if shopify_id in _stock_cache:
        stock, timestamp = _stock_cache[shopify_id]
        cache_ttl = config.get("cache_ttl_seconds", 300)
        age = (datetime.utcnow() - timestamp).total_seconds()
        if age < cache_ttl:
            return stock

    logger.debug(f"⚠️ Stock no en caché para '{nombre_producto}', usar obtener_stock_producto async")
    return None


def formatear_stock(stock: int | None, nombre_producto: str = "") -> str:
    """
    Formatea el stock de forma legible para Claude.

    Args:
        stock: Cantidad disponible
        nombre_producto: Nombre del producto (opcional)

    Returns:
        String formateado
    """
    if stock is None:
        return "Stock no disponible en este momento"
    elif stock == 0:
        return "Sin stock disponible"
    elif stock == 1:
        return "1 unidad disponible"
    else:
        return f"{stock} unidades disponibles"
