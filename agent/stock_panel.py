"""
Panel interactivo de stock — Actualiza inventario en tiempo real
API endpoints para ver y editar stock
"""

import os
import json
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger("stock_panel")

router = APIRouter()
# Path absoluto: sube un nivel desde agent/ para llegar a la raíz del proyecto
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCK_FILE = os.path.join(_BASE_DIR, "knowledge", "stock_actual.json")


def load_stock():
    """Carga stock desde archivo"""
    if not os.path.exists(STOCK_FILE):
        return {"productos": {}, "ultima_actualizacion": datetime.now().isoformat()}

    try:
        with open(STOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error leyendo stock: {e}")
        return {"productos": {}, "ultima_actualizacion": datetime.now().isoformat()}


def save_stock(data):
    """Guarda stock a archivo"""
    try:
        data["ultima_actualizacion"] = datetime.now().isoformat()
        with open(STOCK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Stock guardado - {len(data['productos'])} productos")
    except Exception as e:
        logger.error(f"Error guardando stock: {e}")
        raise


@router.get("/api/stock", response_model=dict)
async def get_stock():
    """Retorna todo el stock actual (API para el panel)"""
    return load_stock()


@router.post("/api/stock/{product_id}")
async def update_stock(product_id: str, stock: int):
    """Actualiza stock de UN producto"""
    if stock < 0:
        raise HTTPException(status_code=400, detail="Stock no puede ser negativo")

    data = load_stock()

    if product_id not in data["productos"]:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    data["productos"][product_id]["stock"] = stock
    data["productos"][product_id]["disponible"] = stock > 0
    data["productos"][product_id]["timestamp"] = datetime.now().isoformat()

    save_stock(data)

    return {
        "status": "ok",
        "producto": data["productos"][product_id]
    }


@router.post("/api/stock/{product_id}/add")
async def add_stock(product_id: str, cantidad: int = 1):
    """Suma stock a un producto"""
    data = load_stock()

    if product_id not in data["productos"]:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    data["productos"][product_id]["stock"] += cantidad
    data["productos"][product_id]["disponible"] = data["productos"][product_id]["stock"] > 0
    data["productos"][product_id]["timestamp"] = datetime.now().isoformat()

    save_stock(data)
    logger.info(f"Stock +{cantidad}: {data['productos'][product_id]['nombre']}")

    return {
        "status": "ok",
        "producto": data["productos"][product_id]
    }


@router.post("/api/stock/{product_id}/subtract")
async def subtract_stock(product_id: str, cantidad: int = 1):
    """Resta stock a un producto"""
    data = load_stock()

    if product_id not in data["productos"]:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    nuevo_stock = data["productos"][product_id]["stock"] - cantidad

    if nuevo_stock < 0:
        raise HTTPException(status_code=400, detail="Stock insuficiente")

    data["productos"][product_id]["stock"] = nuevo_stock
    data["productos"][product_id]["disponible"] = nuevo_stock > 0
    data["productos"][product_id]["timestamp"] = datetime.now().isoformat()

    save_stock(data)
    logger.info(f"Stock -{cantidad}: {data['productos'][product_id]['nombre']}")

    return {
        "status": "ok",
        "producto": data["productos"][product_id]
    }


@router.get("/panel/stock", response_class=HTMLResponse)
async def panel_stock():
    """Panel web interactivo para gestionar stock"""
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Panel de Stock — Rebody</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

    :root {
      --purple:    #8B5CF6;
      --purple-lt: #C4B5FD;
      --purple-bg: #EDE9FE;
      --green:     #10B981;
      --green-bg:  #D1FAE5;
      --green-txt: #065F46;
      --amber:     #F59E0B;
      --amber-bg:  #FEF3C7;
      --amber-txt: #92400E;
      --red:       #EF4444;
      --red-bg:    #FEE2E2;
      --red-txt:   #991B1B;
      --bg:        #FAF5FF;
      --text:      #1E1B4B;
      --text-muted:#6B7280;
      --border:    #E5E7EB;
      --white:     #FFFFFF;
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 16px;
      --shadow-sm: 0 1px 3px rgba(0,0,0,.08);
      --shadow-md: 0 4px 16px rgba(139,92,246,.12);
      --shadow-lg: 0 8px 32px rgba(139,92,246,.18);
    }

    html { font-size: 16px; }

    body {
      font-family: 'Fira Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 24px 16px 48px;
    }

    /* ── Layout ── */
    .page { max-width: 1100px; margin: 0 auto; }

    /* ── Header ── */
    .header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 16px;
      margin-bottom: 28px;
    }
    .header-left { flex: 1; min-width: 200px; }
    .header-title {
      font-family: 'Fira Code', monospace;
      font-size: 1.5rem;
      font-weight: 600;
      color: var(--text);
      letter-spacing: -.5px;
    }
    .header-title span { color: var(--purple); }
    .badge-update {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: .75rem;
      color: var(--text-muted);
      background: var(--white);
      border: 1px solid var(--border);
      border-radius: 99px;
      padding: 3px 10px;
      margin-top: 6px;
    }
    .badge-update .dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--green);
      flex-shrink: 0;
    }
    .badge-update.refreshing .dot {
      background: var(--amber);
      animation: pulse 1s infinite;
    }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

    .btn-refresh {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-family: 'Fira Sans', sans-serif;
      font-size: .875rem;
      font-weight: 600;
      color: var(--white);
      background: var(--purple);
      border: none;
      border-radius: var(--radius-md);
      padding: 10px 18px;
      cursor: pointer;
      transition: background .15s, transform .1s;
      min-height: 44px;
    }
    .btn-refresh:hover { background: #7C3AED; }
    .btn-refresh:active { transform: scale(.97); }
    .btn-refresh svg { flex-shrink: 0; }

    /* ── KPI Cards ── */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 28px;
    }
    @media (max-width: 768px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 400px) { .kpi-grid { grid-template-columns: 1fr; } }

    .kpi-card {
      background: var(--white);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 20px;
      box-shadow: var(--shadow-sm);
    }
    .kpi-card .kpi-label {
      font-size: .75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--text-muted);
      margin-bottom: 8px;
    }
    .kpi-card .kpi-value {
      font-family: 'Fira Code', monospace;
      font-size: 2rem;
      font-weight: 600;
      line-height: 1;
    }
    .kpi-card.total  .kpi-value { color: var(--purple); }
    .kpi-card.disp   .kpi-value { color: var(--green); }
    .kpi-card.bajo   .kpi-value { color: var(--amber); }
    .kpi-card.agot   .kpi-value { color: var(--red); }

    /* ── Toolbar ── */
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      margin-bottom: 20px;
    }
    .search-wrap {
      position: relative;
      flex: 1;
      min-width: 200px;
    }
    .search-wrap svg {
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-muted);
      pointer-events: none;
    }
    .search-input {
      width: 100%;
      padding: 10px 12px 10px 38px;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      font-family: 'Fira Sans', sans-serif;
      font-size: .9rem;
      color: var(--text);
      background: var(--white);
      transition: border-color .15s, box-shadow .15s;
      min-height: 44px;
    }
    .search-input:focus {
      outline: none;
      border-color: var(--purple);
      box-shadow: 0 0 0 3px rgba(139,92,246,.15);
    }

    .tabs { display: flex; gap: 6px; flex-wrap: wrap; }
    .tab {
      font-family: 'Fira Sans', sans-serif;
      font-size: .8rem;
      font-weight: 600;
      padding: 8px 14px;
      border-radius: 99px;
      border: 1.5px solid var(--border);
      background: var(--white);
      color: var(--text-muted);
      cursor: pointer;
      transition: all .15s;
      min-height: 36px;
    }
    .tab:hover { border-color: var(--purple-lt); color: var(--purple); }
    .tab.active { background: var(--purple); border-color: var(--purple); color: var(--white); }

    /* ── Category sections ── */
    .category-section { margin-bottom: 16px; }

    .category-header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 16px;
      background: var(--white);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      cursor: pointer;
      user-select: none;
      transition: background .15s;
    }
    .category-section.open .category-header { border-radius: var(--radius-md) var(--radius-md) 0 0; border-bottom: none; }
    .category-header:hover { background: var(--purple-bg); }
    .category-name {
      font-family: 'Fira Code', monospace;
      font-size: .85rem;
      font-weight: 600;
      color: var(--purple);
      text-transform: uppercase;
      letter-spacing: .08em;
      flex: 1;
    }
    .category-count {
      font-family: 'Fira Code', monospace;
      font-size: .75rem;
      background: var(--purple-bg);
      color: var(--purple);
      border-radius: 99px;
      padding: 2px 9px;
    }
    .chevron {
      color: var(--text-muted);
      transition: transform .2s;
      flex-shrink: 0;
    }
    .category-section.open .chevron { transform: rotate(180deg); }

    /* ── Table ── */
    .table-wrap {
      border: 1px solid var(--border);
      border-top: none;
      border-radius: 0 0 var(--radius-md) var(--radius-md);
      overflow: hidden;
      display: none;
    }
    .category-section.open .table-wrap { display: block; }

    table { width: 100%; border-collapse: collapse; }
    thead th {
      background: #F5F3FF;
      font-size: .75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--text-muted);
      padding: 10px 16px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    thead th.th-stock { text-align: center; }
    thead th.th-actions { text-align: center; }

    tbody tr {
      border-bottom: 1px solid var(--border);
      transition: background .12s;
    }
    tbody tr:last-child { border-bottom: none; }
    tbody tr:hover { background: #FAFAFF; }
    tbody tr.flash-ok {
      animation: rowFlash .6s ease-out;
    }
    @keyframes rowFlash {
      0%   { background: #D1FAE5; }
      100% { background: transparent; }
    }

    td { padding: 12px 16px; vertical-align: middle; }
    td.td-nombre {
      font-size: .9rem;
      font-weight: 500;
      color: var(--text);
    }
    td.td-stock { text-align: center; }
    td.td-badge { text-align: center; }
    td.td-actions { text-align: center; white-space: nowrap; }

    /* ── Stock input ── */
    .stock-input {
      font-family: 'Fira Code', monospace;
      font-size: .95rem;
      font-weight: 500;
      width: 72px;
      padding: 7px 6px;
      text-align: center;
      border: 1.5px solid var(--border);
      border-radius: var(--radius-sm);
      color: var(--text);
      background: var(--white);
      transition: border-color .15s, box-shadow .15s;
      min-height: 44px;
    }
    .stock-input:focus {
      outline: none;
      border-color: var(--purple);
      box-shadow: 0 0 0 3px rgba(139,92,246,.15);
    }
    /* hide spinner arrows */
    .stock-input::-webkit-inner-spin-button,
    .stock-input::-webkit-outer-spin-button { -webkit-appearance: none; }
    .stock-input[type=number] { -moz-appearance: textfield; }

    /* ── Badge estado ── */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: .75rem;
      font-weight: 600;
      border-radius: 99px;
      padding: 4px 10px;
    }
    .badge-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .badge.disponible { background: var(--green-bg); color: var(--green-txt); }
    .badge.disponible .badge-dot { background: var(--green); }
    .badge.bajo       { background: var(--amber-bg); color: var(--amber-txt); }
    .badge.bajo       .badge-dot { background: var(--amber); }
    .badge.agotado    { background: var(--red-bg);   color: var(--red-txt);   }
    .badge.agotado    .badge-dot { background: var(--red); }

    /* ── Action buttons ── */
    .btn-adj {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 44px;
      border: 1.5px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--white);
      color: var(--text-muted);
      cursor: pointer;
      transition: all .15s;
      font-size: 1.1rem;
      vertical-align: middle;
    }
    .btn-adj:hover { border-color: var(--purple); color: var(--purple); background: var(--purple-bg); }
    .btn-adj.minus:hover { border-color: var(--red); color: var(--red); background: var(--red-bg); }
    .btn-adj:active { transform: scale(.93); }
    .btn-adj + .btn-adj { margin-left: 6px; }

    /* ── Toast ── */
    #toast-container {
      position: fixed;
      bottom: 24px;
      right: 24px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      z-index: 9999;
      pointer-events: none;
    }
    .toast {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 18px;
      border-radius: var(--radius-md);
      font-size: .875rem;
      font-weight: 600;
      box-shadow: var(--shadow-lg);
      animation: toastIn .25s ease-out;
      pointer-events: auto;
      max-width: 300px;
    }
    .toast.ok  { background: var(--green); color: var(--white); }
    .toast.err { background: var(--red);   color: var(--white); }
    @keyframes toastIn {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    .toast-fade {
      animation: toastOut .3s ease-in forwards;
    }
    @keyframes toastOut {
      to { opacity: 0; transform: translateY(8px); }
    }

    /* ── Empty / Loading states ── */
    .state-msg {
      text-align: center;
      padding: 48px 24px;
      color: var(--text-muted);
      font-size: .95rem;
    }
    .state-msg svg { display: block; margin: 0 auto 12px; opacity: .4; }

    /* ── Responsive ── */
    @media (max-width: 600px) {
      .header-title { font-size: 1.2rem; }
      td { padding: 10px 12px; }
      .stock-input { width: 60px; }
    }
  </style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <header class="header">
    <div class="header-left">
      <h1 class="header-title">Panel de Stock <span>— Rebody</span></h1>
      <div class="badge-update" id="badge-update">
        <span class="dot"></span>
        <span id="ultima-fecha">Cargando...</span>
      </div>
    </div>
    <button class="btn-refresh" onclick="cargarStock(true)" aria-label="Actualizar stock">
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
      </svg>
      Actualizar
    </button>
  </header>

  <!-- KPI cards -->
  <div class="kpi-grid">
    <div class="kpi-card total">
      <div class="kpi-label">Total Productos</div>
      <div class="kpi-value" id="kpi-total">—</div>
    </div>
    <div class="kpi-card disp">
      <div class="kpi-label">Disponibles</div>
      <div class="kpi-value" id="kpi-disp">—</div>
    </div>
    <div class="kpi-card bajo">
      <div class="kpi-label">Bajo Stock</div>
      <div class="kpi-value" id="kpi-bajo">—</div>
    </div>
    <div class="kpi-card agot">
      <div class="kpi-label">Agotados</div>
      <div class="kpi-value" id="kpi-agot">—</div>
    </div>
  </div>

  <!-- Toolbar -->
  <div class="toolbar">
    <div class="search-wrap">
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="8"/><path stroke-linecap="round" d="M21 21l-4.35-4.35"/>
      </svg>
      <input
        type="search"
        id="search-input"
        class="search-input"
        placeholder="Buscar producto..."
        aria-label="Buscar producto"
        oninput="aplicarFiltros()"
      >
    </div>
    <div class="tabs" role="tablist" aria-label="Filtrar por estado">
      <button class="tab active" role="tab" aria-selected="true"  data-tab="todos"      onclick="setTab(this)">Todos</button>
      <button class="tab"        role="tab" aria-selected="false" data-tab="disponible" onclick="setTab(this)">Disponible</button>
      <button class="tab"        role="tab" aria-selected="false" data-tab="bajo"       onclick="setTab(this)">Bajo Stock</button>
      <button class="tab"        role="tab" aria-selected="false" data-tab="agotado"    onclick="setTab(this)">Agotado</button>
    </div>
  </div>

  <!-- Table area -->
  <div id="main-content">
    <div class="state-msg" id="loading-msg">
      <svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zM16 3H8l-2 4h12l-2-4z"/>
      </svg>
      Cargando inventario...
    </div>
  </div>

</div>

<!-- Toast container -->
<div id="toast-container" aria-live="polite" aria-atomic="false"></div>

<script>
  /* ─── State ─── */
  let stockData = {};
  let tabActivo = 'todos';
  let refreshTimer = null;

  /* ─── Categorization ─── */
  const CATEGORIAS_ORDER = ['WHOOP', 'Theragun', 'TheraFace', 'JetBoots', 'Otros'];

  function getCategoria(nombre) {
    if (!nombre) return 'Otros';
    const n = nombre.trim();
    if (n.startsWith('WHOOP'))     return 'WHOOP';
    if (n.startsWith('Theragun'))  return 'Theragun';
    if (n.startsWith('TheraFace')) return 'TheraFace';
    if (n.startsWith('JetBoots')) return 'JetBoots';
    return 'Otros';
  }

  /* ─── Badge helpers ─── */
  function badgeClass(stock) {
    if (stock === 0)      return 'agotado';
    if (stock <= 2)       return 'bajo';
    return 'disponible';
  }
  function badgeLabel(stock) {
    if (stock === 0)  return 'Agotado';
    if (stock <= 2)   return 'Bajo stock';
    return 'Disponible';
  }

  /* ─── Load ─── */
  async function cargarStock(manual = false) {
    const badge = document.getElementById('badge-update');
    badge.classList.add('refreshing');
    document.getElementById('ultima-fecha').textContent = 'Actualizando...';

    try {
      const res = await fetch('/api/stock');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      stockData = await res.json();
      actualizarKPIs();
      renderCategorias();
      const fecha = new Date(stockData.ultima_actualizacion).toLocaleString('es-PY', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      });
      document.getElementById('ultima-fecha').textContent = 'Actualizado ' + fecha;
      badge.classList.remove('refreshing');
      if (manual) mostrarToast('Inventario actualizado', 'ok');
    } catch (err) {
      badge.classList.remove('refreshing');
      document.getElementById('ultima-fecha').textContent = 'Error al cargar';
      mostrarToast('Error al cargar inventario', 'err');
    }
  }

  /* ─── KPIs ─── */
  function actualizarKPIs() {
    const prods = Object.values(stockData.productos || {});
    const total = prods.length;
    const disp  = prods.filter(p => p.stock >= 3).length;
    const bajo  = prods.filter(p => p.stock === 1 || p.stock === 2).length;
    const agot  = prods.filter(p => p.stock === 0).length;
    document.getElementById('kpi-total').textContent = total;
    document.getElementById('kpi-disp').textContent  = disp;
    document.getElementById('kpi-bajo').textContent  = bajo;
    document.getElementById('kpi-agot').textContent  = agot;
  }

  /* ─── Filters ─── */
  function setTab(btn) {
    document.querySelectorAll('.tab').forEach(t => {
      t.classList.remove('active');
      t.setAttribute('aria-selected', 'false');
    });
    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
    tabActivo = btn.dataset.tab;
    aplicarFiltros();
  }

  function filtrarProductos() {
    const query = document.getElementById('search-input').value.toLowerCase().trim();
    return Object.values(stockData.productos || {}).filter(p => {
      const matchSearch = !query || p.nombre.toLowerCase().includes(query);
      const bc = badgeClass(p.stock);
      const matchTab =
        tabActivo === 'todos' ||
        (tabActivo === 'disponible' && bc === 'disponible') ||
        (tabActivo === 'bajo'       && bc === 'bajo') ||
        (tabActivo === 'agotado'    && bc === 'agotado');
      return matchSearch && matchTab;
    });
  }

  function aplicarFiltros() {
    renderCategorias();
  }

  /* ─── Render ─── */
  function renderCategorias() {
    const filtered = filtrarProductos();
    const container = document.getElementById('main-content');

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="state-msg">
          <svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
          Sin productos que coincidan.
        </div>`;
      return;
    }

    // Group by category
    const groups = {};
    CATEGORIAS_ORDER.forEach(c => { groups[c] = []; });
    filtered.forEach(p => {
      const cat = getCategoria(p.nombre);
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(p);
    });

    let html = '';
    CATEGORIAS_ORDER.forEach(cat => {
      const prods = groups[cat];
      if (!prods || prods.length === 0) return;

      // Remember collapse state
      const sectionId = 'cat-' + cat.replace(/\\s+/g, '-');
      const prevSection = document.getElementById(sectionId);
      const isOpen = prevSection ? prevSection.classList.contains('open') : true;

      html += `
        <div class="category-section ${isOpen ? 'open' : ''}" id="${sectionId}">
          <div class="category-header" onclick="toggleSection('${sectionId}')" role="button" aria-expanded="${isOpen}" aria-controls="${sectionId}-body" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){toggleSection('${sectionId}');event.preventDefault()}">
            <span class="category-name">${cat}</span>
            <span class="category-count">${prods.length}</span>
            <svg class="chevron" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/>
            </svg>
          </div>
          <div class="table-wrap" id="${sectionId}-body">
            <table>
              <thead>
                <tr>
                  <th>Producto</th>
                  <th class="th-stock">Stock</th>
                  <th>Estado</th>
                  <th class="th-actions">Acciones</th>
                </tr>
              </thead>
              <tbody>
                ${prods.map(p => renderFila(p)).join('')}
              </tbody>
            </table>
          </div>
        </div>`;
    });

    container.innerHTML = html;
  }

  function renderFila(prod) {
    const bc  = badgeClass(prod.stock);
    const bl  = badgeLabel(prod.stock);
    const id  = prod.id;
    return `
      <tr id="row-${id}">
        <td class="td-nombre">${escapeHtml(prod.nombre)}</td>
        <td class="td-stock">
          <input
            type="number"
            class="stock-input"
            id="stock-${id}"
            value="${prod.stock}"
            min="0"
            aria-label="Stock de ${escapeHtml(prod.nombre)}"
            onblur="guardarStock('${id}')"
            onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur()}"
          >
        </td>
        <td class="td-badge">
          <span class="badge ${bc}" id="badge-${id}">
            <span class="badge-dot"></span>${bl}
          </span>
        </td>
        <td class="td-actions">
          <button
            class="btn-adj minus"
            onclick="ajustarStock('${id}', 'subtract')"
            aria-label="Restar 1 a ${escapeHtml(prod.nombre)}"
            title="Restar 1"
          >
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" d="M20 12H4"/>
            </svg>
          </button>
          <button
            class="btn-adj"
            onclick="ajustarStock('${id}', 'add')"
            aria-label="Sumar 1 a ${escapeHtml(prod.nombre)}"
            title="Sumar 1"
          >
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" d="M12 4v16m8-8H4"/>
            </svg>
          </button>
        </td>
      </tr>`;
  }

  /* ─── Section collapse ─── */
  function toggleSection(id) {
    const sec = document.getElementById(id);
    if (!sec) return;
    const open = sec.classList.toggle('open');
    const hdr  = sec.querySelector('.category-header');
    if (hdr) hdr.setAttribute('aria-expanded', String(open));
  }

  /* ─── Update single row (no full re-render) ─── */
  function actualizarFila(id, nuevoStock) {
    stockData.productos[id].stock      = nuevoStock;
    stockData.productos[id].disponible = nuevoStock > 0;

    const input = document.getElementById('stock-' + id);
    const badge = document.getElementById('badge-' + id);
    const row   = document.getElementById('row-' + id);

    if (input) input.value = nuevoStock;

    if (badge) {
      const bc = badgeClass(nuevoStock);
      const bl = badgeLabel(nuevoStock);
      badge.className = 'badge ' + bc;
      badge.innerHTML = `<span class="badge-dot"></span>${bl}`;
    }

    if (row) {
      row.classList.remove('flash-ok');
      void row.offsetWidth; // reflow
      row.classList.add('flash-ok');
    }

    actualizarKPIs();
  }

  /* ─── API calls ─── */
  async function guardarStock(id) {
    const input = document.getElementById('stock-' + id);
    if (!input) return;
    const nuevoStock = parseInt(input.value, 10);
    if (isNaN(nuevoStock) || nuevoStock < 0) {
      // restore original
      input.value = stockData.productos[id]?.stock ?? 0;
      return;
    }
    // Skip if unchanged
    if (stockData.productos[id] && stockData.productos[id].stock === nuevoStock) return;

    try {
      const res = await fetch(`/api/stock/${id}?stock=${nuevoStock}`, { method: 'POST' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      actualizarFila(id, data.producto.stock);
      mostrarToast('Stock actualizado', 'ok');
    } catch (err) {
      input.value = stockData.productos[id]?.stock ?? 0;
      mostrarToast('Error al guardar', 'err');
    }
  }

  async function ajustarStock(id, op) {
    const endpoint = op === 'add'
      ? `/api/stock/${id}/add?cantidad=1`
      : `/api/stock/${id}/subtract?cantidad=1`;

    try {
      const res = await fetch(endpoint, { method: 'POST' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      actualizarFila(id, data.producto.stock);
      mostrarToast('Stock actualizado', 'ok');
    } catch (err) {
      mostrarToast('Error al guardar', 'err');
    }
  }

  /* ─── Toast ─── */
  function mostrarToast(msg, tipo) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast ' + tipo;
    const icon = tipo === 'ok'
      ? `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>`
      : `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>`;
    toast.innerHTML = icon + escapeHtml(msg);
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add('toast-fade');
      toast.addEventListener('animationend', () => toast.remove());
    }, 2800);
  }

  /* ─── Util ─── */
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  /* ─── Boot ─── */
  cargarStock(false);
  refreshTimer = setInterval(() => cargarStock(false), 60000);
</script>
</body>
</html>"""
