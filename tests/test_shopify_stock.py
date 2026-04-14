#!/usr/bin/env python3
# tests/test_shopify_stock.py — Test de integración con Shopify

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.shopify import obtener_stock_producto, cargar_config_shopify, formatear_stock


async def test_shopify():
    """Test la integración con Shopify."""
    print("\n" + "="*60)
    print("   Test de Shopify Stock Integration")
    print("="*60 + "\n")

    # Cargar config
    config = cargar_config_shopify()
    if not config:
        print("❌ No se pudo cargar config/shopify.yaml")
        return

    print(f"✓ Tienda Shopify: {config.get('shop_name')}")
    print(f"✓ Token configurado: {'Sí' if config.get('access_token') else 'No'}")
    print(f"✓ Productos mapeados: {len(config.get('products', {}))}\n")

    # Test 1: Obtener stock del Theragun Mini
    print("Test 1: Consultando stock del Theragun Mini 3.0...")
    theragun_id = config.get('products', {}).get('theragun_mini', {}).get('shopify_id')

    if theragun_id:
        stock = await obtener_stock_producto(theragun_id)
        print(f"   Shopify ID: {theragun_id}")
        print(f"   Stock: {stock}")
        print(f"   Formateado: {formatear_stock(stock)}\n")
    else:
        print("   ❌ No se encontró ID de Theragun Mini\n")

    # Test 2: Obtener stock del TheraFace PRO
    print("Test 2: Consultando stock del TheraFace PRO...")
    theraface_id = config.get('products', {}).get('theraface_pro', {}).get('shopify_id')

    if theraface_id:
        stock = await obtener_stock_producto(theraface_id)
        print(f"   Shopify ID: {theraface_id}")
        print(f"   Stock: {stock}")
        print(f"   Formateado: {formatear_stock(stock)}\n")
    else:
        print("   ❌ No se encontró ID de TheraFace PRO\n")

    print("="*60)
    print("✓ Tests completados")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_shopify())
