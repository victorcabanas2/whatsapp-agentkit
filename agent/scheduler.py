# agent/scheduler.py — Tareas de background 100% async
# Generado por AgentKit

"""
Ejecuta tareas automáticas en background usando asyncio (sin APScheduler):
- Seguimiento unificado (reemplaza mismo_dia + 1dia + 3dias + pendientes)
- Recordatorio de promo cada domingo
- Seguimientos programados dinámicamente por el cliente ("escríbeme en 4 minutos")

VENTAJA: 100% async, sin conflictos de event loops, sin threads de APScheduler.
"""

import logging
import asyncio
from datetime import datetime
import pytz

from agent.memory import (
    # Sistema unificado
    obtener_leads_para_seguimiento_unificado,
    marcar_seguimiento_enviado,
    actualizar_fecha_ultimo_seguimiento,
    # Domingo y encuesta (sin cambios)
    obtener_leads_para_seguimiento_domingo,
    obtener_carritos_pendientes,
    marcar_carrito_recordatorio_enviado,
    obtener_pedidos_sin_encuesta,
    marcar_encuesta_enviada,
    obtener_seguimientos_programados,
    marcar_seguimiento_programado_enviado,
    obtener_historial,
)
from agent.brain import generar_mensaje_seguimiento_contextual
from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit.scheduler")
proveedor = obtener_proveedor()
TZ = pytz.timezone('America/Asuncion')


# ════════════════════════════════════════════════════════════════
# FUNCIONES ASYNC — Cada una es una tarea independiente
# ════════════════════════════════════════════════════════════════

async def job_seguimiento_unificado():
    """
    Job único que reemplaza mismo_dia + 1dia + 3dias + pendientes.

    Envía el próximo seguimiento (1, 2 o 3) a todos los leads elegibles.
    Solo marca DESPUÉS de confirmar envío exitoso.
    Resiste reinicios de Railway: el estado vive en la DB, no en memoria.
    """
    try:
        leads = await obtener_leads_para_seguimiento_unificado()
        if not leads:
            logger.debug("No hay leads elegibles para seguimiento")
            return
        logger.info(f"📋 {len(leads)} leads elegibles para seguimiento")
        for lead in leads:
            historial = await obtener_historial(lead.telefono, limite=20)
            numero_seguimiento = lead.seguimientos_enviados + 1  # 1, 2 o 3
            tipo = f"seguimiento_{numero_seguimiento}"
            mensaje = await generar_mensaje_seguimiento_contextual(lead, historial, tipo)
            if mensaje is None:
                # Claude decidió no enviar — actualizar timestamp para no re-consultar en 20h
                await actualizar_fecha_ultimo_seguimiento(lead.telefono)
                logger.info(f"🚫 Seguimiento {numero_seguimiento} omitido → {lead.telefono}")
                continue
            exito = await proveedor.enviar_mensaje(lead.telefono, mensaje)
            if exito:
                await marcar_seguimiento_enviado(lead.telefono)  # solo marca si fue exitoso
                logger.info(f"✓ Seguimiento {numero_seguimiento}/3 enviado → {lead.telefono}")
            else:
                logger.error(f"✗ Fallo envío seguimiento {numero_seguimiento} → {lead.telefono}")
    except Exception as e:
        logger.error(f"Error en job_seguimiento_unificado: {e}", exc_info=False)


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


async def job_seguimiento_domingo():
    """Seguimiento dominical contextual con Claude."""
    try:
        logger.info("📅 Ejecutando: Seguimiento DOMINGO")
        leads = await obtener_leads_para_seguimiento_domingo()
        if not leads:
            logger.debug("No hay leads para seguimiento dominical")
            return
        logger.info(f"📋 {len(leads)} leads candidatos para seguimiento domingo")
        for lead in leads:
            historial = await obtener_historial(lead.telefono, limite=20)
            mensaje = await generar_mensaje_seguimiento_contextual(lead, historial, "domingo")
            if mensaje is None:
                logger.info(f"🚫 Seguimiento domingo omitido → {lead.telefono}")
                continue
            exito = await proveedor.enviar_mensaje(lead.telefono, mensaje)
            if exito:
                logger.info(f"✓ Seguimiento domingo enviado → {lead.telefono}")
            else:
                logger.error(f"✗ Fallo envío domingo → {lead.telefono}")
    except Exception as e:
        logger.error(f"Error en job_seguimiento_domingo: {e}", exc_info=False)


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
                    f"Hola{', ' + seg.nombre if seg.nombre else ''}! 👋\n\n"
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


async def task_seguimiento_unificado_loop():
    """Loop unificado cada 30 minutos. Reemplaza mismo_dia, pendientes, 15h."""
    while True:
        try:
            await job_seguimiento_unificado()
        except Exception as e:
            logger.error(f"Error en loop unificado: {e}", exc_info=False)
        await asyncio.sleep(1800)  # 30 minutos


async def task_promo_domingo_loop():
    """Ejecuta seguimiento dominical a las 14:00 Paraguay todos los domingos."""
    ultimo_domingo_ejecutado = None
    while True:
        try:
            ahora = datetime.now(TZ)
            es_domingo = ahora.weekday() == 6
            hoy = ahora.date()
            if es_domingo and ahora.hour == 14 and ahora.minute < 30 and hoy != ultimo_domingo_ejecutado:
                logger.info("⏰ Domingo 14:00 — ejecutando seguimiento dominical")
                await job_seguimiento_domingo()     # job dominical
                ultimo_domingo_ejecutado = hoy
                await asyncio.sleep(1800)
            else:
                await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Error en loop domingo: {e}", exc_info=False)
            await asyncio.sleep(60)


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
        asyncio.create_task(task_seguimiento_unificado_loop()),
        asyncio.create_task(task_promo_domingo_loop()),
        asyncio.create_task(task_encuesta_post_venta_loop()),
    ]


def cancelar_background_tasks(tasks: list):
    """Cancela todas las background tasks."""
    for task in tasks:
        if not task.done():
            task.cancel()
