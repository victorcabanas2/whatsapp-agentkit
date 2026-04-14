"""Endpoints para dashboard admin - Belén"""

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_
from datetime import datetime, timedelta
import json

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def get_stats(db: AsyncSession):
    """Stats generales del bot"""
    from agent.models import Lead, Pedido, Mensaje

    # Total leads
    total_leads = await db.execute(select(func.count(Lead.id)))
    total_leads = total_leads.scalar() or 0

    # Leads hoy
    hoy = datetime.now().date()
    leads_hoy = await db.execute(
        select(func.count(Lead.id)).where(func.cast(Lead.fecha_creacion, "date") == hoy)
    )
    leads_hoy = leads_hoy.scalar() or 0

    # Pedidos hoy
    pedidos_hoy = await db.execute(
        select(func.count(Pedido.id)).where(func.cast(Pedido.fecha_creacion, "date") == hoy)
    )
    pedidos_hoy = pedidos_hoy.scalar() or 0

    # Conversión
    conversion = (pedidos_hoy / leads_hoy * 100) if leads_hoy > 0 else 0

    return {
        "total_leads": total_leads,
        "leads_hoy": leads_hoy,
        "pedidos_hoy": pedidos_hoy,
        "conversion_pct": round(conversion, 1)
    }


async def get_leads(db: AsyncSession, limite: int = 50):
    """Últimos leads"""
    from agent.models import Lead

    query = select(Lead).order_by(desc(Lead.fecha_creacion)).limit(limite)
    result = await db.execute(query)
    leads = result.scalars().all()

    return [
        {
            "telefono": lead.telefono,
            "nombre": lead.nombre or "Sin nombre",
            "primer_contacto": lead.fecha_creacion.isoformat(),
            "ultimo_mensaje": lead.ultimo_mensaje.isoformat() if lead.ultimo_mensaje else None,
            "estado": lead.estado or "nuevo"
        }
        for lead in leads
    ]


async def get_pedidos(db: AsyncSession, limite: int = 50):
    """Últimos pedidos"""
    from agent.models import Pedido

    query = select(Pedido).order_by(desc(Pedido.fecha_creacion)).limit(limite)
    result = await db.execute(query)
    pedidos = result.scalars().all()

    return [
        {
            "telefono": pedido.telefono,
            "producto": pedido.producto,
            "precio": pedido.precio,
            "metodo_pago": pedido.metodo_pago or "Sin especificar",
            "estado": pedido.estado or "pendiente",
            "fecha": pedido.fecha_creacion.isoformat()
        }
        for pedido in pedidos
    ]
