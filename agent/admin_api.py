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

        return {
            "total_leads": total_leads,
            "leads_hoy": leads_hoy,
            "conversion_pct": conversion,
            "pedidos_totales": total_pedidos,
            "pedidos_hoy": pedidos_hoy,
        }


async def obtener_leads(estado="todos", limite=10):
    """Retorna lista de leads filtrados."""
    async with async_session() as session:
        query = select(Lead).order_by(desc(Lead.ultimo_mensaje))

        if estado == "nuevos":
            hoy = datetime.utcnow().date()
            query = query.where(func.date(Lead.primer_contacto) == hoy)
        elif estado == "sin_responder":
            hace_2h = datetime.utcnow() - timedelta(hours=2)
            query = query.where(Lead.ultimo_mensaje < hace_2h)

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
