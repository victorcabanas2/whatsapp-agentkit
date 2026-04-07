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
from sqlalchemy import String, Text, DateTime, select, Integer, desc, Boolean
from dotenv import load_dotenv
from datetime import timedelta

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

    # Clientes antiguos (previos a AgentKit)
    es_cliente_previo: Mapped[bool] = mapped_column(default=False)
    productos_comprados_previos: Mapped[str] = mapped_column(Text, nullable=True)
    historial_previo_resumen: Mapped[str] = mapped_column(Text, nullable=True)

    seguimiento_1dia_enviado: Mapped[bool] = mapped_column(default=False)
    seguimiento_3dias_enviado: Mapped[bool] = mapped_column(default=False)
    en_manos_humanas: Mapped[bool] = mapped_column(default=False)  # Bot pausa si True

    # Lead Scoring
    score: Mapped[int] = mapped_column(Integer, default=20)  # 0-100
    intencion: Mapped[str] = mapped_column(String(10), default="cold")  # cold/warm/hot
    urgencia: Mapped[str] = mapped_column(String(10), default="baja")  # baja/media/alta
    producto_preferido: Mapped[str] = mapped_column(String(200), nullable=True)
    presupuesto_estimado: Mapped[str] = mapped_column(String(100), nullable=True)
    objeciones: Mapped[str] = mapped_column(Text, nullable=True)
    proximo_followup: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    alerta_vendedor_enviada: Mapped[bool] = mapped_column(default=False)

    def __repr__(self):
        return f"<Lead {self.telefono} - {self.intencion} - {self.primer_contacto}>"


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


class Pedido(Base):
    """Modelo para pedidos confirmados y completados."""
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    producto: Mapped[str] = mapped_column(String(200))  # Nombre del producto
    precio: Mapped[str] = mapped_column(String(50))     # Precio en Gs
    metodo_pago: Mapped[str] = mapped_column(String(100))  # transferencia, efectivo, pagopar, qr

    # Datos de envío
    nombre_cliente: Mapped[str] = mapped_column(String(100), nullable=True)
    direccion_envio: Mapped[str] = mapped_column(Text, nullable=True)
    ciudad_departamento: Mapped[str] = mapped_column(String(100), nullable=True)
    telefono_contacto: Mapped[str] = mapped_column(String(50), nullable=True)

    # Datos de factura
    ruc_cedula: Mapped[str] = mapped_column(String(50), nullable=True)
    razon_social: Mapped[str] = mapped_column(String(100), nullable=True)

    # Estado del pedido
    fecha_pedido: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    estado: Mapped[str] = mapped_column(String(50), default="pendiente")  # pendiente, pagado, entregado
    confirmacion_enviada: Mapped[bool] = mapped_column(default=False)

    def __repr__(self):
        return f"<Pedido {self.telefono} - {self.producto} - {self.estado}>"


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


# ════════════════════════════════════════════════════════════
# FUNCIONES PARA PEDIDOS
# ════════════════════════════════════════════════════════════

async def guardar_pedido(
    telefono: str,
    producto: str,
    precio: str,
    metodo_pago: str,
    nombre_cliente: str = "",
    direccion_envio: str = "",
    ciudad_departamento: str = "",
    telefono_contacto: str = "",
    ruc_cedula: str = "",
    razon_social: str = "",
) -> Pedido:
    """
    Guarda un pedido confirmado en la base de datos.

    Args:
        telefono: Número de teléfono del cliente
        producto: Nombre del producto
        precio: Precio en Guaraní
        metodo_pago: Método de pago (transferencia, efectivo, pagopar, qr)
        nombre_cliente: Nombre del cliente
        direccion_envio: Dirección de envío
        ciudad_departamento: Ciudad o departamento
        telefono_contacto: Teléfono de contacto
        ruc_cedula: RUC o cédula
        razon_social: Razón social

    Returns:
        El pedido guardado
    """
    async with async_session() as session:
        pedido = Pedido(
            telefono=telefono,
            producto=producto,
            precio=precio,
            metodo_pago=metodo_pago,
            nombre_cliente=nombre_cliente,
            direccion_envio=direccion_envio,
            ciudad_departamento=ciudad_departamento,
            telefono_contacto=telefono_contacto,
            ruc_cedula=ruc_cedula,
            razon_social=razon_social,
            estado="pendiente",
            fecha_pedido=datetime.utcnow()
        )
        session.add(pedido)
        await session.commit()
        return pedido


