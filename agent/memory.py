# agent/memory.py — Memoria de conversaciones con SQLite
# Generado por AgentKit

"""
Sistema de memoria del agente Belén.
Guarda el historial de conversaciones por número de teléfono usando SQLite.
Para producción, puede migrarse fácilmente a PostgreSQL (misma interfaz SQLAlchemy).
"""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer, desc
from dotenv import load_dotenv

load_dotenv()

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

# Si es PostgreSQL en producción, ajustar el esquema de URL
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Crear engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Cambiar a True para debug
    pool_pre_ping=True,  # Verificar conexión antes de usar
)

# Factory de sesiones
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    """Base para todos los modelos SQLAlchemy."""
    pass


class Mensaje(Base):
    """Modelo de mensaje en la base de datos."""
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)  # Índice para búsquedas rápidas
    role: Mapped[str] = mapped_column(String(20))  # "user" o "assistant"
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<Mensaje {self.telefono} - {self.role} - {self.timestamp}>"


class Lead(Base):
    """Modelo de lead para seguimiento de clientes."""
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True, unique=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=True)
    primer_contacto: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ultimo_mensaje: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    fue_cliente: Mapped[bool] = mapped_column(default=False)  # Si compró
    seguimiento_1dia_enviado: Mapped[bool] = mapped_column(default=False)
    seguimiento_3dias_enviado: Mapped[bool] = mapped_column(default=False)

    def __repr__(self):
        return f"<Lead {self.telefono} - {self.primer_contacto}>"


class CarritoAbandonado(Base):
    """Modelo para rastrear carritos abandonados."""
    __tablename__ = "carritos_abandonados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    producto: Mapped[str] = mapped_column(String(200))
    precio: Mapped[str] = mapped_column(String(50))
    fecha_abandono: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    recordatorio_enviado: Mapped[bool] = mapped_column(default=False)

    def __repr__(self):
        return f"<Carrito {self.telefono} - {self.producto}>"


