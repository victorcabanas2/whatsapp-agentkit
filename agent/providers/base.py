# agent/providers/base.py — Clase base para proveedores de WhatsApp
# Generado por AgentKit

"""
Define la interfaz común que todos los proveedores de WhatsApp deben implementar.
Esto permite cambiar de proveedor (Whapi, Meta, Twilio) sin modificar el resto del código.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from fastapi import Request


@dataclass
class MensajeEntrante:
    """
    Mensaje normalizado — mismo formato sin importar el proveedor.
    Todos los proveedores deben convertir sus payloads a este formato.
    """
    telefono: str            # Número del remitente (ej: 595991234567)
    texto: str               # Contenido del mensaje
    mensaje_id: str          # ID único del mensaje
    es_propio: bool          # True si lo envió el agente (se ignora)
    payload: str | None = None  # Metadata del anuncio (ej: "depuffing_wand", "theragun_mini")
    imagen_url: str | None = None  # URL de imagen si el mensaje es una imagen
    reply_a_mensaje_id: str | None = None  # ID del mensaje original si es un reply
    reply_a_texto: str | None = None  # Contenido del mensaje al que se responde
    anuncio_id: str | None = None  # ID o URL del anuncio Meta Ads
    contexto_anuncio: dict | None = None  # Info completa del anuncio ({"source_type": "ad", "source_id": "...", ...})


class ProveedorWhatsApp(ABC):
    """
    Interfaz abstracta que cada proveedor de WhatsApp debe implementar.
    Esto permite que el resto del código sea agnóstico al proveedor.
    """

    @abstractmethod
    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """
        Extrae y normaliza mensajes del payload del webhook.

        Args:
            request: Request de FastAPI con el payload del proveedor

        Returns:
            Lista de MensajeEntrante normalizados
        """
        ...

    @abstractmethod
    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """
        Envía un mensaje de texto. Retorna True si fue exitoso.

        Args:
            telefono: Número del destinatario
            mensaje: Texto a enviar

        Returns:
            True si el envío fue exitoso, False en caso contrario
        """
        ...

    async def validar_webhook(self, request: Request) -> dict | int | None:
        """
        Verificación GET del webhook (solo Meta la requiere).
        Por defecto retorna None (no es obligatorio).

        Args:
            request: Request de FastAPI

        Returns:
            Respuesta para validación, o None si no aplica
        """
        return None

    async def enviar_imagen(self, telefono: str, imagen_url: str, caption: str = "") -> bool:
        """
        Envía una imagen. Por defecto, retorna False (debe implementarse en cada proveedor).

        Args:
            telefono: Número del destinatario
            imagen_url: URL de la imagen
            caption: Texto que acompaña la imagen

        Returns:
            True si el envío fue exitoso, False en caso contrario
        """
        return False