async def obtener_pedidos_cliente(telefono: str) -> list[Pedido]:
    """Obtiene todos los pedidos de un cliente."""
    async with async_session() as session:
        query = select(Pedido).where(Pedido.telefono == telefono).order_by(desc(Pedido.fecha_pedido))
        result = await session.execute(query)
        return result.scalars().all()


async def obtener_ultimo_pedido(telefono: str) -> Pedido | None:
    """Obtiene el último pedido de un cliente."""
    async with async_session() as session:
        query = select(Pedido).where(Pedido.telefono == telefono).order_by(desc(Pedido.fecha_pedido)).limit(1)
        result = await session.execute(query)
        return result.scalar_one_or_none()


async def actualizar_estado_pedido(pedido_id: int, nuevo_estado: str):
    """Actualiza el estado de un pedido (pendiente, pagado, entregado)."""
    async with async_session() as session:
        query = select(Pedido).where(Pedido.id == pedido_id)
        result = await session.execute(query)
        pedido = result.scalar_one_or_none()
        if pedido:
            pedido.estado = nuevo_estado
            await session.commit()


# ════════════════════════════════════════════════════════════
# FUNCIONES PARA LEAD SCORING Y ANÁLISIS
# ════════════════════════════════════════════════════════════

async def actualizar_lead_scoring(
    telefono: str,
    score: int = None,
    intencion: str = None,
    urgencia: str = None,
    producto_preferido: str = None,
    presupuesto_estimado: str = None,
    objeciones: str = None,
    proximo_followup: datetime = None
):
    """
    Actualiza los campos de scoring de un lead.
    Solo actualiza los campos que no son None.
    """
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()

        if lead:
            if score is not None:
                lead.score = max(0, min(100, score))  # Clampear entre 0-100
            if intencion is not None:
                lead.intencion = intencion
            if urgencia is not None:
                lead.urgencia = urgencia
            if producto_preferido is not None:
                lead.producto_preferido = producto_preferido
            if presupuesto_estimado is not None:
                lead.presupuesto_estimado = presupuesto_estimado
            if objeciones is not None:
                lead.objeciones = objeciones
            if proximo_followup is not None:
                lead.proximo_followup = proximo_followup

            await session.commit()


async def obtener_resumen_cliente(telefono: str) -> dict:
    """
    Obtiene un resumen completo del cliente para incluir en el context del agente.

    Returns:
        {
            "pedidos_previos": "2 compras (Theragun Mini en dic 2025, Depuffing Wand en ene 2026)",
            "objeciones": "muy caro, lo pienso",
            "producto_preferido": "Theragun Mini",
            "score": 75,
            "intencion": "warm",
            "urgencia": "media"
        }
    """
    async with async_session() as session:
        # Obtener lead
        lead_query = select(Lead).where(Lead.telefono == telefono)
        lead_result = await session.execute(lead_query)
        lead = lead_result.scalar_one_or_none()

        if not lead:
            return {}

        # Obtener pedidos del cliente
        pedidos_query = select(Pedido).where(Pedido.telefono == telefono).order_by(desc(Pedido.fecha_pedido))
        pedidos_result = await session.execute(pedidos_query)
        pedidos = pedidos_result.scalars().all()

        pedidos_texto = ""
        if pedidos:
            lista_productos = ", ".join([
                f"{p.producto} ({p.fecha_pedido.strftime('%b %Y')})"
                for p in pedidos
            ])
            pedidos_texto = f"{len(pedidos)} compras: {lista_productos}"

        return {
            "pedidos_previos": pedidos_texto,
            "objeciones": lead.objeciones or "",
            "producto_preferido": lead.producto_preferido or "",
            "score": lead.score,
            "intencion": lead.intencion,
            "urgencia": lead.urgencia
        }


