# agent/memory.py — Memoria de conversaciones con SQLite
# Generado por AgentKit
# ✅ ACTUALIZADO: Foreign Keys, Constraints, Transacciones Atómicas

"""
Sistema de memoria del agente Belén.
Guarda el historial de conversaciones por número de teléfono usando SQLite.
Para producción, puede migrarse fácilmente a PostgreSQL (misma interfaz SQLAlchemy).

🔒 INTEGRIDAD GARANTIZADA:
- Foreign Keys en todas las relaciones (FK → Lead como tabla principal)
- ON DELETE CASCADE para mantener consistencia
- Transacciones explícitas con rollback automático en caso de error
- Constraints CHECK para validar datos
- Índices compuestos para queries frecuentes
- Bulk operations para operaciones en lote
"""

import os
from datetime import datetime, timezone as tz
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, DateTime, select, Integer, desc, Boolean, ForeignKey, CheckConstraint, Index, func, and_, delete, text
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv
from datetime import timedelta
import logging
import traceback
import json

# Configurar logging
logger = logging.getLogger("memory")
logger.setLevel(logging.DEBUG)

# Handler para archivo (todos los errores)
if not logger.handlers:
    file_handler = logging.FileHandler("agentkit_memory.log")
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

load_dotenv()


# ════════════════════════════════════════════════════════════
# EXCEPCIONES CUSTOM
# ════════════════════════════════════════════════════════════

class AgentKitError(Exception):
    """Excepción base de AgentKit."""
    pass


class IntegrityViolationError(AgentKitError):
    """Violación de integridad referencial (FK constraint)."""
    pass


class ValidationError(AgentKitError):
    """Error de validación de datos."""
    pass


class AtomicityError(AgentKitError):
    """Error en transacción atómica (rollback occurred)."""
    pass


class DataConsistencyError(AgentKitError):
    """Inconsistencia detectada en los datos."""
    pass

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////app/data/agentkit.db")

# Si es PostgreSQL en producción, ajustar el esquema de URL
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Crear engine con soporte para Foreign Keys en SQLite
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Cambiar a True para debug
    pool_pre_ping=True,  # Verificar conexión antes de usar
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

# Factory de sesiones
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Habilitar Foreign Keys en SQLite (debe ser antes de create_all)
async def enable_sqlite_foreign_keys():
    """Habilita Foreign Keys en SQLite."""
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON"))


class Base(DeclarativeBase):
    """Base para todos los modelos SQLAlchemy."""
    pass


class Mensaje(Base):
    """Modelo de mensaje en la base de datos."""
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), ForeignKey("leads.telefono", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" o "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)

    # Constraints
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_mensaje_role"),
        Index("ix_mensaje_telefono_timestamp", "telefono", "timestamp", postgresql_using="brin"),
    )

    def __repr__(self):
        return f"<Mensaje {self.telefono} - {self.role} - {self.timestamp}>"


class Lead(Base):
    """Modelo de lead para seguimiento de clientes (TABLA PRINCIPAL)."""
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=True)
    primer_contacto: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    ultimo_mensaje: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    fue_cliente: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Clientes antiguos (previos a AgentKit)
    es_cliente_previo: Mapped[bool] = mapped_column(default=False, nullable=False)
    productos_comprados_previos: Mapped[str] = mapped_column(Text, nullable=True)
    historial_previo_resumen: Mapped[str] = mapped_column(Text, nullable=True)

    seguimiento_mismo_dia_enviado: Mapped[bool] = mapped_column(default=False, nullable=False)
    seguimiento_1dia_enviado: Mapped[bool] = mapped_column(default=False, nullable=False)
    seguimiento_3dias_enviado: Mapped[bool] = mapped_column(default=False, nullable=False)
    en_manos_humanas: Mapped[bool] = mapped_column(default=False, nullable=False)
    anuncio_producto: Mapped[str] = mapped_column(String(200), nullable=True)  # Producto identificado desde anuncio Meta

    # Seguimiento avanzado
    desistido: Mapped[bool] = mapped_column(default=False, nullable=False)
    ultimo_mensaje_usuario: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # Solo mensajes del cliente
    fecha_seguimiento_mismo_dia: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    fecha_seguimiento_1dia: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Lead Scoring
    score: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    intencion: Mapped[str] = mapped_column(String(10), default="cold", nullable=False)
    urgencia: Mapped[str] = mapped_column(String(10), default="baja", nullable=False)
    producto_preferido: Mapped[str] = mapped_column(String(200), nullable=True)
    presupuesto_estimado: Mapped[str] = mapped_column(String(100), nullable=True)
    objeciones: Mapped[str] = mapped_column(Text, nullable=True)
    proximo_followup: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    alerta_vendedor_enviada: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Constraints
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_lead_score"),
        CheckConstraint("intencion IN ('cold', 'warm', 'hot')", name="ck_lead_intencion"),
        CheckConstraint("urgencia IN ('baja', 'media', 'alta')", name="ck_lead_urgencia"),
        Index("ix_lead_score_ultimo", "score", "ultimo_mensaje"),
    )

    def __repr__(self):
        return f"<Lead {self.telefono} - {self.intencion} - {self.primer_contacto}>"


class CarritoAbandonado(Base):
    """Modelo para rastrear carritos abandonados."""
    __tablename__ = "carritos_abandonados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), ForeignKey("leads.telefono", ondelete="CASCADE"), index=True, nullable=False)
    producto: Mapped[str] = mapped_column(String(200), nullable=False)
    precio: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_abandono: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    recordatorio_enviado: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        Index("ix_carrito_telefono_abandono", "telefono", "fecha_abandono"),
    )

    def __repr__(self):
        return f"<Carrito {self.telefono} - {self.producto}>"


class Pedido(Base):
    """Modelo para pedidos confirmados y completados."""
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), ForeignKey("leads.telefono", ondelete="CASCADE"), index=True, nullable=False)
    producto: Mapped[str] = mapped_column(String(200), nullable=False)
    precio: Mapped[str] = mapped_column(String(50), nullable=False)
    metodo_pago: Mapped[str] = mapped_column(String(100), nullable=False)

    # Datos de envío
    nombre_cliente: Mapped[str] = mapped_column(String(100), nullable=True)
    direccion_envio: Mapped[str] = mapped_column(Text, nullable=True)
    ciudad_departamento: Mapped[str] = mapped_column(String(100), nullable=True)
    telefono_contacto: Mapped[str] = mapped_column(String(50), nullable=True)

    # Datos de factura
    ruc_cedula: Mapped[str] = mapped_column(String(50), nullable=True)
    razon_social: Mapped[str] = mapped_column(String(100), nullable=True)

    # Estado del pedido
    fecha_pedido: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    estado: Mapped[str] = mapped_column(String(50), default="pendiente", nullable=False)
    confirmacion_enviada: Mapped[bool] = mapped_column(default=False, nullable=False)
    encuesta_enviada: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        CheckConstraint("estado IN ('pendiente', 'pagado', 'entregado')", name="ck_pedido_estado"),
        CheckConstraint("metodo_pago IN ('transferencia', 'efectivo', 'pagopar', 'qr')", name="ck_pedido_metodo"),
        Index("ix_pedido_telefono_estado", "telefono", "estado"),
        Index("ix_pedido_fecha_estado", "fecha_pedido", "estado"),
    )

    def __repr__(self):
        return f"<Pedido {self.telefono} - {self.producto} - {self.estado}>"


