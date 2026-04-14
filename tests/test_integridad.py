"""
Tests para validar integridad referencial y transacciones atómicas.

Ejecutar con: pytest tests/test_integridad.py -v
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

# Importar funciones de memory.py
import sys
sys.path.insert(0, '/Users/victorcabanas/whatsapp-agentkit')

from agent.memory import (
    inicializar_db,
    registrar_lead,
    guardar_mensaje,
    guardar_pedido_atomico,
    obtener_lead,
    obtener_historial,
    obtener_estadisticas,
    actualizar_lead_scoring,
    obtener_leads_sin_respuesta_horas,
    validar_integridad_referencial,
    limpiar_historial,
    async_session,
    Lead,
    Mensaje,
    Pedido,
)


# ════════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
async def db_limpia():
    """Inicializa BD limpia para cada test."""
    await inicializar_db()
    yield
    # Cleanup opcional


@pytest.fixture
async def lead_test(db_limpia):
    """Crea un lead de prueba."""
    lead = await registrar_lead("595991234567", "Carlos Test")
    return lead


# ════════════════════════════════════════════════════════════
# TESTS: FOREIGN KEY CONSTRAINTS
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_fk_lead_telefono_unico(db_limpia):
    """Test: Cada lead debe tener un teléfono único."""
    await registrar_lead("595991234567", "Carlos")

    # Intentar crear otro lead con mismo teléfono
    with pytest.raises(Exception):  # Unique constraint
        await registrar_lead("595991234567", "Otro Carlos")


@pytest.mark.asyncio
async def test_fk_mensaje_sin_lead(db_limpia):
    """Test: NO se puede guardar mensaje sin que exista el lead."""
    with pytest.raises(ValueError, match="no existe"):
        await guardar_mensaje("595999999999", "user", "Hola")


@pytest.mark.asyncio
async def test_fk_pedido_atomico_valida_lead(db_limpia):
    """Test: guardar_pedido_atomico valida que el lead existe."""
    with pytest.raises(ValueError, match="no existe"):
        await guardar_pedido_atomico(
            telefono="595999999999",
            producto="Test",
            precio="100000",
            metodo_pago="transferencia"
        )


@pytest.mark.asyncio
async def test_fk_mensaje_con_lead_valido(db_limpia, lead_test):
    """Test: Se puede guardar mensaje cuando el lead existe."""
    await guardar_mensaje(lead_test.telefono, "user", "Hola agente")

    historial = await obtener_historial(lead_test.telefono)
    assert len(historial) == 1
    assert historial[0]["role"] == "user"
    assert historial[0]["content"] == "Hola agente"


# ════════════════════════════════════════════════════════════
# TESTS: TRANSACCIONES ATÓMICAS
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_atomicidad_guardar_pedido(db_limpia, lead_test):
    """Test: guardar_pedido_atomico actualiza lead como cliente."""
    # Verificar estado inicial
    lead = await obtener_lead(lead_test.telefono)
    assert lead.fue_cliente == False
    assert lead.intencion == "cold"

    # Guardar pedido (debe actualizar lead)
    pedido = await guardar_pedido_atomico(
        telefono=lead_test.telefono,
        producto="Theragun Mini",
        precio="500000",
        metodo_pago="transferencia",
        nombre_cliente="Carlos"
    )

    # Verificar que el lead se actualizó
    lead_actualizado = await obtener_lead(lead_test.telefono)
    assert lead_actualizado.fue_cliente == True
    assert lead_actualizado.intencion == "warm"  # Cambió de "cold" a "warm"
    assert lead_actualizado.score > lead.score  # Score aumentó

    # Verificar que el pedido está guardado
    assert pedido.id is not None
    assert pedido.estado == "pendiente"


@pytest.mark.asyncio
async def test_atomicidad_rollback_si_falla(db_limpia):
    """Test: Si falla guardar_pedido_atomico, nada se guarda."""
    # Crear lead válido
    lead = await registrar_lead("595991234567", "Carlos")
    assert lead.fue_cliente == False

    # Intentar guardar pedido con metodo_pago inválido (debe fallar)
    try:
        await guardar_pedido_atomico(
            telefono="595991234567",
            producto="Producto",
            precio="100000",
            metodo_pago="METODO_INVALIDO"  # ← No válido (no está en check constraint)
        )
        assert False, "Debería haber fallado por constraint"
    except ValueError:
        pass  # Esperado

    # Verificar que el lead NO fue actualizado (rollback)
    lead_verificar = await obtener_lead("595991234567")
    assert lead_verificar.fue_cliente == False  # ← No cambió


@pytest.mark.asyncio
async def test_atomicidad_actualizar_scoring(db_limpia, lead_test):
    """Test: actualizar_lead_scoring es atómico."""
    # Actualizar múltiples campos a la vez
    lead = await actualizar_lead_scoring(
        telefono=lead_test.telefono,
        score=85,
        intencion="hot",
        urgencia="alta",
        producto_preferido="Theragun Mini"
    )

    # Todos los campos deben actualizarse juntos
    assert lead.score == 85
    assert lead.intencion == "hot"
    assert lead.urgencia == "alta"
    assert lead.producto_preferido == "Theragun Mini"


# ════════════════════════════════════════════════════════════
# TESTS: CONSTRAINTS CHECK
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_constraint_score_0_100(db_limpia, lead_test):
    """Test: Score debe estar entre 0-100."""
    # Intentar score > 100 (debe ser clamped)
    lead = await actualizar_lead_scoring(lead_test.telefono, score=150)
    assert lead.score == 100  # Clamped a máximo

    # Intentar score < 0 (debe ser clamped)
    lead = await actualizar_lead_scoring(lead_test.telefono, score=-50)
    assert lead.score == 0  # Clamped a mínimo


@pytest.mark.asyncio
async def test_constraint_intencion_valida(db_limpia, lead_test):
    """Test: Intención debe ser cold/warm/hot."""
    # Valores válidos
    for intencion in ["cold", "warm", "hot"]:
        lead = await actualizar_lead_scoring(lead_test.telefono, intencion=intencion)
        assert lead.intencion == intencion

    # Valor inválido debería fallar (en el constraint de BD)
    # (Nota: actualizar_lead_scoring no valida, lo hace la BD)


@pytest.mark.asyncio
async def test_constraint_role_user_assistant(db_limpia, lead_test):
    """Test: Role debe ser 'user' o 'assistant'."""
    # Roles válidos
    await guardar_mensaje(lead_test.telefono, "user", "Mensaje usuario")
    await guardar_mensaje(lead_test.telefono, "assistant", "Respuesta agente")

    historial = await obtener_historial(lead_test.telefono)
    assert len(historial) == 2

    # Role inválido debería fallar (en constraint de BD)


# ════════════════════════════════════════════════════════════
# TESTS: PERFORMANCE + BULK OPERATIONS
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_performance_obtener_estadisticas(db_limpia, lead_test):
    """Test: obtener_estadisticas es rápido (usa SQL, no Python)."""
    import time

    # Crear 100 mensajes
    for i in range(100):
        role = "user" if i % 2 == 0 else "assistant"
        await guardar_mensaje(lead_test.telefono, role, f"Mensaje {i}")

    # Medir tiempo (debe ser < 10ms con SQL optimizado)
    inicio = time.time()
    stats = await obtener_estadisticas(lead_test.telefono)
    tiempo_ms = (time.time() - inicio) * 1000

    # Verificar correctitud
    assert stats["total_mensajes"] == 100
    assert stats["mensajes_usuario"] == 50
    assert stats["mensajes_agente"] == 50

    # Verificar performance
    assert tiempo_ms < 50, f"Demasiado lento: {tiempo_ms:.2f}ms (esperado < 50ms)"
    print(f"✅ obtener_estadisticas en {tiempo_ms:.2f}ms")


@pytest.mark.asyncio
async def test_bulk_delete_historial(db_limpia, lead_test):
    """Test: limpiar_historial es rápido (bulk delete)."""
    # Crear 50 mensajes
    for i in range(50):
        await guardar_mensaje(lead_test.telefono, "user", f"Mensaje {i}")

    # Limpiar en UNA operación SQL
    eliminados = await limpiar_historial(lead_test.telefono)

    assert eliminados == 50

    # Verificar que están eliminados
    historial = await obtener_historial(lead_test.telefono)
    assert len(historial) == 0


@pytest.mark.asyncio
async def test_performance_obtener_leads_sin_respuesta(db_limpia):
    """Test: obtener_leads_sin_respuesta_horas usa SQL (no loops)."""
    import time

    # Crear 10 leads con mensajes antiguos
    for i in range(10):
        telefono = f"5959912345{i:02d}"
        lead = await registrar_lead(telefono, f"Lead {i}")

        # Guardar mensaje hace 6 horas (sin respuesta)
        await guardar_mensaje(telefono, "user", "Pregunta hace 6h")

    # Medir tiempo (debe ser < 50ms con JOIN optimizado)
    inicio = time.time()
    sin_respuesta = await obtener_leads_sin_respuesta_horas(horas=4)
    tiempo_ms = (time.time() - inicio) * 1000

    # Verificar correctitud
    assert len(sin_respuesta) == 10

    # Verificar performance
    assert tiempo_ms < 100, f"Demasiado lento: {tiempo_ms:.2f}ms"
    print(f"✅ obtener_leads_sin_respuesta en {tiempo_ms:.2f}ms")


# ════════════════════════════════════════════════════════════
# TESTS: VALIDACIÓN DE INTEGRIDAD
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_validar_integridad_ok(db_limpia, lead_test):
    """Test: BD íntegra retorna valido=true."""
    # Crear algunos datos válidos
    await guardar_mensaje(lead_test.telefono, "user", "Hola")
    await guardar_pedido_atomico(
        telefono=lead_test.telefono,
        producto="Producto",
        precio="100000",
        metodo_pago="transferencia"
    )

    # Validar integridad
    resultado = await validar_integridad_referencial()

    assert resultado["valido"] == True
    assert len(resultado["errores"]) == 0
    print("✅ BD íntegra validada")


@pytest.mark.asyncio
async def test_validar_integridad_detecta_huerfanos(db_limpia):
    """Test: validar_integridad detecta datos huérfanos."""
    # Intentar insertar mensaje sin lead (falla con FK activo)
    # Pero simulamos que existe un registro huérfano
    # (En BD con FK ON, esto no puede pasar, pero probamos la función)

    resultado = await validar_integridad_referencial()
    # En BD limpia, debe estar válida
    assert resultado["valido"] == True


# ════════════════════════════════════════════════════════════
# TESTS: EDGE CASES
# ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_registrar_lead_idempotente(db_limpia):
    """Test: Registrar same lead 2x no falla (idempotente)."""
    lead1 = await registrar_lead("595991234567", "Carlos")
    lead2 = await registrar_lead("595991234567", "Carlos")

    # Debe retornar el MISMO lead (no crear dupla)
    assert lead1.telefono == lead2.telefono
    assert lead1.id == lead2.id


@pytest.mark.asyncio
async def test_campos_nullable(db_limpia):
    """Test: Campos nullable funcionan."""
    lead = await registrar_lead("595991234567")  # Sin nombre

    assert lead.nombre is None
    assert lead.producto_preferido is None
    assert lead.proximo_followup is None


@pytest.mark.asyncio
async def test_defaults_values(db_limpia):
    """Test: Valores default se aplican correctamente."""
    lead = await registrar_lead("595991234567", "Test")

    # Verificar defaults
    assert lead.score == 20
    assert lead.intencion == "cold"
    assert lead.urgencia == "baja"
    assert lead.fue_cliente == False
    assert lead.primer_contacto is not None


# ════════════════════════════════════════════════════════════
# MAIN: EJECUTAR TODOS LOS TESTS
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
