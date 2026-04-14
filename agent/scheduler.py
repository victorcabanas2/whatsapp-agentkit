# agent/scheduler.py — Scheduler para seguimientos automáticos
# Generado por AgentKit

"""
Ejecuta tareas automáticas en background:
- Seguimiento a clientes MISMO DÍA de contacto inicial
- Seguimiento a clientes 1 día después de contacto
- Seguimiento a clientes 3 días después de contacto
- Recordatorio de promo cada domingo (solo si hay carrito abandonado)
- Seguimientos programados dinámicamente por el cliente ("escríbeme en 4 minutos")
"""

import logging
import asyncio
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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

scheduler = BackgroundScheduler(timezone=pytz.timezone('America/Asuncion'))
proveedor = obtener_proveedor()


# WRAPPERS SYNC para APScheduler — convierte async → sync
def _sync_wrapper(async_func):
    """Convierte una función async a sync para APScheduler."""
    def wrapper(*args, **kwargs):
        try:
            # Usar asyncio.run() que maneja loops correctamente
            return asyncio.run(async_func(*args, **kwargs))
        except RuntimeError as e:
            # Si hay conflicto de loops, intentar en un nuevo loop
            if "Event loop is closed" in str(e) or "attached to a different loop" in str(e):
                logger.warning(f"⚠️ Loop conflict, retrying with new loop: {e}")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(async_func(*args, **kwargs))
                finally:
                    loop.close()
            raise
    return wrapper


# ════════════════════════════════════════════════════════════════
# JOBS AUTOMÁTICOS — Seguimientos rutinarios
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
        logger.error(f"Error en job_seguimiento_mismo_dia: {e}")


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
        logger.error(f"Error en job_seguimiento_1dia: {e}")


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
        logger.error(f"Error en job_seguimiento_3dias: {e}")


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
        logger.error(f"Error en job_promo_domingo: {e}")


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
        logger.error(f"Error en job_encuesta_post_venta: {e}")


async def job_seguimientos_programados():
    """Envía seguimientos programados dinámicamente (ej: 'escríbeme en 4 minutos')."""
    try:
        logger.info("📅 Ejecutando: Seguimientos programados")
        seguimientos = await obtener_seguimientos_programados()

        if not seguimientos:
            logger.debug("No hay seguimientos programados pendientes")
            return

        for seg in seguimientos:
            mensaje = seg.mensaje_personalizado or (
                f"Hola {seg.nombre or 'che'}! 👋\n\n"
                f"Como te lo prometí, acá estoy.\n\n"
                f"¿Qué te puedo ayudar?"
            )

            exito = await proveedor.enviar_mensaje(seg.telefono, mensaje)
            if exito:
                await marcar_seguimiento_programado_enviado(seg.id)
                logger.info(f"✓ Seguimiento programado enviado a {seg.telefono}")
            else:
                logger.error(f"✗ Fallo envío a {seg.telefono}")

    except Exception as e:
        logger.error(f"Error en job_seguimientos_programados: {e}")


# ════════════════════════════════════════════════════════════════
# INICIALIZACIÓN DEL SCHEDULER
# ════════════════════════════════════════════════════════════════

def inicializar_scheduler():
    """Inicializa el scheduler con todas las tareas automáticas."""
    try:
        # Job 0: Seguimiento MISMO DÍA - 3 horas después del contacto (ejecutar cada hora para buscar)
        scheduler.add_job(
            _sync_wrapper(job_seguimiento_mismo_dia),
            CronTrigger(hour=15, minute=0, timezone='America/Asuncion'),  # 3 PM
            id='seguimiento_mismo_dia',
            name='Seguimiento MISMO DÍA',
            replace_existing=True
        )
        logger.info("✓ Job 'Seguimiento MISMO DÍA' programado (15:00 / 3 PM)")

        # Job 1: Seguimiento 1 día - todos los días a las 10:00 AM
        scheduler.add_job(
            _sync_wrapper(job_seguimiento_1dia),
            CronTrigger(hour=10, minute=0, timezone='America/Asuncion'),
            id='seguimiento_1dia',
            name='Seguimiento 1 día',
            replace_existing=True
        )
        logger.info("✓ Job 'Seguimiento 1 día' programado (10:00 AM)")

        # Job 2: Seguimiento 3 días - todos los días a las 14:00 (2 PM)
        scheduler.add_job(
            _sync_wrapper(job_seguimiento_3dias),
            CronTrigger(hour=14, minute=0, timezone='America/Asuncion'),
            id='seguimiento_3dias',
            name='Seguimiento 3 días',
            replace_existing=True
        )
        logger.info("✓ Job 'Seguimiento 3 días' programado (14:00 / 2 PM)")

        # Job 3: Promo domingo - todos los domingos a las 16:00 (4 PM)
        scheduler.add_job(
            _sync_wrapper(job_promo_domingo),
            CronTrigger(day_of_week=6, hour=16, minute=0, timezone='America/Asuncion'),
            id='promo_domingo',
            name='Promos domingo',
            replace_existing=True
        )
        logger.info("✓ Job 'Promos domingo' programado (domingo 16:00 / 4 PM)")

        # Job 4: Encuesta post-venta - cada hora a las :15
        scheduler.add_job(
            _sync_wrapper(job_encuesta_post_venta),
            CronTrigger(minute=15, timezone='America/Asuncion'),
            id='encuesta_post_venta',
            name='Encuesta post-venta',
            replace_existing=True
        )
        logger.info("✓ Job 'Encuesta post-venta' programado (cada hora a :15)")

        # Job 5: Seguimientos programados dinámicamente - cada 30 segundos (urgente, usuario espera 1-2 min)
        scheduler.add_job(
            _sync_wrapper(job_seguimientos_programados),
            IntervalTrigger(seconds=30),
            id='seguimientos_programados',
            name='Seguimientos programados',
            replace_existing=True
        )
        logger.info("✓ Job 'Seguimientos programados' programado (cada 30 segundos)")

        # Iniciar el scheduler
        if not scheduler.running:
            scheduler.start()
            logger.info("✓✓✓ SCHEDULER INICIADO CORRECTAMENTE ✓✓✓")

    except Exception as e:
        logger.error(f"Error inicializando scheduler: {e}")


def detener_scheduler():
    """Detiene el scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("✓ Scheduler detenido")