async def inicializar_db():
    """Crea las tablas si no existen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def guardar_mensaje(telefono: str, role: str, content: str):
    """
    Guarda un mensaje en el historial de conversación.

    Args:
        telefono: Número de teléfono del cliente
        role: "user" o "assistant"
        content: Contenido del mensaje
    """
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    """
    Recupera los últimos N mensajes de una conversación en orden cronológico.

    Args:
        telefono: Número de teléfono del cliente
        limite: Máximo de mensajes a recuperar (default: 20, suficiente para contexto)

    Returns:
        Lista de diccionarios con rol y contenido: [{"role": "user", "content": "..."}, ...]
    """
    async with async_session() as session:
        # Consultar últimos N mensajes ordenados por timestamp descendente
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(desc(Mensaje.timestamp))  # Más recientes primero
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()

        # Invertir para orden cronológico (antiguos → recientes)
        mensajes.reverse()

        # Retornar en formato compatible con Claude API
        return [
            {
                "role": msg.role,
                "content": msg.content
            }
            for msg in mensajes
        ]


async def limpiar_historial(telefono: str):
    """
    Borra todo el historial de una conversación.
    Útil para testing o para resetear una conversación.

    Args:
        telefono: Número de teléfono del cliente
    """
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        mensajes = result.scalars().all()

        for msg in mensajes:
            session.delete(msg)

        await session.commit()


async def obtener_estadisticas(telefono: str) -> dict:
    """
    Obtiene estadísticas de una conversación.

    Args:
        telefono: Número de teléfono del cliente

    Returns:
        Diccionario con stats: total_mensajes, mensajes_usuario, mensajes_agente, primera_msg, ultima_msg
    """
    async with async_session() as session:
        # Total de mensajes
        total_query = select(Mensaje).where(Mensaje.telefono == telefono)
        total_result = await session.execute(total_query)
        todos = total_result.scalars().all()

        # Contar por rol
        user_msgs = [m for m in todos if m.role == "user"]
        assistant_msgs = [m for m in todos if m.role == "assistant"]

        if not todos:
            return {
                "telefono": telefono,
                "total_mensajes": 0,
                "mensajes_usuario": 0,
                "mensajes_agente": 0,
                "primera_msg": None,
                "ultima_msg": None
            }

        return {
            "telefono": telefono,
            "total_mensajes": len(todos),
            "mensajes_usuario": len(user_msgs),
            "mensajes_agente": len(assistant_msgs),
            "primera_msg": min(todos, key=lambda m: m.timestamp).timestamp,
            "ultima_msg": max(todos, key=lambda m: m.timestamp).timestamp
        }


# ════════════════════════════════════════════════════════════
# FUNCIONES PARA LEADS Y SEGUIMIENTO
# ════════════════════════════════════════════════════════════

async def registrar_lead(telefono: str, nombre: str = "") -> Lead:
    """Registra un nuevo lead cuando contacta por primera vez."""
    async with async_session() as session:
        # Verificar si ya existe
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead_existente = result.scalar_one_or_none()

        if lead_existente:
            # Actualizar último mensaje
            lead_existente.ultimo_mensaje = datetime.utcnow()
            await session.commit()
            return lead_existente

        # Crear nuevo lead
        nuevo_lead = Lead(
            telefono=telefono,
            nombre=nombre,
            primer_contacto=datetime.utcnow(),
            ultimo_mensaje=datetime.utcnow()
        )
        session.add(nuevo_lead)
        await session.commit()
        return nuevo_lead


async def obtener_leads_sin_respuesta_1dia() -> list[Lead]:
    """Obtiene leads que contactaron hace 1 día y no respondieron."""
    async with async_session() as session:
        hace_1_dia = datetime.utcnow() - __import__('datetime').timedelta(days=1)

        query = (
            select(Lead)
            .where(Lead.ultimo_mensaje <= hace_1_dia)
            .where(Lead.ultimo_mensaje > hace_1_dia - __import__('datetime').timedelta(hours=2))
            .where(Lead.seguimiento_1dia_enviado == False)
            .where(Lead.fue_cliente == False)
        )
        result = await session.execute(query)
        return result.scalars().all()


async def obtener_leads_sin_respuesta_3dias() -> list[Lead]:
    """Obtiene leads que contactaron hace 3 días y no respondieron."""
    async with async_session() as session:
        hace_3_dias = datetime.utcnow() - __import__('datetime').timedelta(days=3)

        query = (
            select(Lead)
            .where(Lead.ultimo_mensaje <= hace_3_dias)
            .where(Lead.ultimo_mensaje > hace_3_dias - __import__('datetime').timedelta(hours=2))
            .where(Lead.seguimiento_3dias_enviado == False)
            .where(Lead.fue_cliente == False)
        )
        result = await session.execute(query)
        return result.scalars().all()


async def marcar_seguimiento_1dia(telefono: str):
    """Marca que se envió seguimiento de 1 día."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.seguimiento_1dia_enviado = True
            await session.commit()


async def marcar_seguimiento_3dias(telefono: str):
    """Marca que se envió seguimiento de 3 días."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.seguimiento_3dias_enviado = True
            await session.commit()


async def registrar_carrito_abandonado(telefono: str, producto: str, precio: str):
    """Registra un producto abandonado en carrito."""
    async with async_session() as session:
        carrito = CarritoAbandonado(
            telefono=telefono,
            producto=producto,
            precio=precio,
            fecha_abandono=datetime.utcnow()
        )
        session.add(carrito)
        await session.commit()


async def obtener_carritos_pendientes() -> list[CarritoAbandonado]:
    """Obtiene carritos abandonados que aún no recibieron recordatorio."""
    async with async_session() as session:
        query = select(CarritoAbandonado).where(CarritoAbandonado.recordatorio_enviado == False)
        result = await session.execute(query)
        return result.scalars().all()


async def marcar_carrito_recordatorio_enviado(carrito_id: int):
    """Marca que se envió recordatorio de carrito abandonado."""
    async with async_session() as session:
        query = select(CarritoAbandonado).where(CarritoAbandonado.id == carrito_id)
        result = await session.execute(query)
        carrito = result.scalar_one_or_none()
        if carrito:
            carrito.recordatorio_enviado = True
            await session.commit()
