# 🔄 Migración: Habilitar Foreign Keys en SQLite

**Importante**: Si ya tienes una BD existente, sigue estos pasos para habilitar FK sin perder datos.

---

## Problema

SQLite tiene soporte para Foreign Keys, pero **POR DEFECTO está DESHABILITADO** por compatibilidad.

```sql
-- Por defecto:
PRAGMA foreign_keys;  -- Resultado: 0 (deshabilitado)

-- Esto permite insertar datos inconsistentes:
INSERT INTO mensajes (telefono, role, content) 
VALUES ("999999", "user", "Hola");  -- OK ✗ aunque no existe el lead
```

---

## Solución Implementada

### 1. En `agent/memory.py`

Se agregó la función `inicializar_db()` que ahora:

```python
async def inicializar_db():
    """Crea las tablas si no existen y habilita Foreign Keys."""
    async with engine.begin() as conn:
        # Habilitar Foreign Keys en SQLite
        if "sqlite" in DATABASE_URL:
            await conn.execute("PRAGMA foreign_keys = ON")

        # Crear todas las tablas
        await conn.run_sync(Base.metadata.create_all)

        # Verificar que las FK estén habilitadas
        if "sqlite" in DATABASE_URL:
            result = await conn.execute("PRAGMA foreign_keys")
            fk_enabled = (await result.fetchone())[0] == 1
            if fk_enabled:
                print("✅ Foreign Keys habilitadas en SQLite")
            else:
                print("⚠️ Foreign Keys NO habilitadas en SQLite")
```

### 2. En `agent/main.py`

