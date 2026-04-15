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
            contexto_payload = None  # Para guardar metadata del anuncio

            # TIPO 1: Mensaje de texto normal (incluyendo replies/citas)
            if tipo_msg == "text":
                text_obj = msg.get("text", {})
                texto = text_obj.get("body", "").strip()

                # Variables para reply
                reply_a_msg_id = None
                reply_a_msg_texto = None

                # Extraer mensaje citado si existe (reply)
                quoted_msg = text_obj.get("quoted_message", {})
                if quoted_msg:
                    quoted_text = quoted_msg.get("body", "").strip()
                    quoted_id = quoted_msg.get("id", "").strip()

                    # Si el mensaje citado no tiene texto (es imagen/video/doc), describir el tipo
                    if not quoted_text:
                        quoted_type = quoted_msg.get("type", "")
                        quoted_caption = quoted_msg.get("caption", "").strip()
                        if quoted_type == "image":
                            quoted_text = f"[Imagen{': ' + quoted_caption if quoted_caption else ''}]"
                        elif quoted_type == "video":
                            quoted_text = "[Video]"
                        elif quoted_type == "document":
                            doc_name = quoted_msg.get("filename", "")
                            quoted_text = f"[Documento{': ' + doc_name if doc_name else ''}]"
                        elif quoted_type == "audio":
                            quoted_text = "[Audio]"
                        elif quoted_type:
                            quoted_text = f"[{quoted_type}]"
                        else:
                            quoted_text = "[Mensaje anterior]"

                    reply_a_msg_id = quoted_id if quoted_id else None
                    reply_a_msg_texto = quoted_text
                    # Prepender el contexto del mensaje citado
                    texto = f"[Reply a: \"{quoted_text[:100]}\"] {texto}"
                    logger.debug(f"Reply detectado: {texto[:60]}... (reply_id: {reply_a_msg_id})")
                else:
                    logger.debug(f"Mensaje de texto: {texto[:50]}...")

                # ═══════════════════════════════════════════════════════════
                # EXTRAER CONTEXTO DE ANUNCIO (Meta Ads)
                # ═══════════════════════════════════════════════════════════
                # Meta Ads envía el contexto en varios lugares posibles:
                # 1. context.id — ID del mensaje o anuncio anterior
                # 2. context.reference_message_id — ID del mensaje referenciado
                # 3. button.payload — Payload del botón del anuncio
                # 4. referral en RAÍZ del mensaje (Click-to-WhatsApp de Facebook)

                ad_context = text_obj.get("context", {})
                if ad_context:
                    ad_id = ad_context.get("id") or ad_context.get("reference_message_id")
                    if ad_id:
                        contexto_payload = ad_id
                        logger.info(f"🎯 Contexto de anuncio detectado (desde context): {ad_id}")
                        texto = f"[CLIENTE VIENE DE ANUNCIO: {ad_id}] {texto}"

                # BUSCAR REFERRAL EN RAÍZ DEL MENSAJE (Meta Click-to-WhatsApp)
                root_referral = msg.get("referral", {})
                if root_referral:
                    source_type = root_referral.get("source_type", "").strip()
                    source_id = root_referral.get("source_id", "").strip()
                    body_url = root_referral.get("body_url", "").strip()
                    headline = root_referral.get("headline", "").strip()

                    if source_type == "ad" or source_id:
                        # Esto es un anuncio Meta
                        if source_id and not contexto_payload:
                            contexto_payload = source_id
                            logger.info(f"🎯 Contexto de anuncio detectado (desde referral): {source_id}")
                            if headline:
                                texto = f"[CLIENTE VIENE DE ANUNCIO: {source_id} ({headline})] {texto}"
                            else:
                                texto = f"[CLIENTE VIENE DE ANUNCIO: {source_id}] {texto}"

                        # Guardar URL del anuncio en contexto_payload para que ad_analyzer pueda procesarla
                        if body_url:
                            if contexto_payload and "|" not in contexto_payload:
                                contexto_payload = f"{contexto_payload}|URL:{body_url}"
                            elif not contexto_payload:
                                contexto_payload = f"URL:{body_url}"
                            logger.debug(f"📄 URL del anuncio encontrada: {body_url[:80]}...")

            # TIPO 2: Click en botón de anuncio/CTA
            elif tipo_msg == "button":
                # Button reply from ad click
                button_text = msg.get("button", {}).get("text", "").strip()
                payload = msg.get("button", {}).get("payload", "").strip()

                # Guardar payload para contexto de anuncio
                contexto_payload = payload if payload else None

                if button_text:
                    texto = button_text
                elif payload:
                    texto = payload
                else:
                    texto = "[Click en botón de anuncio]"

                logger.info(f"✅ Mensaje desde ANUNCIO/botón: {texto} (payload: {contexto_payload})")

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
                contexto_payload = source_id if source_id else source_type
                logger.info(f"✅ Referral de anuncio: {source_type}")

            # TIPO 7: Audio — detectar y marcar para respuesta polite
            elif tipo_msg == "audio":
                audio_link = msg.get("audio", {}).get("link", "")
                texto = f"[AUDIO_RECIBIDO:{audio_link}]" if audio_link else "[AUDIO_RECIBIDO]"
                logger.info(f"🎵 Audio recibido de {telefono}")

            # TIPO 8: Video
            elif tipo_msg == "video":
                texto = "[Video enviado]"
                logger.debug(f"Video recibido de {telefono}")

            # TIPO 9: Documento/archivo
            elif tipo_msg == "document":
                doc_name = msg.get("document", {}).get("filename", "archivo")
                texto = f"[Documento enviado: {doc_name}]"
                logger.debug(f"Documento recibido de {telefono}")

            else:
                logger.warning(f"⚠️ Tipo de mensaje no reconocido: {tipo_msg}")
                continue

            # ═══════════════════════════════════════════════════════════
            # PROCESAR SI HAY CONTENIDO
            # ═══════════════════════════════════════════════════════════

            if not texto and not imagen_url:
                logger.debug(f"Mensaje vacío de {telefono}, ignorando")
                continue

            # EXTRAER ad_url DE contexto_payload SI ESTÁ INCLUIDA
            ad_url = None
            if contexto_payload and "|URL:" in contexto_payload:
                parts = contexto_payload.split("|URL:")
                ad_url = parts[1] if len(parts) > 1 else None

            mensajes.append(MensajeEntrante(
                telefono=telefono,
                texto=texto,
                mensaje_id=mensaje_id,
                es_propio=False,
                payload=contexto_payload,  # Metadata del anuncio (puede contener |URL:...)
                imagen_url=imagen_url,  # URL de imagen si aplica
                reply_a_mensaje_id=reply_a_msg_id if 'reply_a_msg_id' in locals() else None,
                reply_a_texto=reply_a_msg_texto if 'reply_a_msg_texto' in locals() else None,
                anuncio_id=contexto_payload,  # El payload puede contener el ID del anuncio
                contexto_anuncio={
                    "payload": contexto_payload.split("|URL:")[0] if contexto_payload else None,
                    "ad_url": ad_url,
                } if contexto_payload else None,
            ))
            logger.info(f"📨 Mensaje parseado: {telefono} → {texto[:60]}...")

        return mensajes

    async def enviar_imagen(self, telefono: str, imagen_data: str, caption: str = "") -> bool:
        """Envía una imagen via Whapi.cloud. Acepta URL o base64."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — imagen no enviada")
            return False

        telefono_limpio = str(telefono).replace("+", "").replace(" ", "")
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

        # Detectar si es base64 (comienza con datos:) o URL
        if imagen_data.startswith("data:") or not imagen_data.startswith("http"):
            # Es base64
            payload = {
                "to": telefono_limpio,
                "image": {"base64": imagen_data, "caption": caption} if caption else {"base64": imagen_data}
            }
        else:
            # Es URL
            payload = {
                "to": telefono_limpio,
                "image": {"link": imagen_data, "caption": caption} if caption else {"link": imagen_data}
            }

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
            telefono: Número en formato local (ej: 0986147509) o internacional (ej: 595986147509)
            mensaje: Texto a enviar

        Returns:
            True si el envío fue exitoso, False en caso contrario
        """
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — mensaje no enviado")
            return False

        # Whapi requiere el teléfono sin caracteres especiales y en formato internacional
        telefono_limpio = str(telefono).replace("+", "").replace(" ", "")

        # Convertir de formato local (0986...) a internacional (595986...)
        if telefono_limpio.startswith("0"):
            # Reemplazar 0 inicial con código país Paraguay (595)
            telefono_limpio = "595" + telefono_limpio[1:]
            logger.debug(f"Convertido a formato internacional: {telefono_limpio}")
        elif not telefono_limpio.startswith("595"):
            # Si no empieza con 595 y tampoco con 0, asumir que ya es internacional
            logger.debug(f"Número ya en formato internacional: {telefono_limpio}")

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
