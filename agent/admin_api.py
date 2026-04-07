# agent/admin_api.py — Endpoints de Admin Dashboard

import logging
from datetime import datetime, timedelta
from sqlalchemy import select, desc, func
from agent.memory import async_session, Lead, Pedido, Mensaje

logger = logging.getLogger("agentkit")


async def obtener_stats():
    """Retorna estadísticas generales del bot."""
    async with async_session() as session:
        # Total de leads
        query_leads = select(func.count(Lead.id))
        result = await session.execute(query_leads)
        total_leads = result.scalar() or 0

        # Leads nuevos hoy
        hoy = datetime.utcnow().date()
        query_hoy = select(func.count(Lead.id)).where(
            func.date(Lead.primer_contacto) == hoy
        )
        result = await session.execute(query_hoy)
        leads_hoy = result.scalar() or 0

        # Hot leads (intencion = "hot")
        query_hot = select(func.count(Lead.id)).where(Lead.intencion == "hot")
        result = await session.execute(query_hot)
        hot_leads = result.scalar() or 0

        # Pedidos pagados (conversiones)
        query_pedidos = select(func.count(Pedido.id)).where(Pedido.estado == "pagado")
        result = await session.execute(query_pedidos)
        total_pedidos = result.scalar() or 0

        # Conversión %
        conversion = round((total_pedidos / total_leads * 100) if total_leads > 0 else 0, 1)

        # Pedidos hoy
        query_pedidos_hoy = select(func.count(Pedido.id)).where(
            func.date(Pedido.fecha_pedido) == hoy,
            Pedido.estado == "pagado"
        )
        result = await session.execute(query_pedidos_hoy)
        pedidos_hoy = result.scalar() or 0

        # Pedidos pendientes de pago
        query_pendientes = select(func.count(Pedido.id)).where(Pedido.estado == "pendiente")
        result = await session.execute(query_pendientes)
        pedidos_pendientes = result.scalar() or 0

        # Leads sin respuesta hace >2h
        hace_2h = datetime.utcnow() - timedelta(hours=2)
        query_sin_respuesta = select(func.count(Lead.id)).where(
            Lead.ultimo_mensaje < hace_2h
        )
        result = await session.execute(query_sin_respuesta)
        sin_respuesta_2h = result.scalar() or 0

        return {
            "total_leads": total_leads,
            "leads_hoy": leads_hoy,
            "hot_leads": hot_leads,
            "conversion_pct": conversion,
            "pedidos_totales": total_pedidos,
            "pedidos_hoy": pedidos_hoy,
            "pedidos_pendientes": pedidos_pendientes,
            "sin_respuesta_2h": sin_respuesta_2h,
        }


async def obtener_leads(estado="todos", limite=10):
    """Retorna lista de leads filtrados con score e intención."""
    async with async_session() as session:
        query = select(Lead).order_by(desc(Lead.ultimo_mensaje))

        if estado == "nuevos":
            hoy = datetime.utcnow().date()
            query = query.where(func.date(Lead.primer_contacto) == hoy)
        elif estado == "sin_responder":
            hace_2h = datetime.utcnow() - timedelta(hours=2)
            query = query.where(Lead.ultimo_mensaje < hace_2h)
        elif estado == "hot":
            query = query.where(Lead.intencion == "hot")

        query = query.limit(limite)
        result = await session.execute(query)
        leads = result.scalars().all()

        return [
            {
                "id": lead.id,
                "telefono": lead.telefono,
                "nombre": lead.nombre or "Sin nombre",
                "primer_contacto": lead.primer_contacto.isoformat(),
                "ultimo_mensaje": lead.ultimo_mensaje.isoformat(),
                "fue_cliente": lead.fue_cliente,
                "score": lead.score,
                "intencion": lead.intencion,
                "producto_preferido": lead.producto_preferido or "—",
            }
            for lead in leads
        ]


async def obtener_pedidos(estado="todos", limite=10):
    """Retorna lista de pedidos filtrados."""
    async with async_session() as session:
        query = select(Pedido).order_by(desc(Pedido.fecha_pedido))

        if estado != "todos":
            query = query.where(Pedido.estado == estado)

        query = query.limit(limite)
        result = await session.execute(query)
        pedidos = result.scalars().all()

        return [
            {
                "id": pedido.id,
                "telefono": pedido.telefono,
                "producto": pedido.producto,
                "precio": pedido.precio,
                "metodo_pago": pedido.metodo_pago,
                "estado": pedido.estado,
                "fecha_pedido": pedido.fecha_pedido.isoformat(),
            }
            for pedido in pedidos
        ]


async def obtener_mensajes_sin_respuesta(horas=2, limite=10):
    """
    Retorna leads sin respuesta hace más de X horas.
    Un lead sin respuesta es aquel donde el último mensaje es 'user' (cliente escribió)
    y fue hace más de X horas.
    """
    async with async_session() as session:
        hace_x_horas = datetime.utcnow() - timedelta(hours=horas)

        # Obtener todos los leads
        query_leads = select(Lead).order_by(desc(Lead.ultimo_mensaje))
        result = await session.execute(query_leads)
        todos_leads = result.scalars().all()

        leads_sin_respuesta = []

        for lead in todos_leads:
            # Obtener último mensaje del cliente
            msg_query = (
                select(Mensaje)
                .where(Mensaje.telefono == lead.telefono)
                .where(Mensaje.role == "user")
                .order_by(desc(Mensaje.timestamp))
                .limit(1)
            )
            msg_result = await session.execute(msg_query)
            ultimo_msg_cliente = msg_result.scalar_one_or_none()

            if ultimo_msg_cliente and ultimo_msg_cliente.timestamp < hace_x_horas:
                horas_esperando = (datetime.utcnow() - ultimo_msg_cliente.timestamp).total_seconds() / 3600
                leads_sin_respuesta.append({
                    "telefono": lead.telefono,
                    "nombre": lead.nombre or "Sin nombre",
                    "ultimo_mensaje": ultimo_msg_cliente.content[:100],
                    "horas_sin_respuesta": int(horas_esperando),
                    "score": lead.score,
                    "intencion": lead.intencion,
                    "timestamp_ultimo_msg": ultimo_msg_cliente.timestamp.isoformat(),
                })

        # Retornar ordenados por más tiempo esperando
        leads_sin_respuesta.sort(key=lambda x: x["horas_sin_respuesta"], reverse=True)
        return leads_sin_respuesta[:limite]
