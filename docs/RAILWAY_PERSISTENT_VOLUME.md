# 🔴 PROBLEMA CRÍTICO: Base de Datos se pierde en Railway

## ¿Qué pasó?

Cada vez que hacemos un redeploy en Railway, la base de datos SQLite se **elimina** porque el contenedor se recrea y el volumen temporal se descarta.

**Evidencia:**
- Local (tu máquina): `agentkit.db` persiste (64KB del 4 de abril)
- Railway: Se crea una BD nueva vacía en cada deploy
- Resultado: **Los 687 clientes importados se perdieron**

## Solución: Configurar Volumen Persistente en Railway

### Paso 1: Ir a Railway Dashboard
1. Abre https://railway.app
2. Ve a tu proyecto `whatsapp-agentkit`
3. Selecciona el servicio `whatsapp-agentkit`

### Paso 2: Crear Volumen
1. En el panel del servicio, busca la sección **"Volumes"**
2. Haz clic en **"+ Add Volume"**
3. Configura:
   - **Name**: `agentkit-db-volume` (o cualquier nombre)
   - **Mount Path**: `/app` (la ruta donde está agentkit.db)

### Paso 3: Verificar
- El volumen debe mostrar:
  ```
  agentkit-db-volume  →  /app
  ```
- Después de esto, cada redeploy preservará los archivos en `/app`

## Alternativa: Usar PostgreSQL (RECOMENDADO para Producción)

Si prefieres algo más robusto, Railway ofrece PostgreSQL como servicio:

### Opción A: PostgreSQL en Railway
1. En tu proyecto, haz clic **"+ Add Service"**
2. Selecciona **"PostgreSQL"**
3. Railway te dará una `DATABASE_URL`
4. Actualiza tu `.env` en Railway:
   ```
   DATABASE_URL=postgresql+asyncpg://user:pass@postgres-service/dbname
   ```
5. El código de SQLAlchemy funciona exactamente igual (solo cambia la URL)

### Opción B: Mantener SQLite pero con volumen persistente
Es la opción que recomendé arriba.

## Código actual vs cambios necesarios

### Actual (SQLite local - NO funciona en Railway sin volumen)
```python
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")
```

### Con volumen persistente (✅ Funciona)
```python
# En .env local:
DATABASE_URL=sqlite+aiosqlite:///./agentkit.db

# En Railway (variable de entorno):
DATABASE_URL=sqlite+aiosqlite:///./agentkit.db
# + Volumen montado en /app
```

### Con PostgreSQL (✅ Mejor para producción)
```python
# En Railway (variable de entorno):
DATABASE_URL=postgresql+asyncpg://user:pass@postgres.railway.internal:5432/railway
```

## Próximos pasos INMEDIATOS

### 1. Configura el volumen en Railway (CRÍTICO)
- Sin esto, cada deploy pierde datos
- Haz esto AHORA antes de que se pierdan más datos

### 2. Re-importa los 687 clientes
Una vez que tengas el volumen configurado:
1. Accede al dashboard
2. Ve al tab "Importados"
3. Carga nuevamente tu archivo Meta (tengo un script para automatizar si quieres)

### 3. Crea un procedimiento de backup
```bash
# Bajar la BD actual de Railway
scp -r railway@app:/app/agentkit.db ./backup-$(date +%Y%m%d).db

# O:
railway run cp agentkit.db /tmp/backup.db
```

## Documentación Railway Oficial
- Volúmenes: https://docs.railway.app/deploy/volumes
- Variables de entorno: https://docs.railway.app/develop/variables
- PostgreSQL: https://docs.railway.app/databases/postgresql

## ⚠️ IMPORTANTE

**No hagas más redeploys hasta configurar el volumen persistente**, de lo contrario seguirás perdiendo datos.

Si ya perdiste los datos nuevamente, aquí hay 2 opciones:
1. **Re-importar desde Meta** (archivo que tenías)
2. **Restaurar desde backup** (si hiciste uno)
