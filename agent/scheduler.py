# agent/scheduler.py — Tareas de background 100% async
# Generado por AgentKit

"""
Ejecuta tareas automáticas en background usando asyncio (sin APScheduler):
- Seguimiento a clientes MISMO DÍA de contacto inicial
- Seguimiento a clientes 1 día después de contacto
- Seguimiento a clientes 3 días después de contacto
- Recordatorio de promo cada domingo
- Seguimientos programados dinámicamente por el cliente ("escríbeme en 4 minutos")

VENTAJA: 100% async, sin conflictos de event loops, sin threads de APScheduler.
"""

import logging
import asyncio
from datetime import datetime
import pytz

from agent.memory import (
    obtener_leads_sin_respuesta_mismo_dia,
    obtener_leads_sin_respuesta_1dia,
    obtener_leads_sin_respuesta_3dias,
    marcar_seguimiento_mismo_dia,
    marcar_seguimiento_1dia,
    marcar_seguimiento_3dias,
    obtener_carritos_pendientes,
    marcar_carrito_recordatorio_enviado,
    obtener_pedidos_sin_encuesta,
    marcar_encuesta_enviada,
    obtener_seguimientos_programados,
    marcar_seguimiento_programado_enviado,
)
from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit.scheduler")
proveedor = obtener_proveedor()
TZ = pytz.timezone('America/Asuncion')


# ════════════════════════════════════════════════════════════════
# FUNCIONES ASYNC — Cada una es una tarea independiente
# ════════════════════════════════════════════════════════════════

async def job_seguimiento_mismo_dia():
    """Envía recordatorio a leads el MISMO DÍA de contacto inicial (después de 3 horas)."""
    try:
        logger.info("📅 Ejecutando: Seguimiento MISMO DÍA")
        leads = await obtener_leads_sin_respuesta_mismo_dia()

        if not leads:
            logger.debug("No hay leads con seguimiento mismo día pendiente")
            return

        for lead in leads:
            mensaje = (
                f"Hola {lead.nombre or 'che'}! Déjame preguntarte algo.\n\n"
                f"¿Seguís interesado en los productos que te mostré?\n\n"
                f"Si tenés dudas o querés conocer más, acá estoy para ayudarte 💪"
            )

            exito = await proveedor.enviar_mensaje(lead.telefono, mensaje)
            if exito:
                await marcar_seguimiento_mismo_dia(lead.telefono)
                logger.info(f"✓ Seguimiento mismo día enviado a {lead.telefono}")
            else:
                logger.error(f"✗ Fallo envío a {lead.telefono}")

    except Exception as e:
        logger.error(f"Error en job_seguimiento_mismo_dia: {e}", exc_info=False)


async def job_seguimiento_1dia():
    """Envía recordatorio a leads que no respondieron en 1 día después de contacto."""
    try:
        logger.info("📅 Ejecutando: Seguimiento 1 día")
        leads = await obtener_leads_sin_respuesta_1dia()

        if not leads:
            logger.debug("No hay leads con seguimiento 1 día pendiente")
            return

        for lead in leads:
            mensaje = (
                f"Hola {lead.nombre or 'che'}! Volvimos a pensar en vos.\n\n"
                f"¿Alguna duda con los productos? Seguimos aquí para ayudarte.\n\n"
                f"Escribí cuando quieras 💙"
            )

            exito = await proveedor.enviar_mensaje(lead.telefono, mensaje)
            if exito:
                await marcar_seguimiento_1dia(lead.telefono)
                logger.info(f"✓ Seguimiento 1día enviado a {lead.telefono}")
            else:
                logger.error(f"✗ Fallo envío a {lead.telefono}")

    except Exception as e:
        logger.error(f"Error en job_seguimiento_1dia: {e}", exc_info=False)


