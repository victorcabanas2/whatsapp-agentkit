"""API Admin - Endpoints para dashboard Shopify"""

from sqlalchemy import select, func, desc
from datetime import datetime, timedelta
from agent.memory import async_session, Lead, Pedido, Mensaje


async def obtener_stats():
    """Stats generales del dashboard"""
    async with async_session() as session:
        total_leads = await session.execute(select(func.count(Lead.id)))
        total_leads = total_leads.scalar() or 0

        hot = await session.execute(
            select(func.count(Lead.id)).where(Lead.intencion == "hot")
        )
        hot_leads = hot.scalar() or 0

        hoy = datetime.utcnow().date()
        pedidos_hoy = await session.execute(
            select(func.count(Pedido.id)).where(
                func.cast(Pedido.fecha_pedido, "date") == hoy
            )
        )
        pedidos_hoy = pedidos_hoy.scalar() or 0

        leads_hoy = await session.execute(
            select(func.count(Lead.id)).where(
                func.cast(Lead.primer_contacto, "date") == hoy
            )
        )
        leads_hoy = leads_hoy.scalar() or 0

        total_pedidos = await session.execute(select(func.count(Pedido.id)))
        total_pedidos = total_pedidos.scalar() or 0

        conversion = (pedidos_hoy / leads_hoy * 100) if leads_hoy > 0 else 0

        return {
            "total_leads": total_leads,
            "leads_hoy": leads_hoy,
            "hot_leads": hot_leads,
            "conversion_pct": round(conversion, 1),
            "pedidos_totales": total_pedidos,
            "pedidos_hoy": pedidos_hoy,
            "pedidos_pendientes": 0,
            "sin_respuesta_2h": 0,
        }


async def obtener_leads(estado="todos", limite=500):
    """Leads con filtros"""
    async with async_session() as session:
        query = select(Lead).order_by(desc(Lead.ultimo_mensaje)).limit(limite)

        if estado != "todos":
            query = query.where(Lead.intencion == estado)

        result = await session.execute(query)
        leads = result.scalars().all()

        return [
            {
                "id": str(l.id),
                "telefono": l.telefono,
                "nombre": l.nombre or "Sin nombre",
                "primer_contacto": l.primer_contacto.isoformat(),
                "ultimo_mensaje": l.ultimo_mensaje.isoformat() if l.ultimo_mensaje else None,
                "fue_cliente": l.fue_cliente,
                "score": l.score,
                "intencion": l.intencion,
                "producto_preferido": l.producto_preferido,
            }
            for l in leads
        ]


async def obtener_pedidos(estado="todos", limite=100):
    """Pedidos con filtros"""
    async with async_session() as session:
        query = select(Pedido).order_by(desc(Pedido.fecha_pedido)).limit(limite)

        if estado != "todos":
            query = query.where(Pedido.estado == estado)

        result = await session.execute(query)
        pedidos = result.scalars().all()

        return [
            {
                "id": str(p.id),
                "telefono": p.telefono,
                "producto": p.producto,
                "precio": p.precio,
                "metodo_pago": p.metodo_pago,
                "estado": p.estado,
                "fecha_pedido": p.fecha_pedido.isoformat(),
            }
            for p in pedidos
        ]


async def obtener_mensajes_sin_respuesta(horas=2):
    """Leads sin respuesta en X horas"""
    async with async_session() as session:
        cutoff = datetime.utcnow() - timedelta(hours=horas)
        result = await session.execute(
            select(Lead).where(Lead.ultimo_mensaje < cutoff).limit(20)
        )
        return [
            {
                "telefono": l.telefono,
                "nombre": l.nombre,
                "ultimo_mensaje": l.ultimo_mensaje.isoformat() if l.ultimo_mensaje else None,
            }
            for l in result.scalars().all()
        ]
