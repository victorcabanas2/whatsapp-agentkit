# agent/brain.py — Cerebro del agente: conexión con Claude API
# Generado por AgentKit

"""
Lógica de IA del agente Belén.
Lee el system prompt de prompts.yaml y genera respuestas usando Claude API.
"""

import os
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

# Cliente de Anthropic
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def cargar_config_prompts() -> dict:
    """Lee la configuración completa desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config or {}
    except FileNotFoundError:
        logger.error("❌ config/prompts.yaml no encontrado")
        return {}
    except Exception as e:
        logger.error(f"❌ Error al leer prompts.yaml: {e}")
        return {}


def cargar_system_prompt() -> str:
    """Retorna el system prompt desde config/prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres un asistente útil. Responde en español.")


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado."""
    config = cargar_config_prompts()
    mensajes = config.get("fallback_message", {})
    if isinstance(mensajes, dict):
        return mensajes.get("error_message", "Lo siento, estoy teniendo problemas técnicos.")
    return "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos."


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback para entradas inválidas."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


async def generar_respuesta(mensaje: str, historial: list[dict]) -> str:
    """
    Genera una respuesta usando Claude API.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]

    Returns:
        La respuesta generada por Claude
    """
    # Validar entrada
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    # Cargar system prompt
    system_prompt = cargar_system_prompt()
    if not system_prompt:
        logger.error("❌ No se pudo cargar el system prompt")
        return obtener_mensaje_error()

    # Construir mensajes para la API
    mensajes = []

    # Agregar historial (máximo últimos 10 mensajes para economizar tokens)
    for msg in historial[-10:]:
        mensajes.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", "")
        })

    # Agregar el mensaje actual
    mensajes.append({
        "role": "user",
        "content": mensaje
    })

    try:
        logger.debug(f"Llamando a Claude con {len(mensajes)} mensajes en contexto")

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=mensajes
        )

        # Extraer la respuesta
        respuesta = response.content[0].text

        # Log de uso
        logger.debug(
            f"✓ Respuesta generada | "
            f"Input: {response.usage.input_tokens} tokens | "
            f"Output: {response.usage.output_tokens} tokens"
        )

        return respuesta

    except Exception as e:
        logger.error(f"❌ Error en Claude API: {e}")
        return obtener_mensaje_error()
