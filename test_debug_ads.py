#!/usr/bin/env python3
"""
Debug script: Simula un webhook de WHAPI con Meta Ads context
para ver si el parsing funciona correctamente
"""

import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock
from fastapi import Request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.providers.whapi import ProveedorWhapi
from agent.providers.base import MensajeEntrante


async def test_whapi_parsing():
    """Test parsing de diferentes tipos de mensajes desde WHAPI"""

    proveedor = ProveedorWhapi()

    print("\n" + "="*70)
    print("TEST: WHAPI PARSING — Meta Ads Detection")
    print("="*70)

    # ════════════════════════════════════════════════════════════
    # TEST 1: Mensaje de TEXTO con context.id (anuncio)
    # ════════════════════════════════════════════════════════════
    print("\n\n[TEST 1] Mensaje de TEXTO con context.id (Meta Ads)")
    print("-" * 70)

    payload_1 = {
        "messages": [
            {
                "id": "wamid.test123",
                "chat_id": "595991234567",
                "from_me": False,
                "type": "text",
                "text": {
                    "body": "Hola quiero más información",
                    "context": {
                        "id": "whoop_peak_ad_001",
                        "reference_message_id": None
                    }
                }
            }
        ]
    }

    # Crear un mock Request
    class MockRequest:
        async def json(self):
            return payload_1

    request = MockRequest()
    mensajes = await proveedor.parsear_webhook(request)

    if mensajes:
        msg = mensajes[0]
        print(f"✓ Mensaje parseado: {msg.texto}")
        print(f"  - Anuncio ID: {msg.anuncio_id}")
        print(f"  - Payload: {msg.payload}")
        print(f"  - Contexto anuncio: {msg.contexto_anuncio}")

        if msg.anuncio_id or msg.payload or msg.contexto_anuncio:
            print(f"  ✅ ÉXITO: Se detectó contexto de anuncio")
        else:
            print(f"  ❌ FALLO: NO se detectó contexto de anuncio")
    else:
        print("❌ No se parseó ningún mensaje")

    # ════════════════════════════════════════════════════════════
    # TEST 2: Mensaje de BUTTON (click en botón de anuncio)
    # ════════════════════════════════════════════════════════════
    print("\n\n[TEST 2] Mensaje de BUTTON (click en CTA de anuncio)")
    print("-" * 70)

    payload_2 = {
        "messages": [
            {
                "id": "wamid.test456",
                "chat_id": "595991234567",
                "from_me": False,
                "type": "button",
                "button": {
                    "text": "Quiero más info",
                    "payload": "theragun_mini"
                }
            }
        ]
    }

    request = MockRequest()
    request.json = AsyncMock(return_value=payload_2)
    mensajes = await proveedor.parsear_webhook(request)

    if mensajes:
        msg = mensajes[0]
        print(f"✓ Mensaje parseado: {msg.texto}")
        print(f"  - Anuncio ID: {msg.anuncio_id}")
        print(f"  - Payload: {msg.payload}")
        print(f"  - Contexto anuncio: {msg.contexto_anuncio}")

        if msg.payload == "theragun_mini":
            print(f"  ✅ ÉXITO: Se capturó payload correctamente")
        else:
            print(f"  ❌ FALLO: Payload no se capturó")
    else:
        print("❌ No se parseó ningún mensaje")

    # ════════════════════════════════════════════════════════════
    # TEST 3: Mensaje de REFERRAL (desde anuncio de referral)
    # ════════════════════════════════════════════════════════════
    print("\n\n[TEST 3] Mensaje de REFERRAL (desde anuncio de referral)")
    print("-" * 70)

    payload_3 = {
        "messages": [
            {
                "id": "wamid.test789",
                "chat_id": "595991234567",
                "from_me": False,
                "type": "referral",
                "referral": {
                    "source_type": "ad",
                    "source_id": "jetboots_pro_plus_campaign"
                }
            }
        ]
    }

    request = MockRequest()
    request.json = AsyncMock(return_value=payload_3)
    mensajes = await proveedor.parsear_webhook(request)

    if mensajes:
        msg = mensajes[0]
        print(f"✓ Mensaje parseado: {msg.texto}")
        print(f"  - Anuncio ID: {msg.anuncio_id}")
        print(f"  - Payload: {msg.payload}")
        print(f"  - Contexto anuncio: {msg.contexto_anuncio}")

        if msg.payload == "jetboots_pro_plus_campaign":
            print(f"  ✅ ÉXITO: Se capturó referral source_id")
        else:
            print(f"  ❌ FALLO: Referral no se capturó")
    else:
        print("❌ No se parseó ningún mensaje")

    # ════════════════════════════════════════════════════════════
    # TEST 4: Mensaje de TEXTO SIN context (cliente normal)
    # ════════════════════════════════════════════════════════════
    print("\n\n[TEST 4] Mensaje de TEXTO SIN context (cliente normal, sin anuncio)")
    print("-" * 70)

    payload_4 = {
        "messages": [
            {
                "id": "wamid.test000",
                "chat_id": "595991234567",
                "from_me": False,
                "type": "text",
                "text": {
                    "body": "Hola"
                }
            }
        ]
    }

    request = MockRequest()
    request.json = AsyncMock(return_value=payload_4)
    mensajes = await proveedor.parsear_webhook(request)

    if mensajes:
        msg = mensajes[0]
        print(f"✓ Mensaje parseado: {msg.texto}")
        print(f"  - Anuncio ID: {msg.anuncio_id}")
        print(f"  - Payload: {msg.payload}")

        if msg.anuncio_id is None and msg.payload is None:
            print(f"  ✅ CORRECTO: NO hay contexto de anuncio (es un cliente normal)")
        else:
            print(f"  ⚠️  INESPERADO: Se detectó contexto cuando no debería")
    else:
        print("❌ No se parseó ningún mensaje")

    print("\n" + "="*70)
    print("RESUMEN: Todos los tipos de payload fueron testeados")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(test_whapi_parsing())