Se llama `inicializar_db()` al startup:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de FastAPI."""
    # STARTUP
    logger.info("🚀 Iniciando AgentKit...")
    
    # ✅ NUEVO: Habilitar FK y crear tablas
    await inicializar_db()
    
    # Inicializar scheduler
    await inicializar_scheduler()
    
    logger.info("✅ AgentKit listo para producción")
    
    yield
    
    # SHUTDOWN
    await detener_scheduler()
    logger.info("👋 AgentKit detenido")
```

---

## Pasos para Migrar BD Existente

### Paso 1: Backup

```bash
# Crear copia de seguridad de la BD actual
cp /Users/victorcabanas/whatsapp-agentkit/agentkit.db \
   /Users/victorcabanas/whatsapp-agentkit/agentkit.db.backup.$(date +%Y%m%d_%H%M%S)

echo "✅ Backup creado"
```

### Paso 2: Validar Estado Actual

```bash
# Conectar a la BD
cd /Users/victorcabanas/whatsapp-agentkit

sqlite3 agentkit.db << EOF
-- Ver si las FK están habilitadas
PRAGMA foreign_keys;

-- Listar todas las tablas
.tables

-- Ver cantidad de registros
SELECT COUNT(*) FROM leads;
SELECT COUNT(*) FROM pedidos;
SELECT COUNT(*) FROM mensajes;
EOF
```

### Paso 3: Reemplazar BD Antigua (OPCIÓN A: Fácil)

La forma más segura es dejar que el código recree la BD:

```bash
# 1. Eliminar BD antigua (ya hiciste backup)
rm /Users/victorcabanas/whatsapp-agentkit/agentkit.db

# 2. Reiniciar el servidor
cd /Users/victorcabanas/whatsapp-agentkit
python agent/main.py  # O vía Docker

# 3. Al iniciar, se llama inicializar_db() que:
#    - Habilita PRAGMA foreign_keys = ON
#    - Crea todas las tablas (con FK)
#    - Verifica que funcionan
```

### Paso 4: Restaurar Datos (Si tienes backup sin FK)

Si necesitas restaurar datos de una BD anterior:

```bash
# 1. Abrir BD vieja
sqlite3 agentkit.db.backup

# 2. Exportar estructura sin datos
.schema > schema.sql

# 3. Salir
.exit

# 4. Crear BD nueva (que se genera con inicializar_db())
# Ya está creada en Paso 3

# 5. Importar SOLO datos compatibles
# (Si los datos vieja no violan las nuevas FK, puedes hacer)

sqlite3 agentkit.db << EOF
-- Importar leads
INSERT INTO leads SELECT * FROM agentkit.db.backup WHERE ... ;

-- Importar mensajes (solo si tienen lead correspondiente)
INSERT INTO mensajes SELECT m.* FROM agentkit.db.backup.mensajes m
WHERE EXISTS (SELECT 1 FROM leads l WHERE l.telefono = m.telefono);

-- etc para otras tablas
EOF
```

---

## Opción B: Migración Manual (Avanzada)

Si necesitas preservar exactamente tu BD antigua:

```bash
# 1. Exportar BD vieja sin FK
sqlite3 agentkit.db.backup << EOF
.mode insert
.output /tmp/datos.sql

SELECT * FROM leads;
SELECT * FROM pedidos;
SELECT * FROM mensajes;
SELECT * FROM satisfaccion;
SELECT * FROM carritos_abandonados;

.quit
EOF

# 2. Crear BD nueva con FK
rm agentkit.db
# El servidor la recrea con inicializar_db()

# 3. Importar datos (respetando FK)
sqlite3 agentkit.db << EOF
PRAGMA foreign_keys = ON;

-- Importar leads primero (tabla principal)
.read /tmp/datos.sql

-- Verificar integridad
PRAGMA foreign_key_check;

EOF
```

---

## Verificar Migración Exitosa

```bash
sqlite3 agentkit.db << EOF
-- 1. Verificar que FK está ON
PRAGMA foreign_keys;  -- Debe retornar: 1

-- 2. Ver estructura con FK
.schema leads
.schema pedidos
.schema mensajes

-- 3. Ver índices creados
.indexes

-- 4. Verificar que no hay datos huérfanos
-- (Si hay, significaría que los datos vieja violan las FK)
PRAGMA foreign_key_check;  -- Si está vacío = OK

-- 5. Ver cantidad de registros
SELECT COUNT(*) as total_leads FROM leads;
SELECT COUNT(*) as total_pedidos FROM pedidos;
SELECT COUNT(*) as total_mensajes FROM mensajes;

.quit
EOF
```

---

## Troubleshooting

### Error: "FOREIGN KEY constraint failed"

**Causa**: Intentaste insertar datos que violan FK.

```python
# Ejemplo que falla:
await guardar_mensaje("595999999999", "user", "Hola")
# Lead 595999999999 no existe → FK violation → ValueError

# Solución:
lead = await registrar_lead("595999999999", "")
await guardar_mensaje("595999999999", "user", "Hola")  # OK ✓
```

### Error: "database is locked"

**Causa**: Otro proceso está usando la BD.

```bash
# 1. Ver qué proceso está usando la BD
lsof | grep agentkit.db

# 2. Matar el proceso (si es seguro)
kill -9 <PID>

# 3. Reiniciar servidor
```

### FK No se habilitó

**Causa**: La inicialización falló silenciosamente.

```python
# En logs del servidor, busca:
# "✅ Foreign Keys habilitadas" - OK
# "⚠️ Foreign Keys NO habilitadas" - Problema

# Solución: Ejecutar manualmente
sqlite3 agentkit.db "PRAGMA foreign_keys = ON;"
```

---

## Testing Post-Migración

### Test 1: Verificar FK Funciona

```python
# Esto DEBE fallar ahora
try:
    await guardar_mensaje("999999999", "user", "Test")
    print("❌ FALLA: FK no está funcionando")
except ValueError:
    print("✅ OK: FK está activa")
```

### Test 2: Verificar Atomicidad

```python
# Crear lead
lead = await registrar_lead("595991234567", "Test")
assert lead.fue_cliente == False

# Guardar pedido (debe actualizar lead)
pedido = await guardar_pedido_atomico(
    telefono="595991234567",
    producto="Producto",
    precio="100000",
    metodo_pago="transferencia"
)

# Verificar que lead se actualizó
lead_updated = await obtener_lead("595991234567")
assert lead_updated.fue_cliente == True  # ✅ Debe ser True
```

### Test 3: Verificar Índices

```sql
-- En SQLite
.indexes leads
.indexes pedidos
.indexes mensajes

-- Debes ver índices compuestos:
-- ix_mensaje_telefono_timestamp
-- ix_pedido_telefono_estado
-- etc
```

---

## Checklist Post-Migración

- [ ] BD antigua respaldada en backup
- [ ] Nuevo código (con FK) descargado
- [ ] `inicializar_db()` ejecutada exitosamente
- [ ] `PRAGMA foreign_keys = 1` verificado
- [ ] Datos importados sin errores de FK
- [ ] `PRAGMA foreign_key_check` retorna vacío
- [ ] Tests de integridad pasados
- [ ] Endpoint `/api/admin/integridad` retorna "valido": true
- [ ] Logs no muestran errores de FK
- [ ] Servidor inicia sin problemas

---

## Rollback (Si algo sale mal)

```bash
# Restaurar BD antigua
cp agentkit.db.backup.<timestamp> agentkit.db

# Reiniciar servidor
# Volverá a funcionar sin FK (pero sin garantías de integridad)
```

---

## Próxima Vez: PostgreSQL

Si crece la base de datos y necesitas:
- ✅ Mejor performance
- ✅ Múltiples procesos accediendo simultaneamente
- ✅ Replicación

Migrar a PostgreSQL es trivial:

```python
# Solo cambiar la URL en .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/agentkit_db

# El resto del código NO CAMBIA (mismo SQLAlchemy)
# Las FK funcionarán igual o mejor
```

---

**🎯 Migración: COMPLETADA**
