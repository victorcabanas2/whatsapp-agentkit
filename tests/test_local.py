#!/usr/bin/env /Library/Frameworks/Python.framework/Versions/3.14/bin/python3
# tests/test_local.py — Simulador de chat en terminal
# Generado por AgentKit

"""
Prueba tu agente Belén sin necesitar WhatsApp.
Simula una conversación en la terminal como si un cliente estuviera escribiendo.

Uso:
    python tests/test_local.py

Comandos especiales:
    /limpiar  — borra el historial de la conversación
    /stats    — muestra estadísticas de la conversación
    /salir    — termina el test
"""

import asyncio
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.brain import generar_respuesta
from agent.memory import (
    inicializar_db,
    guardar_mensaje,
    obtener_historial,
    limpiar_historial,
    obtener_estadisticas
)

# Número de teléfono simulado para testing
TELEFONO_TEST = "test-local-001"


async def main():
    """Loop principal del chat de prueba."""
    # Inicializar base de datos
    await inicializar_db()

    # Banner
    print()
    print("=" * 70)
    print("   AgentKit — Chat Local con Belén")
    print("=" * 70)
    print()
    print("  Escribe como si fueras un cliente de Rebody.")
    print("  Belén responderá con IA.")
    print()
    print("  Comandos especiales:")
    print("    /limpiar  — borra el historial")
    print("    /stats    — ve estadísticas")
    print("    /salir    — termina el chat")
    print()
    print("-" * 70)
    print()

    while True:
        try:
            # Leer input del usuario
            entrada = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n✓ Chat finalizado.")
            break

        # Validar entrada
        if not entrada:
            continue

        # Comandos especiales
        if entrada.lower() == "/salir":
            print("\n✓ Chat finalizado.")
            break

        if entrada.lower() == "/limpiar":
            await limpiar_historial(TELEFONO_TEST)
            print("[Historial borrado]\n")
            continue

        if entrada.lower() == "/stats":
            stats = await obtener_estadisticas(TELEFONO_TEST)
            print(f"\n📊 Estadísticas:")
            print(f"   Total de mensajes: {stats['total_mensajes']}")
            print(f"   Mensajes tuyos: {stats['mensajes_usuario']}")
            print(f"   Mensajes de Belén: {stats['mensajes_agente']}")
            if stats['primera_msg']:
                print(f"   Primer mensaje: {stats['primera_msg'].strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Último mensaje: {stats['ultima_msg'].strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            continue

        # Procesamiento normal de mensaje
        try:
            # Obtener historial ANTES de guardar (brain.py agrega el mensaje actual)
            historial = await obtener_historial(TELEFONO_TEST)

            # Mostrar animación de escritura
            print("Belén: ", end="", flush=True)

            # Generar respuesta con Claude
            respuesta = await generar_respuesta(entrada, historial)

            # Mostrar respuesta
            print(respuesta)
            print()

            # Guardar en base de datos
            await guardar_mensaje(TELEFONO_TEST, "user", entrada)
            await guardar_mensaje(TELEFONO_TEST, "assistant", respuesta)

        except KeyboardInterrupt:
            print("\n\n✓ Chat finalizado.")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Por favor intenta de nuevo.\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✓ Chat finalizado.")
