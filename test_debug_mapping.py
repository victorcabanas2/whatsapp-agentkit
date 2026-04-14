#!/usr/bin/env python3
"""
Debug script: Verifica si mapear_anuncio_a_producto() funciona con IDs reales
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.brain import mapear_anuncio_a_producto


def test_mapping():
    """Test diferentes IDs de anuncios y vé qué producto identifica"""

    print("\n" + "="*70)
    print("TEST: mapear_anuncio_a_producto() — ¿Qué producto identifica?")
    print("="*70)

    # Lista de posibles IDs que Meta podría enviar
    test_cases = [
        # IDs esperados (en el diccionario)
        ("whoop_peak", "WHOOP PEAK 5.0"),
        ("theragun_mini", "Theragun Mini 3.0"),
        ("jetboots_pro_plus", "JetBoots Pro Plus"),
        ("theraface_depuffing_wand", "TheraFace Depuffing Wand"),
        ("foreo_faq_211", "FOREO FAQ 211 (Cuello)"),

        # IDs con variaciones (posibles formatos que Meta envíe)
        ("whoop_peak_ad", "WHOOP PEAK 5.0 (con _ad)"),
        ("whoop_peak_campaign", "WHOOP PEAK 5.0 (con _campaign)"),
        ("123456789_whoop_peak", "WHOOP PEAK 5.0 (con ID numérico)"),
        ("WHOOP_PEAK", "WHOOP PEAK 5.0 (mayúsculas)"),
        ("Whoop Peak", "WHOOP PEAK 5.0 (con espacio)"),

        # IDs completamente desconocidos
        ("unknown_product_xyz", "Producto desconocido"),
        ("12345", "ID numérico solo"),
        ("", "String vacío"),
    ]

    print("\nProbando mapeo de IDs:")
    print("-" * 70)

    for anuncio_id, esperado in test_cases:
        resultado = mapear_anuncio_a_producto(anuncio_id)

        if resultado in esperado or esperado in resultado:
            status = "✅"
        elif resultado == anuncio_id:
            status = "⚠️ FALLBACK"  # Retornó el ID original sin mapear
        else:
            status = "❌"

        print(f"{status} ID: '{anuncio_id}'")
        print(f"   → Producto: {resultado}")
        print()

    # ════════════════════════════════════════════════════════════
    # ANÁLISIS: Mostrar el diccionario de mapeos actual
    # ════════════════════════════════════════════════════════════

    print("\n" + "="*70)
    print("MAPEOS ACTUALES EN brain.py:")
    print("="*70)

    import inspect

    # Obtener código fuente de la función para ver el diccionario
    source = inspect.getsource(mapear_anuncio_a_producto)

    # Buscar el diccionario "mapeos = {"
    start = source.find("mapeos = {")
    end = source.find("}", start) + 1

    if start != -1 and end > start:
        mapeos_code = source[start:end]
        print("\nDiccionario en el código:")
        print(mapeos_code[:500])  # Mostrar primeros 500 caracteres
        print("\n... (ver agent/brain.py línea 107 para la lista completa)")
    else:
        print("No se encontró el diccionario. Revisa agent/brain.py")

    print("\n" + "="*70)
    print("CONCLUSIÓN:")
    print("="*70)
    print("""
Si vez ⚠️ FALLBACK, significa que el anuncio_id NO está en el diccionario.
Claude recibirá el ID sin mapear, lo cual puede causar que no identifique
el producto correctamente.

SOLUCIONES:
1. Verifica qué IDs REALMENTE está enviando Meta/WHAPI
2. Agrega esos IDs al diccionario mapeos en brain.py
3. Usa exactamente los IDs esperados en Facebook Ads Manager

Si vez ❌, significa que el mapeo falló completamente.
""")


if __name__ == "__main__":
    test_mapping()