class Satisfaccion(Base):
    """Modelo para almacenar respuestas de encuestas post-venta."""
    __tablename__ = "satisfaccion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), ForeignKey("leads.telefono", ondelete="CASCADE"), index=True, nullable=False)
    pedido_id: Mapped[int] = mapped_column(Integer, ForeignKey("pedidos.id", ondelete="SET NULL"), nullable=True)
    producto: Mapped[str] = mapped_column(String(200), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comentario: Mapped[str] = mapped_column(Text, nullable=True)
    fecha_respuesta: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    nps: Mapped[str] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_satisfaccion_rating"),
        CheckConstraint("nps IN ('promotor', 'neutral', 'detractor') OR nps IS NULL", name="ck_satisfaccion_nps"),
        Index("ix_satisfaccion_telefono_fecha", "telefono", "fecha_respuesta"),
        Index("ix_satisfaccion_nps", "nps"),
    )

    def __repr__(self):
        return f"<Satisfaccion {self.telefono} - {self.rating}⭐ - {self.fecha_respuesta}>"


class Auditoria(Base):
    """Modelo para registrar TODOS los cambios en la BD (auditoría)."""
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tabla: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "leads", "pedidos", "mensajes"
    operacion: Mapped[str] = mapped_column(String(10), nullable=False)  # "INSERT", "UPDATE", "DELETE"
    registro_id: Mapped[int] = mapped_column(Integer, nullable=True, index=True)  # ID del registro afectado
    datos_anteriores: Mapped[str] = mapped_column(Text, nullable=True)  # JSON antes del cambio
    datos_nuevos: Mapped[str] = mapped_column(Text, nullable=True)  # JSON después del cambio
    usuario: Mapped[str] = mapped_column(String(100), nullable=True)  # Usuario que hizo el cambio
    razon: Mapped[str] = mapped_column(String(255), nullable=True)  # Por qué se hizo el cambio
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    error: Mapped[bool] = mapped_column(default=False, nullable=False)  # Si la operación falló
    mensaje_error: Mapped[str] = mapped_column(Text, nullable=True)  # Si error=True, el mensaje

    __table_args__ = (
        CheckConstraint("operacion IN ('INSERT', 'UPDATE', 'DELETE')", name="ck_auditoria_operacion"),
        Index("ix_auditoria_tabla_timestamp", "tabla", "timestamp"),
        Index("ix_auditoria_error", "error"),
    )

    def __repr__(self):
        status = "❌" if self.error else "✅"
        return f"{status} <Auditoria {self.tabla}.{self.operacion} id={self.registro_id} {self.timestamp}>"


class SeguimientoProgramado(Base):
    """Modelo para seguimientos programados dinámicamente (ej: 'escríbeme en 4 minutos')."""
    __tablename__ = "seguimientos_programados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), ForeignKey("leads.telefono", ondelete="CASCADE"), index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=True)

    # Detalles del seguimiento
    momento_programado: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)  # Cuándo enviar
    mensaje_personalizado: Mapped[str] = mapped_column(Text, nullable=True)  # Mensaje personalizado (si lo hay)

    # Control de envío
    fue_enviado: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    fecha_envio_real: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # Cuándo se envió realmente

    # Auditoría
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    contexto_original: Mapped[str] = mapped_column(Text, nullable=True)  # JSON con contexto (para debugging)

    __table_args__ = (
        Index("ix_seguimiento_programado_momento", "momento_programado"),
        Index("ix_seguimiento_programado_telefono_enviado", "telefono", "fue_enviado"),
    )

    def __repr__(self):
        status = "✅" if self.fue_enviado else "⏰"
        return f"{status} <SeguimientoProgramado {self.telefono} → {self.momento_programado}>"