async def obtener_lead(telefono: str) -> Lead | None:
    """Obtiene un lead específico por teléfono."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        return result.scalar_one_or_none()


async def obtener_leads_sin_respuesta_horas(horas: int = 4) -> list[dict]:
    """
    Obtiene leads sin respuesta hace más de X horas.

    Un lead sin respuesta es aquel donde el último mensaje en la tabla 'mensajes'
    tiene role='user' (cliente escribió) y hace más de X horas.

    Args:
        horas: Horas sin respuesta (default: 4)

    Returns:
        [{telefono, nombre, ultimo_mensaje, horas_sin_respuesta, score, intencion}, ...]
    """
    async with async_session() as session:
        ahora = datetime.utcnow()
        hace_x_horas = ahora - timedelta(hours=horas)

        # Obtener todos los leads
        leads_query = select(Lead)
        leads_result = await session.execute(leads_query)
        leads = leads_result.scalars().all()

        leads_sin_respuesta = []

        for lead in leads:
            # Obtener último mensaje del cliente en esta conversación
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
                horas_esperando = (ahora - ultimo_msg_cliente.timestamp).total_seconds() / 3600
                leads_sin_respuesta.append({
                    "telefono": lead.telefono,
                    "nombre": lead.nombre or "Sin nombre",
                    "ultimo_mensaje": ultimo_msg_cliente.content[:100],  # Primeros 100 chars
                    "horas_sin_respuesta": int(horas_esperando),
                    "score": lead.score,
                    "intencion": lead.intencion
                })

        return sorted(leads_sin_respuesta, key=lambda x: x["horas_sin_respuesta"], reverse=True)


async def marcar_alerta_vendedor(telefono: str):
    """Marca que se envió alerta de nuevo lead al vendedor."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.alerta_vendedor_enviada = True
            await session.commit()


# ════════════════════════════════════════════════════════════
# CLIENTES ANTIGUOS — Contexto de clientes previos a AgentKit
# ════════════════════════════════════════════════════════════

async def tomar_control(telefono: str) -> bool:
    """Pausa el bot para este cliente — un humano toma control."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.en_manos_humanas = True
            await session.commit()
            return True
        return False


async def liberar_control(telefono: str) -> bool:
    """Reactiva el bot para este cliente."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.en_manos_humanas = False
            await session.commit()
            return True
        return False


async def obtener_contexto_cliente_antiguo(telefono: str) -> dict | None:
    """Obtiene contexto de un cliente antiguo (previo a AgentKit)."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()

        if not lead or not lead.es_cliente_previo:
            return None

        return {
            "nombre": lead.nombre,
            "es_cliente_antiguo": True,
            "productos_comprados": lead.productos_comprados_previos,
            "historial_resumen": lead.historial_previo_resumen
        }


async def marcar_cliente_como_antiguo(telefono: str, nombre: str, productos_comprados: str, historial_resumen: str) -> bool:
    """Marca un cliente como antiguo (cliente previo a AgentKit)."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()

        if not lead:
            lead = Lead(
                telefono=telefono,
                nombre=nombre,
                es_cliente_previo=True,
                fue_cliente=True,
                productos_comprados_previos=productos_comprados,
                historial_previo_resumen=historial_resumen
            )
            session.add(lead)
        else:
            lead.es_cliente_previo = True
            lead.fue_cliente = True
            lead.nombre = nombre or lead.nombre
            lead.productos_comprados_previos = productos_comprados
            lead.historial_previo_resumen = historial_resumen

        await session.commit()
        return True


async def obtener_todos_los_leads() -> list[Lead]:
    """Obtiene la lista de todos los leads registrados."""
    async with async_session() as session:
        query = select(Lead).order_by(desc(Lead.ultimo_mensaje))
        result = await session.execute(query)
        return result.scalars().all()
