#!/usr/bin/env python3
"""
Script de sincronización de stock desde Shopify.
Se ejecuta cada 5-10 minutos y actualiza stock_actual.json
"""

import os
import json
import yaml
import httpx
from datetime import datetime
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stock_sync")

SHOPIFY_CONFIG_PATH = "config/shopify.yaml"
STOCK_OUTPUT_PATH = "knowledge/stock_actual.json"


def load_shopify_config():
    """Carga configuración de Shopify"""
    with open(SHOPIFY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def get_product_stock(shop_name: str, access_token: str, product_id: str) -> dict:
    """Consulta stock de UN producto en Shopify API"""
    url = f"https://{shop_name}/admin/api/2024-01/products/{product_id}.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                product = data.get("product", {})
                
                # Sumar stock de todas las variantes
                total_stock = 0
                for variant in product.get("variants", []):
                    total_stock += variant.get("inventory_quantity", 0)
                
                return {
                    "id": product_id,
                    "nombre": product.get("title", "Unknown"),
                    "stock": total_stock,
                    "disponible": total_stock > 0,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                logger.error(f"Error Shopify {product_id}: {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"Error consultando {product_id}: {e}")
        return None


async def sync_all_products():
    """Sincroniza stock de TODOS los productos"""
    config = load_shopify_config()
    shop_name = config.get("shop_name")
    access_token = config.get("access_token")
    
    if not shop_name or not access_token:
        logger.error("Falta shop_name o access_token en shopify.yaml")
        return
    
    products_config = config.get("products", {})
    stock_data = {
        "ultima_actualizacion": datetime.now().isoformat(),
        "productos": {}
    }
    
    # Consultar stock en paralelo (máx 10 simultáneas para no sobrecargar Shopify)
    tasks = [
        get_product_stock(shop_name, access_token, info.get("shopify_id"))
        for info in products_config.values()
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, dict) and result.get("id"):
            product_id = result.get("id")
            stock_data["productos"][product_id] = result
    
    if not stock_data["productos"]:
        logger.error("❌ Shopify devolvió 0 productos — no se sobreescribe stock_actual.json para preservar datos")
        return

    with open(STOCK_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(stock_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Stock sincronizado: {len(stock_data['productos'])} productos")


def main():
    """Ejecutar sincronización"""
    try:
        asyncio.run(sync_all_products())
        logger.info("✅ Sincronización completada")
    except Exception as e:
        logger.error(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
