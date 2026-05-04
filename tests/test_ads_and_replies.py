#!/usr/bin/env python3
"""
Test script para validar:
1. Detección de clientes desde Meta Ads
2. Interpretación de replies a mensajes anteriores
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, limpiar_historial


async def test_cliente_desde_anuncio():
    """Test 1: Cliente viene de un anuncio Meta Ads"""
    print("\n" + "="*70)
    print("TEST 1: CLIENTE DESDE ANUNCIO META ADS")
    print("="*70)

    await inicializar_db()
    telefono = "test-anuncio-001"

    # Simular: Cliente hace clic en anuncio de WHOOP PEAK y dice "Hola quiero más información"
    # El mensaje viene con contexto del anuncio

    historial = await obtener_historial(telefono)

    # El contexto es CRÍTICO: esto es lo que main.py prepara cuando detecta un anuncio
    contexto_adicional = """🎯 CONTEXTO CRÍTICO: Este cliente hizo clic en un anuncio específico.
ID/Datos del anuncio: whoop_peak
Producto del anuncio: WHOOP PEAK 5.0
✅ TÚ CONOCES el producto que vio. NO preguntes 'de qué producto es'.
✅ Dale toda la información sobre: WHOOP PEAK 5.0
✅ Precio, stock, beneficios, link — todo sin preguntar qué es."""

    mensaje_usuario = "[CLIENTE VIENE DE ANUNCIO DE: WHOOP PEAK 5.0] Hola quiero más información"

    print(f"\n👤 Cliente: {mensaje_usuario}")
    print(f"\n📌 Contexto para Claude:\n{contexto_adicional}")

    respuesta = await generar_respuesta(
        mensaje_usuario,
        historial,
        contexto_adicional=contexto_adicional
    )

    print(f"\n🤖 Bot:\n{respuesta}")

    # Validar
    print("\n✅ VALIDACIÓN:")
    if "WHOOP" in respuesta and "Gs" in respuesta:
        print("   ✓ Bot identificó el producto (menciona WHOOP y precios)")
    else:
        print("   ✗ Bot NO identificó bien el producto")

    if "de qué" not in respuesta.lower() or "producto" not in respuesta.lower():
        print("   ✓ Bot NO preguntó 'de qué producto' (correcto)")
    else:
        print("   ✗ Bot preguntó 'de qué producto' (INCORRECTO)")

    if "rebody.com.py" in respuesta:
        print("   ✓ Bot incluyó link del producto")
    else:
        print("   ⚠ Bot NO incluyó link (revisar)")

    await limpiar_historial(telefono)


async def test_reply_a_mensaje():
    """Test 2: Cliente responde a mensaje anterior (reply)"""
    print("\n" + "="*70)
    print("TEST 2: CLIENTE RESPONDE A MENSAJE ANTERIOR (REPLY)")
    print("="*70)

    await inicializar_db()
    telefono = "test-reply-001"

    # Simular conversación:
    # 1. Bot pregunta: "¿Buscas monitoreo básico o avanzado?"
    # 2. Cliente responde: "Avanzado" (pero es un reply a esa pregunta)

    # Construir historial
    await guardar_mensaje(telefono, "assistant", "¿Estás buscas monitoreo básico o avanzado?")
    await guardar_mensaje(telefono, "user", "Avanzado")

    historial = await obtener_historial(telefono)

    # El cliente hace un reply a la pregunta anterior
    contexto_adicional = """↩️ CONTEXTO DE REPLY: Este cliente está respondiendo a tu mensaje anterior:
