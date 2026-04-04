# agent/scheduler.py — Scheduler para seguimientos automáticos
# Generado por AgentKit

"""
Ejecuta tareas automáticas en background:
- Seguimiento a clientes 1 día después de contacto
- Seguimiento a clientes 3 días después de contacto
- Recordatorio de promo cada domingo (solo si hay carrito abandonado)
"""

import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from agent.memory import (
    obtener_leads_sin_respuesta_1dia,
    obtener_leads_sin_respuesta_3dias,
    marcar_seguimiento_1dia,
    marcar_seguimiento_3dias,
    obtener_carritos_pendientes,
    marcar_carrito_recordatorio_enviado,
)
from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit.scheduler")

scheduler = BackgroundScheduler(timezone=pytz.timezone('America/Asuncion'))
proveedor = obtener_proveedor()


async def job_seguimiento_1dia():
    """Envía recordatorio a leads que no respondieron en 1 día."""
    try:
        logger.info("📅 Ejecutando: Seguimiento 1 día")
        leads = await obtener_leads_sin_respuesta_1dia()

        if not leads:
            logger.debug("No hay leads con seguimiento 1 día pendiente")
            return

        for lead in leads:
            mensaje = (
                f"Hola {lead.nombre or 'che'}! Volvimos a pensar en vos.\n"
                f"¿Alguna duda con los productos? Seguimos aquí para ayudarte.\n"
                f"Escribí cuando quieras."
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
    """Envía recordatorio a leads que no respondieron en 3 días."""
    try:
        logger.info("📅 Ejecutando: Seguimiento 3 días")
        leads = await obtener_leads_sin_respuesta_3dias()

        if not leads:
            logger.debug("No hay leads con seguimiento 3 días pendiente")
            return

        for lead in leads:
            mensaje = (
                f"Hola de nuevo! No queremos que te pierdas estos productos.\n"
                f"Si tenés dudas específicas o necesitás algo especial, contáctate con nuestro equipo comercial:\n"
                f"+595 993 233333\n"
                f"Estamos acá para ayudarte."
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
    """Envía promos y recordatorios de carrito cada domingo."""
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
                f"Domengo especial en Rebody!\n"
                f"Te acordás de esto que querías?\n\n"
                f"{productos_texto}\n\n"
                f"¿Todavía te interesa? Hagamos tu pedido hoy.\n"
                f"Escribí si querés."
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


def inicializar_scheduler():
    """Inicializa el scheduler con las tareas automáticas."""
    try:
        # Job 1: Seguimiento 1 día - todos los días a las 12:00 PM
        scheduler.add_job(
            job_seguimiento_1dia,
            CronTrigger(hour=12, minute=0, timezone='America/Asuncion'),
            id='seguimiento_1dia',
            name='Seguimiento 1 día',
            replace_existing=True
        )
        logger.info("✓ Job 'Seguimiento 1 día' programado (12:00 PM)")

        # Job 2: Seguimiento 3 días - todos los días a las 12:00 PM
        scheduler.add_job(
            job_seguimiento_3dias,
            CronTrigger(hour=12, minute=0, timezone='America/Asuncion'),
            id='seguimiento_3dias',
            name='Seguimiento 3 días',
            replace_existing=True
        )
        logger.info("✓ Job 'Seguimiento 3 días' programado (12:00 PM)")

        # Job 3: Promo domingo - todos los domingos a las 16:00 (4 PM)
        scheduler.add_job(
            job_promo_domingo,
            CronTrigger(day_of_week=6, hour=16, minute=0, timezone='America/Asuncion'),
            id='promo_domingo',
            name='Promos domingo',
            replace_existing=True
        )
        logger.info("✓ Job 'Promos domingo' programado (domingo 4:00 PM)")

        # Iniciar el scheduler
        if not scheduler.running:
            scheduler.start()
            logger.info("✓ Scheduler iniciado")

    except Exception as e:
        logger.error(f"Error inicializando scheduler: {e}")


def detener_scheduler():
    """Detiene el scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("✓ Scheduler detenido")
