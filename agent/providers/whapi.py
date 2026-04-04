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
        Soporta: mensajes de texto, imágenes, stickers, button replies (de anuncios), y mensajes interactivos.

        Formatos soportados:
        {
            "messages": [
                {
                    "id": "msg_123",
                    "chat_id": "595991234567",
                    "from_me": false,
                    "type": "text",
                    "text": { "body": "Hola" }
                },
                {
                    "id": "msg_456",
                    "chat_id": "595991234567",
                    "from_me": false,
                    "type": "button",
                    "button": { "text": "Sí" },  // Click en botón de anuncio
                    "context": { "id": "..." }
                },
                {
                    "id": "msg_789",
                    "chat_id": "595991234567",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": { "id": "...", "title": "Sí" }
                    }
                }
            ]
        }
        """
        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"❌ Error al parsear JSON de Whapi: {e}")
            return []

        mensajes = []
        for msg in body.get("messages", []):
            # Ignorar mensajes propios (enviados por el bot)
            if msg.get("from_me", False):
                logger.debug("Ignorando mensaje propio del bot")
                continue

            # Extraer teléfono y ID
            telefono = msg.get("chat_id", "").strip()
            mensaje_id = msg.get("id", "")
            tipo_msg = msg.get("type", "")

            if not telefono:
                logger.debug("Mensaje sin chat_id, ignorando")
                continue

            # ═══════════════════════════════════════════════════════════
            # EXTRAER TEXTO SEGÚN EL TIPO DE MENSAJE
            # ═══════════════════════════════════════════════════════════

            texto = ""
            imagen_url = None

            # TIPO 1: Mensaje de texto normal
            if tipo_msg == "text":
                texto = msg.get("text", {}).get("body", "").strip()
                logger.debug(f"Mensaje de texto: {texto[:50]}...")

            # TIPO 2: Click en botón de anuncio/CTA
            elif tipo_msg == "button":
                # Button reply from ad click
                button_text = msg.get("button", {}).get("text", "").strip()
                payload = msg.get("button", {}).get("payload", "").strip()

                if button_text:
                    texto = button_text
                elif payload:
                    texto = payload
                else:
                    texto = "[Click en botón de anuncio]"

                logger.info(f"✅ Mensaje desde ANUNCIO/botón: {texto}")

            # TIPO 3: Mensaje interactivo (respuesta a lista o botones)
            elif tipo_msg == "interactive":
                interactive = msg.get("interactive", {})
                interactive_type = interactive.get("type", "")

                if interactive_type == "button_reply":
                    # Click en botón interactivo
                    titulo = interactive.get("button_reply", {}).get("title", "").strip()
                    texto = titulo if titulo else "[Click en botón]"
                    logger.info(f"✅ Button reply: {texto}")

                elif interactive_type == "list_reply":
                    # Click en opción de lista
                    titulo = interactive.get("list_reply", {}).get("title", "").strip()
                    texto = titulo if titulo else "[Click en opción de lista]"
                    logger.info(f"✅ List reply: {texto}")

                elif interactive_type == "nfm_reply":
                    # Form submission
                    response_json = interactive.get("nfm_reply", {}).get("response_json", "")
                    texto = response_json if response_json else "[Formulario enviado]"
                    logger.info(f"✅ Form reply: {texto[:50]}...")

            # TIPO 4: Imagen
            elif tipo_msg == "image":
                imagen_url = msg.get("image", {}).get("link")
                texto = "[Imagen enviada]"
                logger.debug(f"Imagen recibida: {imagen_url}")

            # TIPO 5: Sticker
            elif tipo_msg == "sticker":
                imagen_url = msg.get("sticker", {}).get("link")
                texto = "[Sticker enviado]"
                logger.debug(f"Sticker recibido: {imagen_url}")

            # TIPO 6: Referral (usuario vino desde anuncio de referral)
            elif tipo_msg == "referral":
                referral = msg.get("referral", {})
                source_type = referral.get("source_type", "")
                source_id = referral.get("source_id", "")
                texto = f"[Referral desde {source_type}: {source_id}]"
                logger.info(f"✅ Referral de anuncio: {source_type}")

            else:
                logger.warning(f"⚠️ Tipo de mensaje no reconocido: {tipo_msg}")
                continue

            # ═══════════════════════════════════════════════════════════
            # PROCESAR SI HAY CONTENIDO
            # ═══════════════════════════════════════════════════════════

            if not texto and not imagen_url:
                logger.debug(f"Mensaje vacío de {telefono}, ignorando")
                continue

            mensajes.append(MensajeEntrante(
                telefono=telefono,
                texto=texto,
                mensaje_id=mensaje_id,
                es_propio=False,
            ))
            logger.info(f"📨 Mensaje parseado: {telefono} → {texto[:60]}...")

        return mensajes

    async def enviar_imagen(self, telefono: str, url_imagen: str) -> bool:
        """Envía una imagen via Whapi.cloud."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — imagen no enviada")
            return False

        telefono_limpio = str(telefono).replace("+", "").replace(" ", "")
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {"to": telefono_limpio, "image": {"link": url_imagen}}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://gate.whapi.cloud/messages/image",
                    json=payload,
                    headers=headers,
                    timeout=10.0,
                )
                if response.status_code == 200:
                    logger.info(f"✓ Imagen enviada a {telefono_limpio}")
                    return True
                else:
                    logger.error(f"✗ Error Whapi imagen ({response.status_code}): {response.text}")
                    return False
        except Exception as e:
            logger.error(f"✗ Error al enviar imagen: {e}")
            return False

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