Tu pregunta anterior fue: "¿Estás buscas monitoreo básico o avanzado?"
✅ INTERPRETA la respuesta en el contexto de esa pregunta.
✅ NO repitas la pregunta. El cliente ya te está respondiendo."""

    mensaje_usuario = "[Reply a tu pregunta: '¿Buscas monitoreo básico o avanzado?'] Dice: Avanzado, algo premium"

    print(f"\n👤 Cliente: {mensaje_usuario}")
    print(f"\n📌 Contexto para Claude:\n{contexto_adicional}")

    respuesta = await generar_respuesta(
        mensaje_usuario,
        historial,
        contexto_adicional=contexto_adicional
    )

    print(f"\n🤖 Bot:\n{respuesta}")

    # Validar
    print("\n✅ VALIDACIÓN:")
    if "PEAK" in respuesta or "LIFE" in respuesta:
        print("   ✓ Bot recomendó productos premium (PEAK o LIFE)")
    else:
        print("   ⚠ Bot no mencionó productos premium esperados")

    if "¿buscas" not in respuesta.lower():
        print("   ✓ Bot NO repitió la pregunta (correcto)")
    else:
        print("   ✗ Bot repitió la pregunta (INCORRECTO)")

    if "Gs" in respuesta:
        print("   ✓ Bot incluyó precios")
    else:
        print("   ⚠ Bot no incluyó precios")

    await limpiar_historial(telefono)


async def test_ambos_contextos():
    """Test 3: Cliente viene de anuncio Y hace un reply"""
    print("\n" + "="*70)
    print("TEST 3: CLIENTE DE ANUNCIO + REPLY")
    print("="*70)

    await inicializar_db()
    telefono = "test-combined-001"

    # Cliente viene de anuncio pero después quiere más detalles
    await guardar_mensaje(telefono, "assistant", "Te tengo WHOOP PEAK 5.0 por Gs. 3.150.000. ¿Te interesa?")

    historial = await obtener_historial(telefono)

    contexto_adicional = """🎯 CONTEXTO CRÍTICO: Este cliente hizo clic en un anuncio específico.
ID/Datos del anuncio: whoop_peak
Producto del anuncio: WHOOP PEAK 5.0
✅ TÚ CONOCES el producto que vio. NO preguntes 'de qué producto es'.

↩️ CONTEXTO DE REPLY: El cliente también está respondiendo a un mensaje anterior:
Tu pregunta anterior fue: "Te tengo WHOOP PEAK 5.0 por Gs. 3.150.000. ¿Te interesa?"
✅ INTERPRETA su respuesta en ese contexto."""

    mensaje_usuario = "[CLIENTE VIENE DE ANUNCIO DE: WHOOP PEAK 5.0] [Reply a: 'Te tengo WHOOP PEAK...'] Sí, ¿cuáles son los beneficios exactos?"

    print(f"\n👤 Cliente: {mensaje_usuario}")
    print(f"\n📌 Contexto para Claude:\n{contexto_adicional}")

    respuesta = await generar_respuesta(
        mensaje_usuario,
        historial,
        contexto_adicional=contexto_adicional
    )

    print(f"\n🤖 Bot:\n{respuesta}")

    print("\n✅ VALIDACIÓN:")
    if "PEAK" in respuesta or "monitoreo" in respuesta.lower():
        print("   ✓ Bot mantuvo el contexto del producto (PEAK)")
    else:
        print("   ✗ Bot perdió el contexto del anuncio")

    if "beneficio" in respuesta.lower() or "monitorea" in respuesta.lower():
        print("   ✓ Bot respondió a la pregunta sobre beneficios")
    else:
        print("   ⚠ Bot no respondió claramente sobre beneficios")

    await limpiar_historial(telefono)


async def main():
    print("\n" + "🧪 "*35)
    print("TESTS: Meta Ads Detection + Reply Handling")
    print("🧪 "*35)

    try:
        await test_cliente_desde_anuncio()
        await test_reply_a_mensaje()
        await test_ambos_contextos()

        print("\n" + "="*70)
        print("✅ TODOS LOS TESTS COMPLETADOS")
        print("="*70)
        print("\nResumen:")
        print("- Test 1: Cliente desde anuncio Meta Ads ✓")
        print("- Test 2: Reply a mensaje anterior ✓")
        print("- Test 3: Combinación de ambos ✓")
        print("\nSi los bots respondieron correctamente sin preguntar")
        print("'de qué producto', el fix está funcionando!")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
