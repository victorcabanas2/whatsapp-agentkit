# agent/providers/__init__.py — Factory de proveedores
# Generado por AgentKit

"""
Selecciona el proveedor de WhatsApp según la variable WHATSAPP_PROVIDER en .env.
Soporta: whapi, meta, twilio
"""

import os
from agent.providers.base import ProveedorWhatsApp


def obtener_proveedor() -> ProveedorWhatsApp:
    """
    Retorna una instancia del proveedor de WhatsApp configurado en WHATSAPP_PROVIDER.

    Raises:
        ValueError: Si el proveedor no está soportado

    Returns:
        ProveedorWhatsApp: Una instancia del proveedor configurado
    """
    proveedor = os.getenv("WHATSAPP_PROVIDER", "whapi").lower().strip()

    if proveedor == "whapi":
        from agent.providers.whapi import ProveedorWhapi
        return ProveedorWhapi()
    elif proveedor == "meta":
        from agent.providers.meta import ProveedorMeta
        return ProveedorMeta()
    elif proveedor == "twilio":
        from agent.providers.twilio import ProveedorTwilio
        return ProveedorTwilio()
    else:
        raise ValueError(
            f"Proveedor no soportado: '{proveedor}'. "
            "Usa: whapi, meta, o twilio"
        )
