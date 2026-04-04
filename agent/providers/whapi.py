# agent/providers/whapi.py — Adaptador para Whapi.cloud
# Generado por AgentKit

"""
Implementa la interfaz ProveedorWhatsApp para Whapi.cloud.
Whapi es una API REST simple y directa para enviar y recibir mensajes WhatsApp.
"""

import os
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


class ProveedorWhapi(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Whapi.cloud (REST API simple)."""

    def __init__(self):
        self.token = os.getenv("WHAPI_TOKEN")
        self.url_envio = "https://gate.whapi.cloud/messages/text"
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado en .env")

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """
        Parsea el payload de Whapi.cloud y retorna una lista de MensajeEntrante.

        Formato esperado:
        {
            "messages": [
                {
                    "id": "msg_123",
                    "chat_id": "595991234567",
                    "from_me": false,
                    "text": {
                        "body": "Hola, ¿tienen productos?"
                    },
                    "timestamp": 1234567890
                }
            ]
        }
        """
        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Error al parsear JSON de Whapi: {e}")
            return []

        mensajes = []
        for msg in body.get("messages", []):
            # Ignorar mensajes propios (enviados por el bot)
            if msg.get("from_me", False):
                continue

            # Extraer datos
            telefono = msg.get("chat_id", "").strip()
            texto = msg.get("text", {}).get("body", "").strip()
            mensaje_id = msg.get("id", "")

            # Solo procesar si hay teléfono y texto
            if telefono and texto:
                mensajes.append(MensajeEntrante(
                    telefono=telefono,
                    texto=texto,
                    mensaje_id=mensaje_id,
                    es_propio=False,
                ))
                logger.debug(f"Mensaje parseado: {telefono} → {texto[:50]}...")

        return mensajes

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """
        Envía un mensaje de texto via Whapi.cloud.

        Args:
            telefono: Número en formato internacional (sin + al inicio)
            mensaje: Texto a enviar

        Returns:
            True si el envío fue exitoso, False en caso contrario
        """
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — mensaje no enviado")
            return False

        # Whapi requiere el teléfono sin caracteres especiales
        telefono_limpio = str(telefono).replace("+", "").replace(" ", "")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        payload = {
            "to": telefono_limpio,
            "body": mensaje,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url_envio,
                    json=payload,
                    headers=headers,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    logger.info(f"✓ Mensaje enviado a {telefono_limpio}")
                    return True
                else:
                    logger.error(
                        f"✗ Error Whapi ({response.status_code}): {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"✗ Error al enviar mensaje via Whapi: {e}")
            return False