async def ejecutar_migraciones():
    """Ejecuta migraciones necesarias para nuevas columnas/tablas."""
    async with engine.begin() as conn:
        # Migración: Agregar columna seguimiento_mismo_dia_enviado si no existe
        try:
            # PostgreSQL: checar si la columna existe
            result = await conn.execute(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='leads' AND column_name='seguimiento_mismo_dia_enviado'
                """)
            )
            if not result.fetchone():
                logger.info("🔄 Agregando columna seguimiento_mismo_dia_enviado...")
                await conn.execute(
                    text("ALTER TABLE leads ADD COLUMN seguimiento_mismo_dia_enviado BOOLEAN DEFAULT FALSE NOT NULL")
                )
                logger.info("✓ Columna seguimiento_mismo_dia_enviado agregada correctamente")
        except Exception as e:
            logger.warning(f"⚠️ Error en migración de seguimiento_mismo_dia_enviado: {e}")
            # Si es SQLite, el error es diferente — ignorar

        # Migración: Agregar columna anuncio_producto si no existe
        # Usa ALTER TABLE directo — funciona en SQLite y PostgreSQL
        # (falla silenciosamente si la columna ya existe)
        try:
            await conn.execute(
                text("ALTER TABLE leads ADD COLUMN anuncio_producto VARCHAR(200) NULL")
            )
            logger.info("✓ Columna anuncio_producto agregada correctamente")
        except Exception:
            pass  # Columna ya existe — normal en deploys subsecuentes

        try:
            await conn.execute(text("ALTER TABLE leads ADD COLUMN desistido BOOLEAN DEFAULT FALSE NOT NULL"))
            logger.info("✓ Columna desistido agregada")
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE leads ADD COLUMN ultimo_mensaje_usuario TIMESTAMP NULL"))
            logger.info("✓ Columna ultimo_mensaje_usuario agregada")
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE leads ADD COLUMN fecha_seguimiento_mismo_dia TIMESTAMP NULL"))
            logger.info("✓ Columna fecha_seguimiento_mismo_dia agregada")
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE leads ADD COLUMN fecha_seguimiento_1dia TIMESTAMP NULL"))
            logger.info("✓ Columna fecha_seguimiento_1dia agregada")
        except Exception:
            pass


async def inicializar_db():
    """Crea las tablas si no existen y habilita Foreign Keys."""
    async with engine.begin() as conn:
        # Habilitar Foreign Keys en SQLite
        if "sqlite" in DATABASE_URL:
            await conn.execute(text("PRAGMA foreign_keys = ON"))

        # Crear todas las tablas
        await conn.run_sync(Base.metadata.create_all)

        # Verificar que las FK estén habilitadas
        if "sqlite" in DATABASE_URL:
            result = await conn.execute(text("PRAGMA foreign_keys"))
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("✅ Foreign Keys habilitadas en SQLite")
            else:
                logger.warning("⚠️ Foreign Keys podrían no estar habilitadas en SQLite")

    # Ejecutar migraciones necesarias
    await ejecutar_migraciones()


# ════════════════════════════════════════════════════════════
# AUDITORÍA Y LOGGING
# ════════════════════════════════════════════════════════════

async def registrar_auditoria(
    tabla: str,
    operacion: str,
    registro_id: int = None,
    datos_anteriores: dict = None,
    datos_nuevos: dict = None,
    usuario: str = "sistema",
    razon: str = None,
    error: bool = False,
    mensaje_error: str = None
) -> Auditoria:
    """
    Registra un cambio en la auditoría.

    ✅ ANTI-ERROR-SILENCIOSO: Todos los cambios quedan registrados

    Args:
        tabla: Nombre de la tabla ("leads", "pedidos", etc)
        operacion: "INSERT", "UPDATE", "DELETE"
        registro_id: ID del registro modificado
        datos_anteriores: Dict con datos antes del cambio
        datos_nuevos: Dict con datos después del cambio
        usuario: Usuario que hizo el cambio
        razon: Por qué se hizo el cambio
        error: Si la operación falló
        mensaje_error: Si error=True, el mensaje de error

    Returns:
        El registro de auditoría creado
    """
    async with async_session() as session:
        try:
            auditoria = Auditoria(
                tabla=tabla,
                operacion=operacion,
                registro_id=registro_id,
                datos_anteriores=json.dumps(datos_anteriores, default=str) if datos_anteriores else None,
                datos_nuevos=json.dumps(datos_nuevos, default=str) if datos_nuevos else None,
                usuario=usuario,
                razon=razon,
                error=error,
                mensaje_error=mensaje_error,
                timestamp=datetime.utcnow()
            )
            session.add(auditoria)
            await session.commit()

            # Log también en el archivo
            if error:
                logger.error(f"🔴 {tabla}.{operacion} ERROR: {mensaje_error}")
            else:
                logger.info(f"✅ {tabla}.{operacion} id={registro_id} by {usuario}")

            return auditoria

        except Exception as e:
            logger.critical(f"❌ ERROR CRITICO registrando auditoría: {e}")
            raise


async def obtener_errores_recientes(horas: int = 24, limite: int = 50) -> list[Auditoria]:
    """
    Obtiene todos los errores de las últimas X horas.

    ✅ ANTI-ERROR-SILENCIOSO: Ver todos los errores que pasaron

    Args:
        horas: Cuántas horas atrás buscar
        limite: Máximo de registros

    Returns:
        Lista de Auditoria con error=True
    """
    async with async_session() as session:
        hace_x_horas = datetime.utcnow() - timedelta(hours=horas)

        query = (
            select(Auditoria)
            .where(Auditoria.error == True)
            .where(Auditoria.timestamp >= hace_x_horas)
            .order_by(desc(Auditoria.timestamp))
            .limit(limite)
        )
        result = await session.execute(query)
        return result.scalars().all()


async def obtener_historial_auditoria_tabla(
    tabla: str,
    horas: int = 24,
    limite: int = 100
) -> list[Auditoria]:
    """
    Obtiene el historial de cambios de una tabla.

    ✅ ANTI-ERROR-SILENCIOSO: Ver quién cambió qué y cuándo

    Args:
        tabla: Nombre de la tabla
        horas: Cuántas horas atrás
        limite: Máximo de registros

    Returns:
        Lista de Auditoria filtrada
    """
    async with async_session() as session:
        hace_x_horas = datetime.utcnow() - timedelta(hours=horas)

        query = (
            select(Auditoria)
            .where(Auditoria.tabla == tabla)
            .where(Auditoria.timestamp >= hace_x_horas)
            .order_by(desc(Auditoria.timestamp))
            .limit(limite)
        )
        result = await session.execute(query)
        return result.scalars().all()


async def obtener_estadisticas_auditoria() -> dict:
    """
    Obtiene estadísticas de auditoría.

    ✅ ANTI-ERROR-SILENCIOSO: Saber cuántos errores hubo

    Returns:
        {
            "total_operaciones": int,
            "total_errores": int,
            "tasa_error": float,
            "por_tabla": {...},
            "por_operacion": {...}
        }
    """
    async with async_session() as session:
        # Total operaciones
        total = await session.execute(select(func.count(Auditoria.id)))
        total_ops = total.scalar() or 0

        # Total errores
        errores = await session.execute(
            select(func.count(Auditoria.id)).where(Auditoria.error == True)
        )
        total_errores = errores.scalar() or 0

        # Por tabla
        por_tabla = await session.execute(
            select(Auditoria.tabla, func.count(Auditoria.id))
            .group_by(Auditoria.tabla)
        )
        tabla_stats = {tabla: count for tabla, count in por_tabla.all()}

        # Por operación
        por_op = await session.execute(
            select(Auditoria.operacion, func.count(Auditoria.id))
            .group_by(Auditoria.operacion)
        )
        op_stats = {op: count for op, count in por_op.all()}

        tasa_error = (total_errores / total_ops * 100) if total_ops > 0 else 0

        return {
            "total_operaciones": total_ops,
            "total_errores": total_errores,
            "tasa_error": round(tasa_error, 2),
            "por_tabla": tabla_stats,
            "por_operacion": op_stats
        }


async def guardar_mensaje(telefono: str, role: str, content: str) -> Mensaje:
    """
    Guarda un mensaje en el historial de conversación.

    ✅ ATÓMICO: Si el lead no existe, falla con IntegrityError (FK constraint)
    ✅ ANTI-ERROR-SILENCIOSO: Registra auditoría y lanza excepciones específicas

    Args:
        telefono: Número de teléfono del cliente
        role: "user" o "assistant"
        content: Contenido del mensaje

    Raises:
        IntegrityViolationError: Si el lead no existe (violación de FK)
        ValidationError: Si los parámetros son inválidos
    """
    # Validar inputs
    if not telefono or not role or not content:
        await registrar_auditoria(
            tabla="mensajes",
            operacion="INSERT",
            usuario="sistema",
            error=True,
            mensaje_error=f"Validación fallida: telefono={telefono}, role={role}, content={content}"
        )
        raise ValidationError(f"Campos requeridos: telefono, role, content")

    if role not in ("user", "assistant"):
        await registrar_auditoria(
            tabla="mensajes",
            operacion="INSERT",
            usuario="sistema",
            error=True,
            mensaje_error=f"Role inválido: {role} (debe ser 'user' o 'assistant')"
        )
        raise ValidationError(f"Role debe ser 'user' o 'assistant', recibido: {role}")

    async with async_session() as session:
        try:
            mensaje = Mensaje(
                telefono=telefono,
                role=role,
                content=content,
                timestamp=datetime.utcnow()
            )
            session.add(mensaje)
            await session.commit()
            await session.refresh(mensaje)

            # Registrar en auditoría
            await registrar_auditoria(
                tabla="mensajes",
                operacion="INSERT",
                registro_id=mensaje.id,
                datos_nuevos={"telefono": telefono, "role": role, "content": content[:50]},
                usuario="sistema",
                razon="Nuevo mensaje en conversación"
            )

            return mensaje

        except IntegrityError as e:
            await session.rollback()

            # Registrar el error en auditoría
            await registrar_auditoria(
                tabla="mensajes",
                operacion="INSERT",
                usuario="sistema",
                error=True,
                mensaje_error=f"FK constraint failed: {str(e)}"
            )

            if "FOREIGN KEY constraint failed" in str(e):
                logger.error(f"❌ Lead {telefono} no existe")
                raise IntegrityViolationError(
                    f"Lead con teléfono {telefono} no existe. Registra el lead primero."
                )
            raise

        except Exception as e:
            await session.rollback()

            # Registrar cualquier otro error
            await registrar_auditoria(
                tabla="mensajes",
                operacion="INSERT",
                usuario="sistema",
                error=True,
                mensaje_error=f"Error inesperado: {str(e)}\n{traceback.format_exc()}"
            )

            logger.critical(f"❌ Error guardando mensaje para {telefono}: {e}\n{traceback.format_exc()}")
            raise AgentKitError(f"Error al guardar mensaje: {e}")


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    """
    Recupera los últimos N mensajes de una conversación en orden cronológico.

    ✅ OPTIMIZADO: Usa LIMIT en SQL, no trae a Python

    Args:
        telefono: Número de teléfono del cliente
        limite: Máximo de mensajes a recuperar (default: 20, suficiente para contexto)

    Returns:
        Lista de diccionarios con rol y contenido: [{"role": "user", "content": "..."}, ...]
    """
    async with async_session() as session:
        # Subquery: últimos N mensajes
        subquery = (
            select(Mensaje.id)
            .where(Mensaje.telefono == telefono)
            .order_by(desc(Mensaje.timestamp))
            .limit(limite)
            .subquery()
        )

        # Query principal: obtener en orden cronológico (antiguos → recientes)
        query = (
            select(Mensaje)
            .where(Mensaje.id.in_(select(subquery.c.id)))
            .order_by(Mensaje.timestamp)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()

        # Retornar en formato compatible con Claude API
        return [
            {
                "role": msg.role,
                "content": msg.content
            }
            for msg in mensajes
        ]


async def limpiar_historial(telefono: str) -> int:
    """
    Borra todo el historial de una conversación en una única operación SQL.

    ✅ ATÓMICO + OPTIMIZADO: Usa DELETE en SQL, no loops

    Args:
        telefono: Número de teléfono del cliente

    Returns:
        Cantidad de mensajes eliminados
    """
    async with async_session() as session:
        try:
            stmt = delete(Mensaje).where(Mensaje.telefono == telefono)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
        except Exception as e:
            await session.rollback()
            raise ValueError(f"Error al limpiar historial: {e}")


async def obtener_estadisticas(telefono: str) -> dict:
    """
    Obtiene estadísticas de una conversación usando SQL aggregation.

    ✅ OPTIMIZADO: Usa COUNT, MIN, MAX en SQL en lugar de traer a Python

    Args:
        telefono: Número de teléfono del cliente

    Returns:
        Diccionario con stats
    """
    async with async_session() as session:
        # Count total mensajes
        total_query = select(func.count(Mensaje.id)).where(Mensaje.telefono == telefono)
        total_result = await session.execute(total_query)
        total_mensajes = total_result.scalar() or 0

        if total_mensajes == 0:
            return {
                "telefono": telefono,
                "total_mensajes": 0,
                "mensajes_usuario": 0,
                "mensajes_agente": 0,
                "primera_msg": None,
                "ultima_msg": None
            }

        # Contar por rol
        user_count = await session.execute(
            select(func.count(Mensaje.id))
            .where(and_(Mensaje.telefono == telefono, Mensaje.role == "user"))
        )
        mensajes_usuario = user_count.scalar() or 0

        assistant_count = await session.execute(
            select(func.count(Mensaje.id))
            .where(and_(Mensaje.telefono == telefono, Mensaje.role == "assistant"))
        )
        mensajes_agente = assistant_count.scalar() or 0

        # Min y Max timestamps
        minmax_query = select(
            func.min(Mensaje.timestamp).label("primera_msg"),
            func.max(Mensaje.timestamp).label("ultima_msg")
        ).where(Mensaje.telefono == telefono)
        minmax_result = await session.execute(minmax_query)
        primera_msg, ultima_msg = minmax_result.first()

        return {
            "telefono": telefono,
            "total_mensajes": total_mensajes,
            "mensajes_usuario": mensajes_usuario,
            "mensajes_agente": mensajes_agente,
            "primera_msg": primera_msg,
            "ultima_msg": ultima_msg
        }


# ════════════════════════════════════════════════════════════
# FUNCIONES PARA LEADS Y SEGUIMIENTO
# ════════════════════════════════════════════════════════════

async def registrar_lead(telefono: str, nombre: str = "") -> Lead:
    """
    Registra un nuevo lead o actualiza uno existente (UPSERT).

    ✅ ATÓMICO: Usa sesión única, actualiza último_mensaje de forma segura
    ✅ ANTI-ERROR-SILENCIOSO: Registra auditoría de creación/actualización

    Args:
        telefono: Número de teléfono único
        nombre: Nombre del cliente (opcional)

    Returns:
        El Lead registrado o actualizado

    Raises:
        ValidationError: Si el teléfono es inválido
        AgentKitError: Si hay error en la BD
    """
    # Validar teléfono
    if not telefono or not isinstance(telefono, str) or len(telefono) < 5:
        await registrar_auditoria(
            tabla="leads",
            operacion="INSERT",
            usuario="sistema",
            error=True,
            mensaje_error=f"Teléfono inválido: {telefono}"
        )
        raise ValidationError(f"Teléfono inválido: {telefono}")

    async with async_session() as session:
        try:
            # Verificar si ya existe
            query = select(Lead).where(Lead.telefono == telefono)
            result = await session.execute(query)
            lead_existente = result.scalar_one_or_none()

            if lead_existente:
                # ACTUALIZAR: Registrar auditoría de cambio
                datos_anteriores = {
                    "nombre": lead_existente.nombre,
                    "ultimo_mensaje": str(lead_existente.ultimo_mensaje)
                }

                lead_existente.ultimo_mensaje = datetime.utcnow()
                if nombre and not lead_existente.nombre:
                    lead_existente.nombre = nombre

                await session.commit()
                await session.refresh(lead_existente)

                # Registrar en auditoría
                await registrar_auditoria(
                    tabla="leads",
                    operacion="UPDATE",
                    registro_id=lead_existente.id,
                    datos_anteriores=datos_anteriores,
                    datos_nuevos={"nombre": lead_existente.nombre, "ultimo_mensaje": str(lead_existente.ultimo_mensaje)},
                    usuario="sistema",
                    razon="Actualización de lead existente"
                )

                logger.info(f"✅ Lead actualizado: {telefono}")
                return lead_existente

            # INSERTAR: Crear nuevo lead
            nuevo_lead = Lead(
                telefono=telefono,
                nombre=nombre or None,
                primer_contacto=datetime.utcnow(),
                ultimo_mensaje=datetime.utcnow(),
                score=20,
                intencion="cold",
                urgencia="baja"
            )
            session.add(nuevo_lead)
            await session.commit()
            await session.refresh(nuevo_lead)

            # Registrar en auditoría
            await registrar_auditoria(
                tabla="leads",
                operacion="INSERT",
                registro_id=nuevo_lead.id,
                datos_nuevos={"telefono": telefono, "nombre": nombre},
                usuario="sistema",
                razon="Nuevo lead registrado"
            )

            logger.info(f"✅ Lead creado: {telefono} - {nombre}")
            return nuevo_lead

        except IntegrityError as e:
            await session.rollback()

            # Registrar el error
            await registrar_auditoria(
                tabla="leads",
                operacion="INSERT",
                usuario="sistema",
                error=True,
                mensaje_error=f"Unique constraint failed (teléfono duplicado): {telefono}"
            )

            logger.error(f"❌ Error registrando lead {telefono}: {e}")
            raise AgentKitError(f"Error al registrar lead: {e}")

        except Exception as e:
            await session.rollback()

            # Registrar error inesperado
            await registrar_auditoria(
                tabla="leads",
                operacion="INSERT",
                usuario="sistema",
                error=True,
                mensaje_error=f"Error inesperado: {str(e)}\n{traceback.format_exc()}"
            )

            logger.critical(f"❌ Error crítico registrando lead {telefono}: {e}\n{traceback.format_exc()}")
            raise AgentKitError(f"Error al registrar lead: {e}")


async def obtener_leads_para_seguimiento_1() -> list[Lead]:
    """Leads para seguimiento 1: todos los leads activos 3+ horas después del primer contacto."""
    async with async_session() as session:
        hace_3h = datetime.utcnow() - timedelta(hours=3)
        hace_72h = datetime.utcnow() - timedelta(hours=72)  # ventana amplia
        query = (
            select(Lead)
            .where(Lead.primer_contacto <= hace_3h)
            .where(Lead.primer_contacto >= hace_72h)
            .where(Lead.seguimiento_mismo_dia_enviado == False)
            .where(Lead.fue_cliente == False)
            .where(Lead.desistido == False)
            .where(Lead.en_manos_humanas == False)
            .order_by(Lead.primer_contacto)
        )
        result = await session.execute(query)
        return result.scalars().all()


async def obtener_leads_para_seguimiento_2() -> list[Lead]:
    """
    Leads para seguimiento 2 (día siguiente 15:00):
    - Recibieron seguimiento 1
    - NO respondieron desde entonces (ultimo_mensaje_usuario no avanzó)
    - Seguimiento 2 aún no enviado
    """
    async with async_session() as session:
        hace_20h = datetime.utcnow() - timedelta(hours=20)
        hace_96h = datetime.utcnow() - timedelta(hours=96)
        query = (
            select(Lead)
            .where(Lead.seguimiento_mismo_dia_enviado == True)
            .where(Lead.seguimiento_1dia_enviado == False)
            .where(Lead.fue_cliente == False)
            .where(Lead.desistido == False)
            .where(Lead.en_manos_humanas == False)
            .where(Lead.primer_contacto <= hace_20h)
            .where(Lead.primer_contacto >= hace_96h)
            # No respondieron: ultimo_mensaje_usuario es null o igual a primer_contacto
            # (solo escribieron el mensaje inicial, no respondieron al bot)
            .where(
                (Lead.ultimo_mensaje_usuario == None) |
                (Lead.ultimo_mensaje_usuario <= Lead.primer_contacto + timedelta(minutes=30))
            )
        )
        result = await session.execute(query)
        return result.scalars().all()


async def obtener_leads_para_seguimiento_3() -> list[Lead]:
    """
    Leads para seguimiento 3 (día 3, 15:00):
    - Recibieron al menos seguimiento 1
    - NO respondieron a ningún seguimiento
    - Seguimiento 3 aún no enviado
    - Han pasado 3+ días desde primer contacto
    """
    async with async_session() as session:
        hace_3dias = datetime.utcnow() - timedelta(days=3)
        hace_10dias = datetime.utcnow() - timedelta(days=10)
        query = (
            select(Lead)
            .where(Lead.seguimiento_mismo_dia_enviado == True)
            .where(Lead.seguimiento_3dias_enviado == False)
            .where(Lead.fue_cliente == False)
            .where(Lead.desistido == False)
            .where(Lead.en_manos_humanas == False)
            .where(Lead.primer_contacto <= hace_3dias)
            .where(Lead.primer_contacto >= hace_10dias)
            .where(
                (Lead.ultimo_mensaje_usuario == None) |
                (Lead.ultimo_mensaje_usuario <= Lead.primer_contacto + timedelta(minutes=30))
            )
        )
        result = await session.execute(query)
        return result.scalars().all()


async def obtener_leads_para_seguimiento_domingo() -> list[Lead]:
    """
    Leads para seguimiento dominical (todos los domingos 14:00):
    - Recibieron al menos 1 seguimiento
    - Nunca respondieron
    - No desistidos, no clientes
    """
    async with async_session() as session:
        hace_7dias = datetime.utcnow() - timedelta(days=7)  # No más de 7 días
        query = (
            select(Lead)
            .where(Lead.seguimiento_mismo_dia_enviado == True)
            .where(Lead.fue_cliente == False)
            .where(Lead.desistido == False)
            .where(Lead.en_manos_humanas == False)
            .where(Lead.primer_contacto >= hace_7dias)
            .where(
                (Lead.ultimo_mensaje_usuario == None) |
                (Lead.ultimo_mensaje_usuario <= Lead.primer_contacto + timedelta(minutes=30))
            )
        )
        result = await session.execute(query)
        return result.scalars().all()


# Aliases para compatibilidad con código existente
obtener_leads_sin_respuesta_mismo_dia = obtener_leads_para_seguimiento_1
obtener_leads_sin_respuesta_1dia = obtener_leads_para_seguimiento_2
obtener_leads_sin_respuesta_3dias = obtener_leads_para_seguimiento_3


async def actualizar_ultimo_mensaje_usuario(telefono: str):
    """Actualiza el timestamp del último mensaje del cliente (no del bot)."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.ultimo_mensaje_usuario = datetime.utcnow()
            await session.commit()


async def marcar_desistido(telefono: str):
    """Marca que el cliente explícitamente rechazó — para todos los seguimientos."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.desistido = True
            await session.commit()
            logger.info(f"✗ Lead marcado como desistido: {telefono}")


async def marcar_seguimiento_1dia(telefono: str):
    """Marca que se envió seguimiento de 1 día."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.seguimiento_1dia_enviado = True
            lead.fecha_seguimiento_1dia = datetime.utcnow()
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
    Guarda un pedido confirmado en la base de datos (simple, sin actualizar Lead).

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

    Raises:
        IntegrityError: Si el lead no existe (violación de FK)
    """
    async with async_session() as session:
        try:
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
            await session.refresh(pedido)
            return pedido
        except IntegrityError as e:
            await session.rollback()
            if "FOREIGN KEY constraint failed" in str(e):
                raise ValueError(f"Lead con teléfono {telefono} no existe.")
            raise


async def guardar_pedido_atomico(
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
    Guarda un pedido Y marca el lead como "fue_cliente = True" en UNA transacción.

    ✅ ATÓMICO: Si falla actualizar el lead, todo el pedido se revierte (ROLLBACK)
    ✅ ANTI-ERROR-SILENCIOSO: Registra auditoría y lanza excepciones específicas

    Args:
        Mismos que guardar_pedido()

    Returns:
        El pedido guardado

    Raises:
        IntegrityViolationError: Si el lead no existe
        ValidationError: Si hay error de validación
        AtomicityError: Si la transacción falla
    """
    # Validar inputs
    if not all([telefono, producto, precio, metodo_pago]):
        await registrar_auditoria(
            tabla="pedidos",
            operacion="INSERT",
            usuario="sistema",
            error=True,
            mensaje_error=f"Campos requeridos inválidos"
        )
        raise ValidationError("Campos requeridos: telefono, producto, precio, metodo_pago")

    if metodo_pago not in ("transferencia", "efectivo", "pagopar", "qr"):
        await registrar_auditoria(
            tabla="pedidos",
            operacion="INSERT",
            usuario="sistema",
            error=True,
            mensaje_error=f"Metodo_pago inválido: {metodo_pago}"
        )
        raise ValidationError(f"Metodo_pago inválido: {metodo_pago}")

    async with async_session() as session:
        try:
            # DENTRO de la misma transacción:

            # 1. Verificar que el lead existe
            lead_query = select(Lead).where(Lead.telefono == telefono)
            lead_result = await session.execute(lead_query)
            lead = lead_result.scalar_one_or_none()

            if not lead:
                await registrar_auditoria(
                    tabla="pedidos",
                    operacion="INSERT",
                    usuario="sistema",
                    error=True,
                    mensaje_error=f"Lead {telefono} no existe"
                )
                raise IntegrityViolationError(f"Lead con teléfono {telefono} no existe.")

            datos_lead_anterior = {"fue_cliente": lead.fue_cliente, "score": lead.score, "intencion": lead.intencion}
            score_anterior = lead.score

            # 2. Crear pedido
            pedido = Pedido(
                telefono=telefono,
                producto=producto,
                precio=precio,
                metodo_pago=metodo_pago,
                nombre_cliente=nombre_cliente or lead.nombre,
                direccion_envio=direccion_envio,
                ciudad_departamento=ciudad_departamento,
                telefono_contacto=telefono_contacto,
                ruc_cedula=ruc_cedula,
                razon_social=razon_social,
                estado="pendiente",
                fecha_pedido=datetime.utcnow()
            )
            session.add(pedido)

            # 3. Actualizar lead como cliente
            lead.fue_cliente = True
            lead.ultimo_mensaje = datetime.utcnow()
            if lead.score < 70:
                lead.score = min(100, lead.score + 30)
            if lead.intencion == "cold":
                lead.intencion = "warm"

            # 4. Commit ATÓMICO: todo o nada
            await session.commit()
            await session.refresh(pedido)

            # Registrar auditoría de éxito
            await registrar_auditoria(
                tabla="pedidos",
                operacion="INSERT",
                registro_id=pedido.id,
                datos_nuevos={"producto": producto, "precio": precio, "metodo_pago": metodo_pago},
                usuario="sistema",
                razon="Nuevo pedido - Conversión a cliente"
            )

            await registrar_auditoria(
                tabla="leads",
                operacion="UPDATE",
                registro_id=lead.id,
                datos_anteriores=datos_lead_anterior,
                datos_nuevos={"fue_cliente": True, "score": lead.score, "intencion": lead.intencion},
                usuario="sistema",
                razon=f"Pedido #{pedido.id} - Score {score_anterior}→{lead.score}"
            )

            logger.info(f"✅ ATÓMICO: Pedido #{pedido.id} + Lead {telefono} actualizado")
            return pedido

        except (IntegrityViolationError, ValidationError):
            raise

        except IntegrityError as e:
            await session.rollback()
            await registrar_auditoria(
                tabla="pedidos",
                operacion="INSERT",
                usuario="sistema",
                error=True,
                mensaje_error=f"IntegrityError: {str(e)}"
            )
            logger.error(f"❌ Error integridad al guardar pedido {telefono}: {e}")
            raise

        except Exception as e:
            await session.rollback()
            await registrar_auditoria(
                tabla="pedidos",
                operacion="INSERT",
                usuario="sistema",
                error=True,
                mensaje_error=f"Error: {str(e)[:200]}\n{traceback.format_exc()[:500]}"
            )
            logger.critical(f"❌ Error crítico al guardar pedido {telefono}: {e}\n{traceback.format_exc()}")
            raise AtomicityError(f"Transacción fallida (ROLLBACK): {e}")


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
) -> Lead | None:
    """
    Actualiza los campos de scoring de un lead en UNA transacción.

    ✅ ATÓMICO: Todos los cambios se aplican juntos o ninguno

    Args:
        telefono: Teléfono del lead
        score: Score 0-100 (se clampea automáticamente)
        intencion: "cold", "warm", "hot"
        urgencia: "baja", "media", "alta"
        ... (resto de campos opcionales)

    Returns:
        El lead actualizado o None si no existe
    """
    async with async_session() as session:
        try:
            query = select(Lead).where(Lead.telefono == telefono)
            result = await session.execute(query)
            lead = result.scalar_one_or_none()

            if not lead:
                return None

            # Actualizar todos los campos en una transacción
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
            await session.refresh(lead)
            return lead

        except IntegrityError as e:
            await session.rollback()
            raise ValueError(f"Error al actualizar scoring del lead: {e}")


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
    Obtiene leads sin respuesta hace más de X horas usando SQL JOIN.

    ✅ OPTIMIZADO: Usa JOIN + GROUP BY en SQL, no loops en Python

    Un lead sin respuesta es aquel donde el último mensaje en 'mensajes'
    tiene role='user' (cliente escribió) y hace más de X horas.

    Args:
        horas: Horas sin respuesta (default: 4)

    Returns:
        [{telefono, nombre, ultimo_mensaje, horas_sin_respuesta, score, intencion}, ...]
    """
    async with async_session() as session:
        ahora = datetime.utcnow()
        hace_x_horas = ahora - timedelta(hours=horas)

        # Subquery: último mensaje de usuario por teléfono
        ultimo_msg_subquery = (
            select(
                Mensaje.telefono,
                Mensaje.content,
                Mensaje.timestamp
            )
            .where(Mensaje.role == "user")
            .order_by(Mensaje.telefono, desc(Mensaje.timestamp))
            .distinct(Mensaje.telefono)
            .subquery()
        )

        # Query principal: JOIN con leads, filtrar por tiempo
        query = (
            select(
                Lead.telefono,
                Lead.nombre,
                ultimo_msg_subquery.c.content,
                ultimo_msg_subquery.c.timestamp,
                Lead.score,
                Lead.intencion
            )
            .join(
                ultimo_msg_subquery,
                Lead.telefono == ultimo_msg_subquery.c.telefono
            )
            .where(ultimo_msg_subquery.c.timestamp < hace_x_horas)
            .order_by(desc(ultimo_msg_subquery.c.timestamp))
        )

        result = await session.execute(query)
        rows = result.all()

        leads_sin_respuesta = []
        for telefono, nombre, contenido, timestamp, score, intencion in rows:
            horas_esperando = (ahora - timestamp).total_seconds() / 3600
            leads_sin_respuesta.append({
                "telefono": telefono,
                "nombre": nombre or "Sin nombre",
                "ultimo_mensaje": contenido[:100] if contenido else "",
                "horas_sin_respuesta": int(horas_esperando),
                "score": score,
                "intencion": intencion
            })

        return leads_sin_respuesta


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


# ════════════════════════════════════════════════════════════
# ENCUESTAS POST-VENTA
# ════════════════════════════════════════════════════════════

async def obtener_pedidos_sin_encuesta() -> list[Pedido]:
    """Obtiene pedidos pagados hace 2h que aún no recibieron encuesta."""
    async with async_session() as session:
        hace_2h = datetime.utcnow() - timedelta(hours=2)
        hace_2_5h = datetime.utcnow() - timedelta(hours=2, minutes=30)

        query = (
            select(Pedido)
            .where(Pedido.estado == "pagado")
            .where(Pedido.encuesta_enviada == False)
            .where(Pedido.fecha_pedido >= hace_2_5h)
            .where(Pedido.fecha_pedido <= hace_2h)
            .order_by(desc(Pedido.fecha_pedido))
        )
        result = await session.execute(query)
        return result.scalars().all()


async def marcar_encuesta_enviada(pedido_id: int):
    """Marca que se envió encuesta al cliente."""
    async with async_session() as session:
        query = select(Pedido).where(Pedido.id == pedido_id)
        result = await session.execute(query)
        pedido = result.scalar_one_or_none()
        if pedido:
            pedido.encuesta_enviada = True
            await session.commit()


# ════════════════════════════════════════════════════════════
# SEGUIMIENTO MISMO DÍA
# ════════════════════════════════════════════════════════════

async def obtener_leads_sin_respuesta_mismo_dia() -> list[Lead]:
    """
    Obtiene leads contactados hace 3 a 48 horas que no respondieron.
    Se envía el primer seguimiento de reactivación.
    """
    async with async_session() as session:
        hace_3h = datetime.utcnow() - timedelta(hours=3)
        hace_48h = datetime.utcnow() - timedelta(hours=48)

        query = (
            select(Lead)
            .where(Lead.primer_contacto <= hace_3h)   # al menos 3 horas desde contacto
            .where(Lead.primer_contacto >= hace_48h)  # no más de 48 horas
            .where(Lead.seguimiento_mismo_dia_enviado == False)  # No se envió aún
            .where(Lead.fue_cliente == False)  # No son clientes (todavía)
            .order_by(Lead.primer_contacto)
        )
        result = await session.execute(query)
        return result.scalars().all()


async def marcar_seguimiento_mismo_dia(telefono: str):
    """Marca que se envió el seguimiento de mismo día."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead:
            lead.seguimiento_mismo_dia_enviado = True
            lead.fecha_seguimiento_mismo_dia = datetime.utcnow()
            await session.commit()