async def job_seguimiento_3dias():
    """Envía recordatorio a leads que no respondieron en 3 días después de contacto."""
    try:
        logger.info("📅 Ejecutando: Seguimiento 3 días")
        leads = await obtener_leads_sin_respuesta_3dias()

        if not leads:
            logger.debug("No hay leads con seguimiento 3 días pendiente")
            return

        for lead in leads:
            mensaje = (
                f"Hola de nuevo! No queremos que te pierdas estos productos.\n\n"
                f"Si tenés dudas específicas o necesitás algo especial, contáctate con nuestro equipo comercial:\n\n"
                f"+595 993 233333\n\n"
                f"Estamos acá para ayudarte 🚀"
            )

            exito = await proveedor.enviar_mensaje(lead.telefono, mensaje)
            if exito:
                await marcar_seguimiento_3dias(lead.telefono)
                logger.info(f"✓ Seguimiento 3días enviado a {lead.telefono}")
            else:
                logger.error(f"✗ Fallo envío a {lead.telefono}")

    except Exception as e:
        logger.error(f"Error en job_seguimiento_3dias: {e}", exc_info=False)


async def job_promo_domingo():
    """Envía promos y recordatorios de carrito cada domingo a los que no respondieron."""
    try:
        logger.info("📅 Ejecutando: Promos de domingo")
        carritos = await obtener_carritos_pendientes()

        if not carritos:
            logger.debug("No hay carritos abandonados")
            return

        # Agrupar por teléfono
        carritos_por_telefono = {}
        for carrito in carritos:
            if carrito.telefono not in carritos_por_telefono:
                carritos_por_telefono[carrito.telefono] = []
            carritos_por_telefono[carrito.telefono].append(carrito)

        for telefono, lista_carritos in carritos_por_telefono.items():
            # Construir mensaje con los productos abandonados
            productos_texto = "\n".join(
                [f"  - {c.producto} ({c.precio} Gs)" for c in lista_carritos]
            )

            mensaje = (
                f"🌟 Dominguito especial en Rebody!\n\n"
                f"Te acordás de esto que querías?\n\n"
                f"{productos_texto}\n\n"
                f"¿Todavía te interesa? Hagamos tu pedido hoy.\n\n"
                f"Escribí cuando quieras 😊"
            )

            exito = await proveedor.enviar_mensaje(telefono, mensaje)
            if exito:
                for carrito in lista_carritos:
                    await marcar_carrito_recordatorio_enviado(carrito.id)
                logger.info(f"✓ Promo domingo enviada a {telefono}")
            else:
                logger.error(f"✗ Fallo envío a {telefono}")

    except Exception as e:
        logger.error(f"Error en job_promo_domingo: {e}", exc_info=False)


async def job_encuesta_post_venta():
    """Envía encuesta de satisfacción 2 horas después de la compra."""
    try:
        logger.info("📋 Ejecutando: Encuesta post-venta")
        pedidos = await obtener_pedidos_sin_encuesta()

        if not pedidos:
            logger.debug("No hay pedidos pendientes de encuesta")
            return

        for pedido in pedidos:
            mensaje = (
                f"Hola! 👋\n\n"
                f"¿Cómo te fue con tu {pedido.producto}?\n\n"
                f"Nos encantaría saber tu opinión:\n\n"
                f"⭐⭐⭐⭐⭐ (5 estrellas - Excelente)\n"
                f"⭐⭐⭐⭐ (4 estrellas - Muy bien)\n"
                f"⭐⭐⭐ (3 estrellas - Bien)\n"
                f"⭐⭐ (2 estrellas - Podría mejorar)\n"
                f"⭐ (1 estrella - No me gustó)\n\n"
                f"Escribí el número de estrellas (1-5) y, si querés, contáme más."
            )

            exito = await proveedor.enviar_mensaje(pedido.telefono, mensaje)
            if exito:
                await marcar_encuesta_enviada(pedido.id)
                logger.info(f"✓ Encuesta enviada a {pedido.telefono} (pedido #{pedido.id})")
            else:
                logger.error(f"✗ Fallo envío encuesta a {pedido.telefono}")

    except Exception as e:
        logger.error(f"Error en job_encuesta_post_venta: {e}", exc_info=False)


