# agent/tools.py — Herramientas y utilidades del agente Belén
# Generado por AgentKit

"""
Herramientas específicas del negocio Rebody.
Estas funciones extienden las capacidades del agente más allá de responder texto.
"""

import os
import yaml
import logging
from datetime import datetime

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """
    Retorna el horario de atención de Rebody.

    Returns:
        Dict con horarios y estado de apertura
    """
    info = cargar_info_negocio()
    horario = info.get("negocio", {}).get("horario", {})

    # Obtener hora actual
    ahora = datetime.now()
    hora_actual = ahora.hour
    dia_semana = ahora.weekday()  # 0=lunes, 5=sábado, 6=domingo

    # Determinar si está abierto (SIMPLIFICADO - mejorar con huso horario de Paraguay)
    if dia_semana < 5:  # Lunes a viernes
        abierto = 8 <= hora_actual < 18
    elif dia_semana == 5:  # Sábado
        abierto = 8 <= hora_actual < 12
    else:  # Domingo
        abierto = False

    return {
        "lunes_viernes": horario.get("lunes_viernes", "8:00 AM - 6:00 PM"),
        "sabado": horario.get("sabado", "8:00 AM - 12:00 PM"),
        "domingo": horario.get("domingo", "Cerrado"),
        "abierto_ahora": abierto,
        "hora_actual": ahora.strftime("%H:%M"),
    }


def obtener_datos_pago() -> dict:
    """
    Retorna los datos de pago para transferencias bancarias.

    Returns:
        Dict con datos bancarios
    """
    info = cargar_info_negocio()
    return info.get("pago", {})


def buscar_producto_en_catalogo(consulta: str) -> list[dict]:
    """
    Busca productos en el catálogo que coincidan con la consulta.
    (NOTA: En una versión mejorada, cargaríamos el catálogo desde un CSV/DB)

    Args:
        consulta: Nombre de producto o marca a buscar

    Returns:
        Lista de productos que coinciden
    """
    # Por ahora, retornar lista vacía o placeholder
    # En producción, esto consultaría la base de datos de productos
    logger.info(f"Búsqueda de producto: {consulta}")
    return []


def es_horario_laboral() -> bool:
    """
    Verifica si estamos dentro del horario de atención.

    Returns:
        True si está abierto, False si está cerrado
    """
    return obtener_horario().get("abierto_ahora", False)


def obtener_mensaje_fuera_horario() -> str:
    """Retorna mensaje para atender fuera de horario."""
    horario_info = obtener_horario()
    return (
        f"Hola! Gracias por escribir a Rebody. Estamos fuera de horario ahora mismo.\n\n"
        f"📅 Nuestro horario de atención:\n"
        f"Lunes-Viernes: {horario_info['lunes_viernes']}\n"
        f"Sábado: {horario_info['sabado']}\n"
        f"Domingo: {horario_info['domingo']}\n\n"
        f"Te responderemos apenas abra nuestro horario. ¿Hay algo urgente?"
    )


def normalizar_telefono(telefono: str) -> str:
    """
    Normaliza un número de teléfono a formato internacional.

    Args:
        telefono: Número a normalizar

    Returns:
        Número normalizado (ej: 595991234567)
    """
    # Remover caracteres especiales
    limpio = "".join(c for c in telefono if c.isdigit())
    # Si no tiene el código de país Paraguay (595), agregarlo
    if not limpio.startswith("595"):
        limpio = "595" + limpio.lstrip("0")
    return limpio


def registrar_lead(telefono: str, nombre: str = "", interes: str = "") -> dict:
    """
    Registra un nuevo lead de ventas.
    (En producción, esto guardaría en la DB)

    Args:
        telefono: Número de cliente
        nombre: Nombre del cliente (opcional)
        interes: Producto o servicio de interés

    Returns:
        Dict con datos del lead registrado
    """
    lead = {
        "telefono": normalizar_telefono(telefono),
        "nombre": nombre,
        "interes": interes,
        "fecha": datetime.now().isoformat(),
        "estado": "nuevo"
    }
    logger.info(f"Lead registrado: {lead}")
    return lead


# ════════════════════════════════════════════════════════════
# Herramientas específicas para casos de uso de Rebody:
#
# 1. FAQ / Preguntas frecuentes:
#    - buscar_producto_en_catalogo() — Buscar por nombre/marca
#    - obtener_datos_pago() — Información de pago
#    - obtener_horario() — Horarios de atención
#
# 2. Leads / Ventas:
#    - registrar_lead() — Guardar datos del cliente
#    - obtener_mensajes_recomendacion() — Sugerencias de productos
#
# 3. Pedidos:
#    - crear_pedido() — Guardar un pedido (TODO)
#    - confirmar_pago() — Marcar pedido como pagado (TODO)
#
# 4. Soporte:
#    - crear_ticket_soporte() — Registrar problema (TODO)
#    - escalar_a_humano() — Transferir a vendedor (TODO)
#
# Nota: Claude Sonnet puede ser instruido en el system prompt para usar
# estas funciones de forma natural sin necesidad de function_calling.
# ════════════════════════════════════════════════════════════
