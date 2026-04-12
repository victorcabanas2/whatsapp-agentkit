# Dashboard Rebody - Status & Handoff (2026-04-11)

## ✅ COMPLETADO

**Infraestructura:**
- Tailwind CSS v4 instalado (`npm install -D tailwindcss @tailwindcss/vite`)
- Prisma schema extendido (Campaign + CampaignRecipient models)
- Migración aplicada (`npx prisma migrate dev --name add_crm_campaigns`)
- Bot API client: `/app/lib/bot-api.server.js` (todos los endpoints)
- Nuevo endpoint bot Python: `POST /api/admin/enviar-mensaje` (deployed)

**Rutas & Componentes:**
- ✅ `app/routes/dashboard.jsx` — Layout principal + sidebar nav
- ✅ `app/routes/dashboard._index.jsx` — Home dashboard (stats cards)
- ✅ `app/routes/dashboard.conversations.jsx` — Conversaciones + **BotToggle** (CRÍTICO - useFetcher optimista)
- ✅ `app/components/ui/Avatar.jsx` — Circle initials avatar
- ✅ `app/components/ui/IntentBadge.jsx` — hot/warm/cold badges
- ✅ `app/components/ui/BotToggle.jsx` — Bot ON/OFF toggle con optimistic UI

**Estado actual:**
- Dashboard carga en Shopify Admin (https://admin.shopify.com/store/rebody-dev/...)
- Versión dev funciona con mock data (try/catch en loaders)
- Bot está en production (Railway): https://whatsapp-agentkit-production-51ea.up.railway.app/

---

## ❌ FALTA (5 páginas + componentes extra)

### Páginas a crear (en orden):

1. **`app/routes/dashboard.leads.jsx`**
   - Loader: `getLeads("todos", 500)` 
   - UI: Filtros (todos/nuevos/hot/warm/cold/clientes), tabla sorteable
   - Columnas: Nombre | Teléfono | Score bar | Intención | Primer contacto | Último mensaje | Fue cliente | Acciones
   - Botón "Importar" → link a `/dashboard/leads/import`

2. **`app/routes/dashboard.leads.import.jsx`**
   - UI: Drag-drop zone + file picker (.xlsx, .xls, .csv)
   - Action: Recibe archivo → `importExcel(file)` → muestra resultados
   - Muestra: éxito count, duplicados, errores (primeros 10 con razón)
   - Datos: 654 clientes en `/Users/victorcabanas/whatsapp-agentkit/knowledge/clientes rebody importado.xlsx`

3. **`app/routes/dashboard.messages.jsx`**
   - UI: Autocomplete search para lead (name → dropdown)
   - Tabs: "Solo texto" | "Solo imagen" | "Texto + imagen"
   - Compose area (textarea o image picker)
   - Preview section
   - Action: Detecta intent, llama `sendMessage()` o `sendImage()`

4. **`app/routes/dashboard.campaigns.jsx`**
   - Loader: `db.campaign.findMany({ include: { recipients }, orderBy: { creadoEn: 'desc' } })`
   - UI: Tabla campaigns (Nombre | Audiencia | Total | Exitosos | Fallidos | Estado | Fecha | Actions)
   - Botón "Nueva campaña" → `/dashboard/campaigns/new`

5. **`app/routes/dashboard.campaigns.new.jsx`**
   - Loader: `getLeads("todos", 500)` para contar por intención
   - UI: 
     - Campo nombre
     - Radio buttons audiencia: Todos (N) | Solo Hot (N) | Solo Warm (N) | Solo Cold (N)
     - Tabs: Solo texto | Solo imagen | Texto + imagen
     - Compose area
     - "Se enviará a X contactos" preview
     - Botones: "Enviar ahora" | "Guardar borrador"
   - Action (multi-step):
     1. Create Campaign record (estado=sending)
     2. Filter leads by audiencia
     3. Create CampaignRecipient rows
     4. Loop leads + call `sendMessage()` o `sendImage()` con delay
     5. Update Campaign (estado=sent, exitosos/fallidos/total)
     6. Return result

6. **`app/routes/dashboard.orders.jsx`**
   - Loader: `getPedidos("todos", 100)`
   - UI: Filtros (todos/pendiente/pagado/cancelado)
   - Tabla: Teléfono | Producto | Precio | Método pago | Estado | Fecha

### Componentes extra a crear:

- `ScoreBar.jsx` — 0-100 horizontal bar (color by range)
- `PageHeader.jsx` — Page title + subtitle + action slot
- `StatCard.jsx` — KPI card (icon + label + value)

---

## 🚀 CÓMO CONTINUAR EN PRÓXIMA SESIÓN

**Di exactamente esto:**

```
"Continúa el dashboard Rebody. 
Falta:
- 5 páginas (leads, import, messages, campaigns/new, orders)
- 3 componentes (ScoreBar, PageHeader, StatCard)

Usa el mismo patrón:
- Try/catch en loaders con mock data
- useFetcher para actions
- Tailwind puro (sin custom utilities)
- Bot API via bot-api.server.js

Empieza con dashboard.leads.jsx. 
Orden: leads → import → messages → campaigns.jsx → campaigns.new.jsx → orders
Luego componentes."
```

---

## 📍 URLs & Archivos Clave

- **Dev Dashboard**: https://admin.shopify.com/store/rebody-dev/apps/e24cdd110755d821f5efdac2c9e9f0c2?dev-console=show
- **Bot API**: https://whatsapp-agentkit-production-51ea.up.railway.app
- **Bot API Client**: `/app/lib/bot-api.server.js` (todos los exports)
- **Excel clientes**: `/Users/victorcabanas/whatsapp-agentkit/knowledge/clientes rebody importado.xlsx` (654 rows)
- **Prisma Schema**: `/prisma/schema.prisma` (Session + Campaign + CampaignRecipient)

---

## 🔧 Quick Commands

```bash
# Arranca dev server
cd /Users/victorcabanas/agentkit-api
shopify app dev --use-localhost

# Prueba Prisma
npx prisma studio

# Genera client si cambias schema
npx prisma generate && npx prisma migrate dev
```

---

## 🎨 Design Reference

**Colors** (ya en Tailwind):
- Sidebar: `#0F0F0E`
- Content: `#FAFAF9`
- Border: `#E8E8E5`
- Hot: `#DC2626`, Warm: `#D97706`, Cold: `#71717A`
- Green CTA: `#16A34A`

**Density**: Compact tables (h-11 rows), no shadows, fast transitions (150ms)

---

**Last updated**: 2026-04-11 22:59
**Status**: Ready for next phase
