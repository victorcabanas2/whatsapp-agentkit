# AgentKit — Rebody WhatsApp Bot

Agente de WhatsApp con IA para Rebody (Paraguay). Vendedora digital "Belén" que atiende consultas de productos wellness (WHOOP, Theragun, JetBoots, FOREO, etc.).

---

## Stack actual (en producción)

| Capa | Tecnología |
|------|------------|
| Backend | Python 3.11 + FastAPI + Uvicorn |
| IA | Claude sonnet-4-6 (Anthropic API) — prompt caching activado |
| WhatsApp | Whapi.cloud |
| DB | SQLite vía SQLAlchemy async (agentkit.db) |
| CRM Dashboard | React Router v7 + Prisma + Shopify embedded app (app/) |
| Deploy | Railway (backend Python) + Shopify Partner (CRM) |
| Stock sync | Shopify Storefront API vía agent/shopify.py |

---

## Archivos clave

```
agent/
  main.py          — FastAPI + webhook Whapi + endpoints admin CRM
  brain.py         — Claude API, system prompt dinámico, FAQs pre-escritas
  memory.py        — SQLAlchemy async: Lead, Mensaje, Pedido, Auditoria
  scheduler.py     — Seguimientos automáticos (cron-like async tasks)
  shopify.py       — Stock en tiempo real via Shopify Storefront API
  ad_analyzer.py   — Mapeo anuncios Meta → productos
  stock_panel.py   — Router FastAPI para panel de stock
  admin_api.py     — Endpoints API para CRM externo
  admin_endpoints.py — Endpoints HTML admin panel
  providers/
    whapi.py       — Envío/recepción Whapi.cloud

config/
  business.yaml    — Datos Rebody: contacto, horario, pagos
  prompts.yaml     — System prompt de Belén (NO modificar sin leer brain.py)
  ads.yaml         — Mapeo ID anuncios Meta → nombres de producto
  shopify.yaml     — IDs productos Shopify para sync de stock

knowledge/
  catálogo_completo.json      — Catálogo con precios y specs (fuente de verdad)
  catálogo_búsqueda_rápida.json — Índice para búsquedas rápidas
  stock_actual.json           — Stock en vivo (actualizado por scheduler)
  imagenes_productos.json     — URLs imágenes Shopify por product_id

app/                — CRM dashboard (React Router + Shopify embedded)
  routes/dashboard.*  — Leads, conversaciones, campañas, pedidos

scripts/
  import_excel_to_db.py    — Importar clientes desde Excel a SQLite
  sync_shopify_stock.py    — Sync manual de stock Shopify
  create_demo_data.py      — Datos de prueba

tests/
  test_local.py            — Chat interactivo en terminal (simula WhatsApp)
  test_integridad.py       — Tests de integridad DB
  test_shopify_stock.py    — Tests de sync Shopify
  test_ads_and_replies.py  — Tests anuncios Meta
  test_debug_ads.py        — Debug anuncios
  test_debug_mapping.py    — Debug mapeo productos
```

---

## Variables de entorno críticas (.env)

```env
ANTHROPIC_API_KEY=sk-ant-...
WHAPI_TOKEN=...
WHATSAPP_PROVIDER=whapi
PORT=8000
ENVIRONMENT=development          # development | production
DATABASE_URL=sqlite+aiosqlite:///./agentkit.db
VENDEDOR_WHATSAPP=+595...        # Para alertas al vendedor
ADMIN_PASSWORD=...
ADMIN_WHATSAPP=+595986147509
CRM_SHARED_SECRET=...

# Shopify (para sync de stock)
SHOPIFY_STORE_DOMAIN=rebody.myshopify.com
SHOPIFY_STOREFRONT_TOKEN=...
SHOPIFY_ACCESS_TOKEN=...
```

---

## Comandos

```bash
# Arrancar bot local
uvicorn agent.main:app --reload --port 8000

# Test sin WhatsApp (chat en terminal)
python tests/test_local.py

# Sync stock manual
python scripts/sync_shopify_stock.py

# Importar clientes desde Excel
python scripts/import_excel_to_db.py

# Build Docker
docker compose up --build

# Deploy Railway
railway up

# Ver logs producción
railway logs --deployment
```

---

## Arquitectura del flujo de mensajes

```
WhatsApp cliente
    → Whapi.cloud webhook → POST /webhook
    → agent/providers/whapi.py (parsea)
    → agent/brain.py (FAQs pre-escritas → ahorra tokens)
    → Claude sonnet-4-6 con system prompt + historial (8 msgs)
    → Respuesta enviada por Whapi
    → agent/memory.py guarda Lead + Mensaje + Auditoria
    → agent/scheduler.py programa seguimientos automáticos
```

---

## Notas de arquitectura importantes

- **Prompt caching**: `brain.py` usa `cache_control: ephemeral` en el system prompt. No romper esto.
- **FAQs pre-escritas**: saludos y preguntas simples responden sin llamar a Claude (ahorra ~1000 tokens/msg).
- **Stock dinámico**: `brain.py` inyecta `stock_actual.json` en el system prompt en cada llamada.
- **Historial limitado a 8 mensajes**: `memory.py obtener_historial(limite=8)` — balance contexto/costo.
- **FK con CASCADE**: `memory.py` tiene foreign keys reales con ON DELETE CASCADE. No modificar schema sin revisar migraciones.
- **Seguimientos automáticos**: `scheduler.py` ejecuta tareas async en background. Se cancelan limpiamente en lifespan shutdown.
- **Imagen datos bancarios**: hardcodeada en `main.py` → `IMAGEN_DATOS_BANCARIOS`.
- **agentkit_memory.log**: generado por `memory.py`, no subir a Git (está en .gitignore).