async def job_seguimientos_programados():
    """Envía seguimientos programados dinámicamente (ej: 'escríbeme en 4 minutos')."""
    try:
        logger.debug("📅 Ejecutando: Seguimientos programados")
        seguimientos = await obtener_seguimientos_programados()

        if not seguimientos:
            logger.debug("No hay seguimientos programados pendientes")
            return

        logger.info(f"Found {len(seguimientos)} pending programmed follow-ups")

        for seg in seguimientos:
            try:
                mensaje = seg.mensaje_personalizado or (
                    f"Hola {seg.nombre or 'che'}! 👋\n\n"
                    f"Como te lo prometí, acá estoy.\n\n"
                    f"¿Qué te puedo ayudar?"
                )

                exito = await proveedor.enviar_mensaje(seg.telefono, mensaje)
                if exito:
                    await marcar_seguimiento_programado_enviado(seg.id)
                    logger.info(f"✓ Seguimiento programado enviado a {seg.telefono} (ID: {seg.id})")
                else:
                    logger.error(f"✗ Fallo envío a {seg.telefono} (ID: {seg.id})")
            except Exception as e:
                logger.error(f"Error enviando seguimiento a {seg.telefono}: {e}", exc_info=False)
                continue

    except Exception as e:
        logger.error(f"Error en job_seguimientos_programados: {e}", exc_info=False)


# ════════════════════════════════════════════════════════════════
# BACKGROUND TASKS PARA FASTAPI
# ════════════════════════════════════════════════════════════════

async def task_seguimientos_programados_loop():
    """Loop infinito que ejecuta seguimientos cada 30 segundos."""
    while True:
        try:
            await job_seguimientos_programados()
        except Exception as e:
            logger.error(f"Error en loop de seguimientos: {e}", exc_info=False)

        await asyncio.sleep(30)


async def task_seguimiento_mismo_dia_loop():
    """Ejecuta seguimiento mismo día a las 15:00 (3 PM)."""
    while True:
        try:
            ahora = datetime.now(TZ)
            if ahora.hour == 15 and ahora.minute == 0:
                await job_seguimiento_mismo_dia()
                await asyncio.sleep(60)  # Esperar un minuto para no repetir
            else:
                await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error en loop de mismo día: {e}", exc_info=False)


async def task_seguimiento_1dia_loop():
    """Ejecuta seguimiento 1 día a las 10:00 AM."""
    while True:
        try:
            ahora = datetime.now(TZ)
            if ahora.hour == 10 and ahora.minute == 0:
                await job_seguimiento_1dia()
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error en loop de 1 día: {e}", exc_info=False)


async def task_seguimiento_3dias_loop():
    """Ejecuta seguimiento 3 días a las 14:00 (2 PM)."""
    while True:
        try:
            ahora = datetime.now(TZ)
            if ahora.hour == 14 and ahora.minute == 0:
                await job_seguimiento_3dias()
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error en loop de 3 días: {e}", exc_info=False)


async def task_promo_domingo_loop():
    """Ejecuta promos domingo a las 16:00 (4 PM) solo los domingos."""
    while True:
        try:
            ahora = datetime.now(TZ)
            es_domingo = ahora.weekday() == 6
            if es_domingo and ahora.hour == 16 and ahora.minute == 0:
                await job_promo_domingo()
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error en loop de promo domingo: {e}", exc_info=False)


async def task_encuesta_post_venta_loop():
    """Ejecuta encuesta post-venta cada hora a :15."""
    while True:
        try:
            ahora = datetime.now(TZ)
            if ahora.minute == 15:
                await job_encuesta_post_venta()
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error en loop de encuesta: {e}", exc_info=False)


def crear_background_tasks() -> list:
    """Retorna lista de tasks para crear en FastAPI lifespan."""
    return [
        asyncio.create_task(task_seguimientos_programados_loop()),
        asyncio.create_task(task_seguimiento_mismo_dia_loop()),
        asyncio.create_task(task_seguimiento_1dia_loop()),
        asyncio.create_task(task_seguimiento_3dias_loop()),
        asyncio.create_task(task_promo_domingo_loop()),
        asyncio.create_task(task_encuesta_post_venta_loop()),
    ]


def cancelar_background_tasks(tasks: list):
    """Cancela todas las background tasks."""
    for task in tasks:
        if not task.done():
            task.cancel()