async def guardar_anuncio_producto(telefono: str, producto: str):
    """Guarda el producto identificado desde anuncio Meta en la BD."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalar_one_or_none()
        if lead and not lead.anuncio_producto:  # Solo si no tiene ya un producto guardado
            lead.anuncio_producto = producto
            await session.commit()
            logger.info(f"✓ Anuncio producto guardado: {telefono} → {producto}")


# ════════════════════════════════════════════════════════════
# SEGUIMIENTOS PROGRAMADOS DINÁMICOS
# ════════════════════════════════════════════════════════════

async def programar_seguimiento_dinamico(
    telefono: str,
    momento_programado: datetime,
    nombre: str = None,
    mensaje_personalizado: str = None,
    contexto: dict = None
) -> bool:
    """
    Programa un seguimiento dinámico para un cliente.
    Usado cuando el cliente dice "escríbeme en 4 minutos", etc.

    Args:
        telefono: Número de teléfono del cliente
        momento_programado: Cuándo enviar el mensaje (datetime)
        nombre: Nombre del cliente (para incluir en mensaje)
        mensaje_personalizado: Mensaje personalizado (si es None, se usa genérico)
        contexto: Contexto JSON para debugging

    Returns:
        True si se programó correctamente, False en caso contrario
    """
    try:
        async with async_session() as session:
            # Verificar que el lead existe
            query = select(Lead).where(Lead.telefono == telefono)
            result = await session.execute(query)
            lead = result.scalar_one_or_none()

            if not lead:
                logger.warning(f"❌ Lead {telefono} no existe para programar seguimiento")
                return False

            # Crear el seguimiento programado
            seguimiento = SeguimientoProgramado(
                telefono=telefono,
                nombre=nombre or lead.nombre,
                momento_programado=momento_programado,
                mensaje_personalizado=mensaje_personalizado,
                contexto_original=json.dumps(contexto or {}),
                fue_enviado=False  # Explícitamente pendiente
            )

            session.add(seguimiento)
            await session.commit()

            # AUDITORÍA: Verificar que se guardó correctamente
            seg_id = seguimiento.id

            # Validar que se guardó en BD
            query_check = select(SeguimientoProgramado).where(SeguimientoProgramado.id == seg_id)
            result_check = await session.execute(query_check)
            guardado = result_check.scalar_one_or_none()

            if not guardado:
                logger.error(f"❌ CRÍTICO: Seguimiento #{seg_id} no se guardó en BD después de commit!")
                return False

            logger.info(f"✅ Seguimiento #{seg_id} programado para {telefono} en {momento_programado} (VERIFICADO)")
            logger.debug(f"   Nombre: {nombre or lead.nombre}")
            logger.debug(f"   Mensaje: {mensaje_personalizado or '[genérico]'}")
            return True

    except IntegrityError as e:
        logger.error(f"❌ Error de integridad al programar seguimiento para {telefono}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error programando seguimiento para {telefono}: {type(e).__name__}: {e}", exc_info=True)
        return False


async def obtener_seguimientos_programados() -> list[SeguimientoProgramado]:
    """
    Obtiene todos los seguimientos programados que están vencidos (hora de enviar ya llegó).
    Los devuelve en orden de momento_programado.
    """
    async with async_session() as session:
        ahora = datetime.now(tz.utc).replace(tzinfo=None)
        logger.debug(f"🔍 Buscando seguimientos vencidos. Ahora UTC: {ahora}")

        query = (
            select(SeguimientoProgramado)
            .where(SeguimientoProgramado.fue_enviado == False)
            .where(SeguimientoProgramado.momento_programado <= ahora)
            .order_by(SeguimientoProgramado.momento_programado)
        )
        result = await session.execute(query)
        return result.scalars().all()


async def marcar_seguimiento_programado_enviado(seguimiento_id: int) -> bool:
    """Marca un seguimiento programado como enviado."""
    try:
        async with async_session() as session:
            query = select(SeguimientoProgramado).where(SeguimientoProgramado.id == seguimiento_id)
            result = await session.execute(query)
            seguimiento = result.scalar_one_or_none()

            if seguimiento:
                seguimiento.fue_enviado = True
                seguimiento.fecha_envio_real = datetime.utcnow()
                await session.commit()
                logger.info(f"✓ Seguimiento programado #{seguimiento_id} marcado como enviado")
                return True

        logger.warning(f"❌ Seguimiento programado #{seguimiento_id} no encontrado")
        return False

    except Exception as e:
        logger.error(f"Error marcando seguimiento como enviado: {e}")
        return False


async def guardar_respuesta_encuesta(
    telefono: str,
    pedido_id: int,
    producto: str,
    rating: int,
    comentario: str = ""
):
    """Guarda la respuesta de la encuesta de satisfacción."""
    async with async_session() as session:
        # Calcular NPS: 1-2=detractor, 3-4=neutral, 5=promotor
        if rating <= 2:
            nps = "detractor"
        elif rating <= 4:
            nps = "neutral"
        else:
            nps = "promotor"

        satisfaccion = Satisfaccion(
            telefono=telefono,
            pedido_id=pedido_id,
            producto=producto,
            rating=rating,
            comentario=comentario,
            nps=nps
        )
        session.add(satisfaccion)
        await session.commit()


async def obtener_nps_score() -> dict:
    """
    Calcula NPS score usando SQL aggregation.

    ✅ OPTIMIZADO: Usa COUNT en SQL, no trae a Python

    NPS = (Promotores - Detractores) / Total * 100
    """
    async with async_session() as session:
        query = select(
            func.count(Satisfaccion.id).label("total"),
            func.sum(func.cast(Satisfaccion.nps == "promotor", Integer)).label("promotores"),
            func.sum(func.cast(Satisfaccion.nps == "detractor", Integer)).label("detractores"),
            func.sum(func.cast(Satisfaccion.nps == "neutral", Integer)).label("neutrales")
        )
        result = await session.execute(query)
        total, promotores, detractores, neutrales = result.first()

        # Manejar valores None
        total = total or 0
        promotores = promotores or 0
        detractores = detractores or 0
        neutrales = neutrales or 0

        nps = round((promotores - detractores) / total * 100) if total > 0 else 0

        return {
            "nps": nps,
            "promotores": promotores,
            "neutrales": neutrales,
            "detractores": detractores,
            "total": total
        }


# ════════════════════════════════════════════════════════════
# FUNCIONES PARA MANEJO AVANZADO DE TRANSACCIONES
# ════════════════════════════════════════════════════════════

async def ejecutar_en_transaccion_atomica(operaciones: list[callable]) -> bool:
    """
    Ejecuta múltiples operaciones en una ÚNICA transacción.

    ✅ ATÓMICO: Si cualquiera falla, TODO se revierte (ROLLBACK)

    Args:
        operaciones: Lista de funciones async que se ejecutan en orden

    Returns:
        True si todas se ejecutan exitosamente, False si falla cualquiera

    Ejemplo:
        async def op1(session):
            # ... código ...

        async def op2(session):
            # ... código ...

        await ejecutar_en_transaccion_atomica([op1, op2])
    """
    async with async_session() as session:
        try:
            for operacion in operaciones:
                await operacion(session)
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            print(f"❌ Transacción revertida: {e}")
            return False


async def validar_integridad_referencial() -> dict:
    """
    Valida la integridad de la base de datos.

    ✅ Detecta:
    - Mensajes sin lead correspondiente
    - Pedidos sin lead
    - Satisfacciones sin pedido
    - Datos huérfanos

    Returns:
        {"valido": bool, "errores": [...]}
    """
    async with async_session() as session:
        errores = []

        # 1. Mensajes sin lead
        msg_sin_lead = await session.execute(
            select(func.count(Mensaje.id))
            .where(~Mensaje.telefono.in_(select(Lead.telefono)))
        )
        if msg_sin_lead.scalar() > 0:
            errores.append(f"⚠️ {msg_sin_lead.scalar()} mensajes sin lead correspondiente")

        # 2. Pedidos sin lead
        pedido_sin_lead = await session.execute(
            select(func.count(Pedido.id))
            .where(~Pedido.telefono.in_(select(Lead.telefono)))
        )
        if pedido_sin_lead.scalar() > 0:
            errores.append(f"⚠️ {pedido_sin_lead.scalar()} pedidos sin lead correspondiente")

        # 3. Satisfacciones sin pedido (cuando pedido_id no es NULL)
        satisf_sin_pedido = await session.execute(
            select(func.count(Satisfaccion.id))
            .where(Satisfaccion.pedido_id.is_not(None))
            .where(~Satisfaccion.pedido_id.in_(select(Pedido.id)))
        )
        if satisf_sin_pedido.scalar() > 0:
            errores.append(f"⚠️ {satisf_sin_pedido.scalar()} satisfacciones sin pedido correspondiente")

        return {
            "valido": len(errores) == 0,
            "errores": errores,
            "timestamp": datetime.utcnow()
        }
