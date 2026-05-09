"""
Panel interactivo de stock — Actualiza inventario en tiempo real
API endpoints para ver y editar stock
"""

import os
import json
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("stock_panel")

router = APIRouter()
# Path absoluto: sube un nivel desde agent/ para llegar a la raíz del proyecto
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# DATA_DIR: en Railway apunta al volumen persistente; en local usa knowledge/
_DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(_BASE_DIR, "knowledge")
STOCK_FILE = os.path.join(_DATA_DIR, "stock_actual.json")
CONSIG_FILE = os.path.join(_DATA_DIR, "consignacion.json")
MOVIMIENTOS_FILE = os.path.join(_DATA_DIR, "movimientos.json")


# ── Pydantic models para consignacion ──

class TiendaCreate(BaseModel):
    nombre: str
    tipo: Optional[str] = "consignacion"
    direccion: Optional[str] = ""

class TiendaUpdate(BaseModel):
    nombre: Optional[str] = None
    direccion: Optional[str] = None

class ProductoCreate(BaseModel):
    nombre: str
    stock: int = 0
    notas: Optional[str] = ""
    fecha_entrega: Optional[str] = ""
    recibido_por: Optional[str] = ""

class ProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    stock: Optional[int] = None
    notas: Optional[str] = None


class MovimientoCreate(BaseModel):
    tipo: str  # "venta" | "reposicion" | "retiro" | "ajuste"
    producto: str
    cantidad: int  # para ajuste puede ser negativo
    ubicacion: str = "Solumedic"
    precio_venta: float = 0.0
    notas: str = ""
    fecha: str = ""  # ISO date string; si vacío usa now()
    recibido_por: str = ""


# ── Consignacion helpers ──

def load_consig():
    if not os.path.exists(CONSIG_FILE):
        return {"tiendas": [], "ultima_actualizacion": datetime.now().isoformat()}
    try:
        with open(CONSIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error leyendo consignacion: {e}")
        return {"tiendas": [], "ultima_actualizacion": datetime.now().isoformat()}


def save_consig(data):
    try:
        data["ultima_actualizacion"] = datetime.now().isoformat()
        with open(CONSIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando consignacion: {e}")
        raise


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


@router.get("/api/consignacion")
async def get_consignacion():
    data = load_consig()
    stock_data = load_stock()
    for tienda in data["tiendas"]:
        if tienda.get("tipo") == "principal":
            tienda["productos"] = [
                {
                    "id": prod_id,
                    "nombre": prod["nombre"],
                    "stock": prod["stock"],
                    "notas": "",
                    "fecha_entrega": prod.get("timestamp", ""),
                    "recibido_por": "",
                }
                for prod_id, prod in stock_data.get("productos", {}).items()
            ]
    return data


@router.post("/api/consignacion/tiendas")
async def crear_tienda(body: TiendaCreate):
    data = load_consig()
    nueva = {
        "id": uuid.uuid4().hex[:8],
        "nombre": body.nombre.strip(),
        "tipo": body.tipo if body.tipo in ("principal", "consignacion") else "consignacion",
        "direccion": body.direccion or "",
        "activa": True,
        "productos": []
    }
    data["tiendas"].append(nueva)
    save_consig(data)
    return {"status": "ok", "tienda": nueva}


@router.put("/api/consignacion/tiendas/{store_id}")
async def editar_tienda(store_id: str, body: TiendaUpdate):
    data = load_consig()
    tienda = next((t for t in data["tiendas"] if t["id"] == store_id), None)
    if not tienda:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    if body.nombre is not None:
        tienda["nombre"] = body.nombre.strip()
    if body.direccion is not None:
        tienda["direccion"] = body.direccion
    save_consig(data)
    return {"status": "ok", "tienda": tienda}


@router.delete("/api/consignacion/tiendas/{store_id}")
async def eliminar_tienda(store_id: str):
    if store_id == "solumedic":
        raise HTTPException(status_code=403, detail="No se puede eliminar la tienda principal")
    data = load_consig()
    original = len(data["tiendas"])
    data["tiendas"] = [t for t in data["tiendas"] if t["id"] != store_id]
    if len(data["tiendas"]) == original:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    save_consig(data)
    return {"status": "ok"}


@router.post("/api/consignacion/tiendas/{store_id}/productos")
async def agregar_producto(store_id: str, body: ProductoCreate):
    data = load_consig()
    tienda = next((t for t in data["tiendas"] if t["id"] == store_id), None)
    if not tienda:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    if tienda.get("tipo") == "principal":
        raise HTTPException(status_code=403, detail="Usa Stock Principal para agregar productos a esta tienda")
    if body.stock < 0:
        raise HTTPException(status_code=400, detail="Stock no puede ser negativo")
    nuevo = {
        "id": uuid.uuid4().hex[:8],
        "nombre": body.nombre.strip(),
        "stock": body.stock,
        "notas": body.notas or "",
        "fecha_entrega": body.fecha_entrega or datetime.now().isoformat(),
        "recibido_por": body.recibido_por or "",
        "timestamp": datetime.now().isoformat()
    }
    tienda["productos"].append(nuevo)
    save_consig(data)
    return {"status": "ok", "producto": nuevo}


@router.put("/api/consignacion/tiendas/{store_id}/productos/{prod_id}")
async def actualizar_producto(store_id: str, prod_id: str, body: ProductoUpdate):
    data = load_consig()
    tienda = next((t for t in data["tiendas"] if t["id"] == store_id), None)
    if not tienda:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")

    # Tienda principal: redirigir a stock_actual.json
    if tienda.get("tipo") == "principal":
        stock_data = load_stock()
        if prod_id not in stock_data["productos"]:
            raise HTTPException(status_code=404, detail="Producto no encontrado en stock principal")
        prod_s = stock_data["productos"][prod_id]
        if body.stock is not None:
            if body.stock < 0:
                raise HTTPException(status_code=400, detail="Stock no puede ser negativo")
            prod_s["stock"] = body.stock
            prod_s["disponible"] = body.stock > 0
        prod_s["timestamp"] = datetime.now().isoformat()
        save_stock(stock_data)
        return {"status": "ok", "producto": {
            "id": prod_id, "nombre": prod_s["nombre"],
            "stock": prod_s["stock"], "notas": "",
        }}

    prod = next((p for p in tienda["productos"] if p["id"] == prod_id), None)
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    if body.nombre is not None:
        prod["nombre"] = body.nombre.strip()
    if body.stock is not None:
        if body.stock < 0:
            raise HTTPException(status_code=400, detail="Stock no puede ser negativo")
        prod["stock"] = body.stock
    if body.notas is not None:
        prod["notas"] = body.notas
    prod["timestamp"] = datetime.now().isoformat()
    save_consig(data)
    return {"status": "ok", "producto": prod}


@router.delete("/api/consignacion/tiendas/{store_id}/productos/{prod_id}")
async def eliminar_producto(store_id: str, prod_id: str):
    data = load_consig()
    tienda = next((t for t in data["tiendas"] if t["id"] == store_id), None)
    if not tienda:
        raise HTTPException(status_code=404, detail="Tienda no encontrada")
    if tienda.get("tipo") == "principal":
        raise HTTPException(status_code=403, detail="Elimina el producto desde la pestana Stock Principal")
    original = len(tienda["productos"])
    tienda["productos"] = [p for p in tienda["productos"] if p["id"] != prod_id]
    if len(tienda["productos"]) == original:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    save_consig(data)
    return {"status": "ok"}


# ── Movimientos helpers ──

def load_movimientos():
    if not os.path.exists(MOVIMIENTOS_FILE):
        return {"movimientos": [], "ultima_actualizacion": datetime.now().isoformat()}
    try:
        with open(MOVIMIENTOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error leyendo movimientos: {e}")
        return {"movimientos": [], "ultima_actualizacion": datetime.now().isoformat()}


def save_movimientos(data):
    try:
        data["ultima_actualizacion"] = datetime.now().isoformat()
        with open(MOVIMIENTOS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando movimientos: {e}")
        raise


@router.get("/api/movimientos")
async def get_movimientos(tipo: str = "", desde: str = "", hasta: str = "", producto: str = ""):
    data = load_movimientos()
    movs = data.get("movimientos", [])
    if tipo:
        movs = [m for m in movs if m.get("tipo") == tipo]
    if desde:
        movs = [m for m in movs if m.get("fecha", "") >= desde]
    if hasta:
        movs = [m for m in movs if m.get("fecha", "") <= hasta + "T23:59:59"]
    if producto:
        q = producto.lower()
        movs = [m for m in movs if q in m.get("producto", "").lower()]
    return {"movimientos": movs, "ultima_actualizacion": data.get("ultima_actualizacion", "")}


@router.post("/api/movimientos")
async def crear_movimiento(body: MovimientoCreate):
    if body.tipo not in ("venta", "reposicion", "retiro", "ajuste"):
        raise HTTPException(status_code=400, detail="Tipo invalido")
    if body.tipo == "ajuste":
        if body.cantidad == 0:
            raise HTTPException(status_code=400, detail="Cantidad no puede ser 0")
    else:
        if body.cantidad < 1:
            raise HTTPException(status_code=400, detail="Cantidad debe ser >= 1")

    data = load_movimientos()
    nuevo = {
        "id": uuid.uuid4().hex[:8],
        "tipo": body.tipo,
        "producto": body.producto.strip(),
        "cantidad": body.cantidad,
        "ubicacion": body.ubicacion or "Solumedic",
        "precio_venta": body.precio_venta,
        "notas": body.notas or "",
        "fecha": body.fecha if body.fecha else datetime.now().isoformat(),
        "recibido_por": body.recibido_por or "",
    }
    data["movimientos"].insert(0, nuevo)
    save_movimientos(data)

    # ── Aplicar efecto en stock automáticamente ──
    ubicacion = (body.ubicacion or "Solumedic").strip()
    nombre_prod = body.producto.strip().lower()
    cantidad = body.cantidad
    tipo = body.tipo

    consig = load_consig()
    tienda = next((t for t in consig["tiendas"] if t["nombre"].strip().lower() == ubicacion.lower()), None)

    if tienda and tienda.get("tipo") == "principal":
        # Tienda principal → misma lógica que stock_actual directamente
        stock_d = load_stock()
        prod_p = next((p for p in stock_d["productos"].values() if p["nombre"].strip().lower() == nombre_prod), None)
        if prod_p:
            if tipo == "reposicion":
                prod_p["stock"] = prod_p["stock"] + cantidad
            elif tipo in ("venta", "retiro"):
                prod_p["stock"] = max(0, prod_p["stock"] - cantidad)
            elif tipo == "ajuste":
                prod_p["stock"] = max(0, prod_p["stock"] + cantidad)
            prod_p["disponible"] = prod_p["stock"] > 0
            prod_p["timestamp"] = datetime.now().isoformat()
            save_stock(stock_d)
    elif tienda:
        # Ubicación es una tienda de consignación
        prod_c = next((p for p in tienda["productos"] if p["nombre"].strip().lower() == nombre_prod), None)

        if tipo == "reposicion":
            if prod_c:
                prod_c["stock"] = max(0, prod_c["stock"] + cantidad)
                prod_c["timestamp"] = datetime.now().isoformat()
            else:
                tienda["productos"].append({
                    "id": uuid.uuid4().hex[:8],
                    "nombre": body.producto.strip(),
                    "stock": cantidad,
                    "notas": "",
                    "fecha_entrega": datetime.now().isoformat(),
                    "recibido_por": body.recibido_por or "",
                    "timestamp": datetime.now().isoformat(),
                })
            save_consig(consig)
            # Descuenta del stock principal
            stock_d = load_stock()
            prod_p = next((p for p in stock_d["productos"].values() if p["nombre"].strip().lower() == nombre_prod), None)
            if prod_p:
                prod_p["stock"] = max(0, prod_p["stock"] - cantidad)
                prod_p["disponible"] = prod_p["stock"] > 0
                prod_p["timestamp"] = datetime.now().isoformat()
                save_stock(stock_d)

        elif tipo == "venta":
            if prod_c:
                prod_c["stock"] = max(0, prod_c["stock"] - cantidad)
                prod_c["timestamp"] = datetime.now().isoformat()
                save_consig(consig)

        elif tipo == "retiro":
            if prod_c:
                prod_c["stock"] = max(0, prod_c["stock"] - cantidad)
                prod_c["timestamp"] = datetime.now().isoformat()
                save_consig(consig)
            # Suma en stock principal
            stock_d = load_stock()
            prod_p = next((p for p in stock_d["productos"].values() if p["nombre"].strip().lower() == nombre_prod), None)
            if prod_p:
                prod_p["stock"] = prod_p["stock"] + cantidad
                prod_p["disponible"] = True
                prod_p["timestamp"] = datetime.now().isoformat()
                save_stock(stock_d)

        elif tipo == "ajuste":
            if prod_c:
                prod_c["stock"] = max(0, prod_c["stock"] + cantidad)
                prod_c["timestamp"] = datetime.now().isoformat()
                save_consig(consig)

    else:
        # Ubicación es stock principal
        stock_d = load_stock()
        prod_p = next((p for p in stock_d["productos"].values() if p["nombre"].strip().lower() == nombre_prod), None)
        if prod_p:
            if tipo == "reposicion":
                prod_p["stock"] = prod_p["stock"] + cantidad
            elif tipo == "venta":
                prod_p["stock"] = max(0, prod_p["stock"] - cantidad)
            elif tipo == "ajuste":
                prod_p["stock"] = max(0, prod_p["stock"] + cantidad)
            prod_p["disponible"] = prod_p["stock"] > 0
            prod_p["timestamp"] = datetime.now().isoformat()
            save_stock(stock_d)

    return {"status": "ok", "movimiento": nuevo}


@router.delete("/api/movimientos/{mov_id}")
async def eliminar_movimiento(mov_id: str):
    data = load_movimientos()
    original = len(data["movimientos"])
    data["movimientos"] = [m for m in data["movimientos"] if m.get("id") != mov_id]
    if len(data["movimientos"]) == original:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    save_movimientos(data)
    return {"status": "ok"}


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
  <link href="https://fonts.googleapis.com/css2?family=Raleway:wght@300;400;500;600;700;800&family=Montserrat:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

    :root {
      --purple:    #083262;
      --purple-lt: #3a5f96;
      --purple-bg: #e8eef5;
      --green:     #00b199;
      --green-bg:  #d4f5f0;
      --green-txt: #005a50;
      --amber:     #F59E0B;
      --amber-bg:  #FEF3C7;
      --amber-txt: #92400E;
      --red:       #EF4444;
      --red-bg:    #FEE2E2;
      --red-txt:   #991B1B;
      --bg:        #f5f7fa;
      --text:      #000000;
      --text-muted:#5a6a7a;
      --border:    #cdd6df;
      --white:     #FFFFFF;
      --radius-sm: 6px;
      --radius-md: 10px;
      --radius-lg: 16px;
      --shadow-sm: 0 1px 3px rgba(8,50,98,.08);
      --shadow-md: 0 4px 16px rgba(8,50,98,.12);
      --shadow-lg: 0 8px 32px rgba(8,50,98,.18);
    }

    html { font-size: 16px; }

    body {
      font-family: 'Raleway', sans-serif;
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
      font-family: 'Montserrat', sans-serif;
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
      font-family: 'Raleway', sans-serif;
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
      font-family: 'Montserrat', sans-serif;
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
      font-family: 'Raleway', sans-serif;
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
      font-family: 'Raleway', sans-serif;
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
      font-family: 'Montserrat', sans-serif;
      font-size: .85rem;
      font-weight: 600;
      color: var(--purple);
      text-transform: uppercase;
      letter-spacing: .08em;
      flex: 1;
    }
    .category-count {
      font-family: 'Montserrat', sans-serif;
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

    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    thead th {
      background: var(--purple-bg);
      font-size: .72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--text-muted);
      padding: 10px 16px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    thead th.th-stock  { text-align: center; width: 110px; }
    thead th.th-estado { text-align: center; width: 140px; }
    thead th.th-actions{ text-align: center; width: 100px; }

    tbody tr {
      border-bottom: 1px solid var(--border);
      transition: background .12s;
    }
    tbody tr:last-child { border-bottom: none; }
    tbody tr:hover { background: var(--purple-bg); }
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
      font-family: 'Montserrat', sans-serif;
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
      box-shadow: 0 0 0 3px rgba(8,50,98,.15);
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

    /* ── Section tabs (Stock Principal / Consignacion) ── */
    .section-tabs {
      display: flex;
      gap: 4px;
      margin-bottom: 24px;
      border-bottom: 2px solid var(--border);
      padding-bottom: 0;
    }
    .section-tab {
      font-family: 'Raleway', sans-serif;
      font-size: .9rem;
      font-weight: 600;
      padding: 10px 20px;
      border: none;
      border-bottom: 3px solid transparent;
      background: none;
      color: var(--text-muted);
      cursor: pointer;
      transition: color .15s, border-color .15s;
      margin-bottom: -2px;
      border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    }
    .section-tab:hover { color: var(--purple); }
    .section-tab.active { color: var(--purple); border-bottom-color: var(--purple); }

    /* ── Consignacion KPI grid (2 cards) ── */
    .kpi-grid-2 {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
      margin-bottom: 28px;
    }
    @media (max-width: 400px) { .kpi-grid-2 { grid-template-columns: 1fr; } }

    /* ── Store cards ── */
    .store-card {
      background: var(--white);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-sm);
      margin-bottom: 16px;
      overflow: hidden;
    }
    .store-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      background: #FAFAFF;
    }
    .store-info { flex: 1; min-width: 0; }
    .store-name {
      font-family: 'Montserrat', sans-serif;
      font-size: .95rem;
      font-weight: 600;
      color: var(--text);
    }
    .store-addr {
      font-size: .8rem;
      color: var(--text-muted);
      margin-top: 2px;
    }
    .badge-tipo {
      font-size: .7rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
      border-radius: 99px;
      padding: 3px 10px;
      flex-shrink: 0;
    }
    .badge-tipo.principal  { background: var(--purple-bg); color: var(--purple); }
    .badge-tipo.consignacion { background: var(--amber-bg); color: var(--amber-txt); }
    .store-actions { display: flex; gap: 6px; flex-shrink: 0; }

    .btn-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border: 1.5px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--white);
      color: var(--text-muted);
      cursor: pointer;
      transition: all .15s;
    }
    .btn-icon:hover { border-color: var(--purple); color: var(--purple); background: var(--purple-bg); }
    .btn-icon.danger:hover { border-color: var(--red); color: var(--red); background: var(--red-bg); }
    .btn-icon:active { transform: scale(.92); }

    .store-body { padding: 0; }

    /* consignacion product table */
    .consig-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    .consig-table thead th:nth-child(2) { width: 110px; }
    .consig-table thead th:nth-child(4) { width: 100px; }
    .consig-table thead th {
      background: #F5F3FF;
      font-size: .72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--text-muted);
      padding: 8px 16px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    .consig-table thead th.th-c { text-align: center; }
    .consig-table tbody tr {
      border-bottom: 1px solid var(--border);
      transition: background .12s;
    }
    .consig-table tbody tr:last-child { border-bottom: none; }
    .consig-table tbody tr:hover { background: #FAFAFF; }
    .consig-table tbody tr.flash-ok { animation: rowFlash .6s ease-out; }
    .consig-table td { padding: 10px 16px; vertical-align: middle; }
    .consig-table td.td-c { text-align: center; }

    .inline-edit {
      font-family: 'Raleway', sans-serif;
      font-size: .88rem;
      width: 100%;
      padding: 5px 8px;
      border: 1.5px solid transparent;
      border-radius: var(--radius-sm);
      background: transparent;
      color: var(--text);
      transition: border-color .15s, background .15s;
    }
    .inline-edit:hover { border-color: var(--border); background: var(--white); }
    .inline-edit:focus { outline: none; border-color: var(--purple); background: var(--white); box-shadow: 0 0 0 3px rgba(139,92,246,.12); }

    .consig-stock-wrap { display: flex; align-items: center; justify-content: center; gap: 4px; }
    .consig-stock-input {
      font-family: 'Montserrat', sans-serif;
      font-size: .88rem;
      font-weight: 500;
      width: 62px;
      padding: 5px 4px;
      text-align: center;
      border: 1.5px solid var(--border);
      border-radius: var(--radius-sm);
      color: var(--text);
      background: var(--white);
      transition: border-color .15s, box-shadow .15s;
      min-height: 36px;
    }
    .consig-stock-input:focus { outline: none; border-color: var(--purple); box-shadow: 0 0 0 3px rgba(139,92,246,.15); }
    .consig-stock-input::-webkit-inner-spin-button,
    .consig-stock-input::-webkit-outer-spin-button { -webkit-appearance: none; }
    .consig-stock-input[type=number] { -moz-appearance: textfield; }

    .btn-adj-sm {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 36px;
      border: 1.5px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--white);
      color: var(--text-muted);
      cursor: pointer;
      transition: all .15s;
      font-size: 1rem;
    }
    .btn-adj-sm:hover { border-color: var(--purple); color: var(--purple); background: var(--purple-bg); }
    .btn-adj-sm.minus:hover { border-color: var(--red); color: var(--red); background: var(--red-bg); }
    .btn-adj-sm:active { transform: scale(.92); }

    /* inline add-product form */
    .inline-form {
      display: none;
      padding: 14px 16px;
      background: var(--purple-bg);
      border-top: 1px solid var(--border);
      gap: 8px;
      flex-wrap: wrap;
      align-items: flex-end;
    }
    .inline-form.visible { display: flex; }
    .inline-form label { font-size: .75rem; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 4px; }
    .inline-form input[type=text],
    .inline-form input[type=number] {
      font-family: 'Raleway', sans-serif;
      font-size: .85rem;
      padding: 7px 10px;
      border: 1.5px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--white);
      color: var(--text);
      min-height: 38px;
    }
    .inline-form input[type=text]:focus,
    .inline-form input[type=number]:focus {
      outline: none;
      border-color: var(--purple);
      box-shadow: 0 0 0 3px rgba(139,92,246,.12);
    }
    .inline-form .f-nombre { flex: 2; min-width: 140px; }
    .inline-form .f-stock  { width: 80px; }
    .inline-form .f-notas  { flex: 1; min-width: 100px; }
    .inline-form .f-btns   { display: flex; gap: 6px; align-self: flex-end; }

    .btn-sm {
      font-family: 'Raleway', sans-serif;
      font-size: .8rem;
      font-weight: 600;
      padding: 7px 14px;
      border-radius: var(--radius-sm);
      border: none;
      cursor: pointer;
      min-height: 38px;
      transition: background .15s, transform .1s;
    }
    .btn-sm.primary { background: var(--purple); color: var(--white); }
    .btn-sm.primary:hover { background: #7C3AED; }
    .btn-sm.secondary { background: var(--white); color: var(--text-muted); border: 1.5px solid var(--border); }
    .btn-sm.secondary:hover { border-color: var(--purple); color: var(--purple); }
    .btn-sm:active { transform: scale(.96); }

    /* add-product button row */
    .store-footer {
      padding: 10px 16px;
      border-top: 1px solid var(--border);
      background: #FAFAFF;
    }
    .btn-add-prod {
      font-family: 'Raleway', sans-serif;
      font-size: .8rem;
      font-weight: 600;
      color: var(--purple);
      background: none;
      border: 1.5px dashed var(--purple-lt);
      border-radius: var(--radius-sm);
      padding: 6px 14px;
      cursor: pointer;
      transition: background .15s, border-color .15s;
      min-height: 34px;
    }
    .btn-add-prod:hover { background: var(--purple-bg); border-color: var(--purple); }

    /* nueva tienda inline form (top-level) */
    .new-store-form {
      display: none;
      background: var(--white);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-sm);
      padding: 20px;
      margin-bottom: 20px;
      gap: 12px;
      flex-wrap: wrap;
      align-items: flex-end;
    }
    .new-store-form.visible { display: flex; }
    .new-store-form label { font-size: .75rem; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 4px; }
    .new-store-form input[type=text],
    .new-store-form select {
      font-family: 'Raleway', sans-serif;
      font-size: .88rem;
      padding: 8px 12px;
      border: 1.5px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--white);
      color: var(--text);
      min-height: 42px;
      width: 100%;
    }
    .new-store-form input[type=text]:focus,
    .new-store-form select:focus {
      outline: none;
      border-color: var(--purple);
      box-shadow: 0 0 0 3px rgba(139,92,246,.12);
    }
    .new-store-form .f-nombre { flex: 2; min-width: 160px; }
    .new-store-form .f-tipo   { width: 150px; }
    .new-store-form .f-dir    { flex: 2; min-width: 160px; }
    .new-store-form .f-btns   { display: flex; gap: 8px; align-self: flex-end; }

    /* edit store inline form */
    .edit-store-form {
      display: none;
      background: var(--amber-bg);
      border-top: 1px solid var(--border);
      padding: 14px 20px;
      gap: 10px;
      flex-wrap: wrap;
      align-items: flex-end;
    }
    .edit-store-form.visible { display: flex; }
    .edit-store-form label { font-size: .75rem; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 4px; }
    .edit-store-form input[type=text] {
      font-family: 'Raleway', sans-serif;
      font-size: .88rem;
      padding: 7px 10px;
      border: 1.5px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--white);
      color: var(--text);
      min-height: 38px;
      width: 100%;
    }
    .edit-store-form input[type=text]:focus {
      outline: none;
      border-color: var(--purple);
      box-shadow: 0 0 0 3px rgba(139,92,246,.12);
    }
    .edit-store-form .f-nombre { flex: 2; min-width: 140px; }
    .edit-store-form .f-dir    { flex: 2; min-width: 140px; }
    .edit-store-form .f-btns   { display: flex; gap: 6px; align-self: flex-end; }

    .consig-empty {
      padding: 28px 16px;
      text-align: center;
      color: var(--text-muted);
      font-size: .85rem;
    }

    /* Global "Nueva tienda" button */
    .btn-new-store {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-family: 'Raleway', sans-serif;
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
    .btn-new-store:hover { background: #7C3AED; }
    .btn-new-store:active { transform: scale(.97); }

    .consig-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 16px;
    }
    .consig-toolbar-title {
      font-size: .85rem;
      color: var(--text-muted);
      font-weight: 500;
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

  <!-- Section tabs -->
  <div class="section-tabs">
    <button class="section-tab active" id="stab-stock" onclick="switchSection('stock')">Stock Principal</button>
    <button class="section-tab" id="stab-consig" onclick="switchSection('consig')">Consignacion</button>
    <button class="section-tab" id="stab-movimientos" onclick="switchSection('movimientos')">Movimientos</button>
  </div>

  <!-- ══ SECTION: Stock Principal ══ -->
  <div id="section-stock">
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

  <!-- ══ SECTION: Movimientos ══ -->
  <div id="section-movimientos" style="display:none">

    <!-- KPIs movimientos -->
    <div class="kpi-grid" id="mov-kpi-grid">
      <div class="kpi-card total">
        <div class="kpi-label">Ventas del mes</div>
        <div class="kpi-value" id="mkpi-ventas">—</div>
      </div>
      <div class="kpi-card disp">
        <div class="kpi-label">Unidades vendidas</div>
        <div class="kpi-value" id="mkpi-unidades">—</div>
      </div>
      <div class="kpi-card bajo">
        <div class="kpi-label">Reposiciones del mes</div>
        <div class="kpi-value" id="mkpi-repos">—</div>
      </div>
      <div class="kpi-card agot" style="color:var(--green)">
        <div class="kpi-label">Valor vendido</div>
        <div class="kpi-value" id="mkpi-valor" style="font-size:1.3rem">—</div>
      </div>
    </div>

    <!-- Toolbar movimientos -->
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:16px">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <select id="mfil-tipo" onchange="filtrarMovimientos()" style="font-family:Raleway,sans-serif;font-size:.85rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:38px">
          <option value="">Todos los tipos</option>
          <option value="venta">Venta</option>
          <option value="reposicion">Reposicion</option>
          <option value="retiro">Retiro</option>
          <option value="ajuste">Ajuste</option>
        </select>
        <select id="mfil-periodo" onchange="filtrarMovimientos()" style="font-family:Raleway,sans-serif;font-size:.85rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:38px">
          <option value="mes">Este mes</option>
          <option value="semana">Esta semana</option>
          <option value="hoy">Hoy</option>
          <option value="todo">Todo</option>
        </select>
        <input type="text" id="mfil-buscar" placeholder="Buscar producto..." oninput="filtrarMovimientos()" style="font-family:Raleway,sans-serif;font-size:.85rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:38px;min-width:180px">
      </div>
      <button class="btn-new-store" onclick="toggleMovForm()" id="btn-nuevo-mov">
        <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" d="M12 4v16m8-8H4"/>
        </svg>
        Registrar movimiento
      </button>
    </div>

    <!-- Inline form nuevo movimiento -->
    <div class="new-store-form" id="mov-form" style="flex-direction:column;gap:14px">
      <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end">
        <div style="min-width:140px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Tipo *</label>
          <select id="mf-tipo" onchange="onMovTipoChange()" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 12px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
            <option value="venta">Venta</option>
            <option value="reposicion">Reposicion</option>
            <option value="retiro">Retiro</option>
            <option value="ajuste">Ajuste</option>
          </select>
        </div>
        <div style="flex:2;min-width:160px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Producto *</label>
          <select id="mf-producto" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 12px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
            <option value="">— Seleccionar —</option>
          </select>
        </div>
        <div style="width:90px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Cantidad *</label>
          <input type="number" id="mf-cantidad" value="1" min="1" onkeydown="if(event.key==='Enter'){event.preventDefault();registrarMovimiento()}" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
        </div>
        <div style="min-width:150px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Ubicacion</label>
          <select id="mf-ubicacion" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 12px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
            <option value="Solumedic">Solumedic</option>
          </select>
        </div>
        <div id="mf-precio-wrap" style="min-width:150px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Precio venta</label>
          <input type="number" id="mf-precio" value="0" min="0" placeholder="Gs." onkeydown="if(event.key==='Enter'){event.preventDefault();registrarMovimiento()}" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
        </div>
        <div style="min-width:120px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Fecha</label>
          <input type="date" id="mf-fecha" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
        </div>
        <div id="mf-signo-wrap" style="display:none;min-width:100px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Direccion</label>
          <select id="mf-signo" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
            <option value="1">+ Sumar</option>
            <option value="-1">− Restar</option>
          </select>
        </div>
        <div style="min-width:140px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Recibido por</label>
          <input type="text" id="mf-recibido" placeholder="Nombre..." onkeydown="if(event.key==='Enter'){event.preventDefault();registrarMovimiento()}" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
        </div>
        <div style="flex:2;min-width:160px">
          <label style="font-size:.75rem;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px">Notas</label>
          <input type="text" id="mf-notas" placeholder="Opcional" onkeydown="if(event.key==='Enter'){event.preventDefault();registrarMovimiento()}" style="font-family:Raleway,sans-serif;font-size:.88rem;padding:8px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:42px;width:100%">
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn-sm primary" onclick="registrarMovimiento()">Registrar</button>
        <button class="btn-sm secondary" onclick="toggleMovForm()">Cancelar</button>
      </div>
    </div>

    <!-- Tabla historial -->
    <div style="background:var(--white);border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden;box-shadow:var(--shadow-sm)">
      <table style="width:100%;border-collapse:collapse" id="mov-table">
        <thead>
          <tr>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:left;border-bottom:1px solid var(--border)">Fecha</th>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:left;border-bottom:1px solid var(--border)">Tipo</th>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:left;border-bottom:1px solid var(--border)">Producto</th>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:center;border-bottom:1px solid var(--border)">Cant.</th>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:left;border-bottom:1px solid var(--border)">Ubicacion</th>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:left;border-bottom:1px solid var(--border)">Recibido por</th>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:right;border-bottom:1px solid var(--border)">Precio</th>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:left;border-bottom:1px solid var(--border)">Notas</th>
            <th style="background:#F5F3FF;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted);padding:10px 14px;text-align:center;border-bottom:1px solid var(--border)">Acciones</th>
          </tr>
        </thead>
        <tbody id="mov-tbody">
          <tr><td colspan="9" class="state-msg">Cargando...</td></tr>
        </tbody>
      </table>
    </div>

  </div>

  <!-- ══ SECTION: Consignacion ══ -->
  <div id="section-consig" style="display:none">

    <!-- KPIs -->
    <div class="kpi-grid-2">
      <div class="kpi-card total">
        <div class="kpi-label">Tiendas / Locales</div>
        <div class="kpi-value" id="ckpi-tiendas">—</div>
      </div>
      <div class="kpi-card disp">
        <div class="kpi-label">Unidades en consignacion</div>
        <div class="kpi-value" id="ckpi-unidades">—</div>
      </div>
    </div>

    <!-- Toolbar consig -->
    <div class="consig-toolbar">
      <span class="consig-toolbar-title" id="consig-subtitle">Cargando...</span>
      <button class="btn-new-store" onclick="toggleNewStoreForm()">
        <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" d="M12 4v16m8-8H4"/>
        </svg>
        Nueva tienda
      </button>
    </div>

    <!-- Inline new-store form -->
    <div class="new-store-form" id="new-store-form">
      <div class="f-nombre">
        <label>Nombre *</label>
        <input type="text" id="ns-nombre" placeholder="Nombre del local" onkeydown="if(event.key==='Enter'){event.preventDefault();crearTienda()}">
      </div>
      <div class="f-tipo">
        <label>Tipo</label>
        <select id="ns-tipo">
          <option value="consignacion">Consignacion</option>
          <option value="principal">Principal</option>
        </select>
      </div>
      <div class="f-dir">
        <label>Direccion</label>
        <input type="text" id="ns-dir" placeholder="Direccion (opcional)" onkeydown="if(event.key==='Enter'){event.preventDefault();crearTienda()}">
      </div>
      <div class="f-btns">
        <button class="btn-sm primary" onclick="crearTienda()">Guardar</button>
        <button class="btn-sm secondary" onclick="toggleNewStoreForm()">Cancelar</button>
      </div>
    </div>

    <!-- Store list -->
    <div id="consig-stores">
      <div class="state-msg">
        <svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="M20 7H4a2 2 0 00-2 2v10a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zM16 3H8l-2 4h12l-2-4z"/>
        </svg>
        Cargando consignacion...
      </div>
    </div>

  </div>

</div>

<!-- Toast container -->
<div id="toast-container" aria-live="polite" aria-atomic="false"></div>

<script>
  /* ─── State ─── */
  let stockData = {};
  let tabActivo = 'todos';
  let storeCollapsed = {};
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
                  <th class="th-estado">Estado</th>
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

  /* ─── Section switching ─── */
  let currentSection = 'stock';

  function switchSection(sec) {
    currentSection = sec;
    document.getElementById('section-stock').style.display = sec === 'stock' ? '' : 'none';
    document.getElementById('section-consig').style.display = sec === 'consig' ? '' : 'none';
    document.getElementById('section-movimientos').style.display = sec === 'movimientos' ? '' : 'none';
    document.getElementById('stab-stock').classList.toggle('active', sec === 'stock');
    document.getElementById('stab-consig').classList.toggle('active', sec === 'consig');
    document.getElementById('stab-movimientos').classList.toggle('active', sec === 'movimientos');
    if (sec === 'consig' && !consigData) cargarConsig();
    if (sec === 'movimientos' && !movimientosData) cargarMovimientos();
  }

  /* ─── Movimientos state ─── */
  let movimientosData = null;
  let movimientosFiltrados = [];

  /* ─── Movimientos helpers ─── */
  function formatFechaMov(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    if (isNaN(d)) return isoStr;
    return d.toLocaleString('es-PY', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
  }

  function formatGs(num) {
    if (!num) return '—';
    return 'Gs. ' + Math.round(num).toLocaleString('es-PY');
  }

  function mesActual() {
    const now = new Date();
    return now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0');
  }

  function actualizarMovKPIs(movs) {
    const mes = mesActual();
    const ventasMes = movs.filter(m => m.tipo === 'venta' && (m.fecha || '').startsWith(mes));
    const reposMes  = movs.filter(m => m.tipo === 'reposicion' && (m.fecha || '').startsWith(mes));
    const unidades  = ventasMes.reduce((s,m) => s + (m.cantidad||0), 0);
    const valor     = ventasMes.reduce((s,m) => s + ((m.precio_venta||0) * (m.cantidad||0)), 0);
    document.getElementById('mkpi-ventas').textContent  = ventasMes.length;
    document.getElementById('mkpi-unidades').textContent = unidades;
    document.getElementById('mkpi-repos').textContent   = reposMes.length;
    document.getElementById('mkpi-valor').textContent   = formatGs(valor);
  }

  function badgeMov(tipo) {
    const map = {
      venta:      ['var(--green-bg)',  'var(--green-txt)',  'Venta'],
      reposicion: ['var(--purple-bg)', 'var(--purple)',     'Reposicion'],
      retiro:     ['var(--amber-bg)',  'var(--amber-txt)',  'Retiro'],
      ajuste:     ['#ebebeb',          '#555',              'Ajuste'],
    };
    const [bg, color, label] = map[tipo] || ['#ebebeb','#555', tipo];
    return `<span style="display:inline-flex;align-items:center;font-size:.72rem;font-weight:700;border-radius:99px;padding:3px 10px;background:${bg};color:${color}">${label}</span>`;
  }

  function rowBgMov(tipo) {
    const map = { venta:'var(--green-bg)', reposicion:'#e8eef5', retiro:'var(--amber-bg)', ajuste:'#f0f0f0' };
    return map[tipo] || 'transparent';
  }

  /* ─── Movimientos load ─── */
  async function cargarMovimientos() {
    try {
      const res = await fetch('/api/movimientos');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      movimientosData = await res.json();
      filtrarMovimientos();
    } catch(err) {
      document.getElementById('mov-tbody').innerHTML =
        '<tr><td colspan="9" class="state-msg">Error al cargar movimientos</td></tr>';
      mostrarToast('Error al cargar movimientos', 'err');
    }
  }

  /* ─── Render movimientos ─── */
  function renderMovimientos(movs) {
    actualizarMovKPIs(movimientosData ? (movimientosData.movimientos || []) : []);
    const tbody = document.getElementById('mov-tbody');
    if (!movs || movs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="state-msg">Sin movimientos registrados aun.</td></tr>';
      return;
    }
    tbody.innerHTML = movs.map(m => `
      <tr style="border-bottom:1px solid var(--border);background:${rowBgMov(m.tipo)}">
        <td style="padding:10px 14px;font-size:.82rem;white-space:nowrap">${formatFechaMov(m.fecha)}</td>
        <td style="padding:10px 14px">${badgeMov(m.tipo)}</td>
        <td style="padding:10px 14px;font-size:.88rem;font-weight:500">${escapeHtml(m.producto)}</td>
        <td style="padding:10px 14px;text-align:center;font-family:Montserrat,sans-serif;font-weight:600">${m.cantidad > 0 ? '+'+m.cantidad : m.cantidad}</td>
        <td style="padding:10px 14px;font-size:.85rem;color:var(--text-muted)">${escapeHtml(m.ubicacion||'')}</td>
        <td style="padding:10px 14px;font-size:.82rem;color:var(--text-muted)">${escapeHtml(m.recibido_por||'—')}</td>
        <td style="padding:10px 14px;text-align:right;font-size:.82rem;font-family:Montserrat,sans-serif">${m.precio_venta ? formatGs(m.precio_venta) : '—'}</td>
        <td style="padding:10px 14px;font-size:.82rem;color:var(--text-muted)">${escapeHtml(m.notas||'')}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn-icon danger" onclick="eliminarMovimiento('${m.id}')" title="Eliminar">
            <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
            </svg>
          </button>
        </td>
      </tr>`).join('');
  }

  /* ─── Filtrar movimientos (JS, sin recarga) ─── */
  function filtrarMovimientos() {
    if (!movimientosData) return;
    const tipo    = document.getElementById('mfil-tipo').value;
    const periodo = document.getElementById('mfil-periodo').value;
    const buscar  = document.getElementById('mfil-buscar').value.toLowerCase().trim();
    const now     = new Date();
    const hoy     = now.toISOString().slice(0,10);
    const lunes   = (() => { const d = new Date(now); d.setDate(d.getDate() - ((d.getDay()+6)%7)); return d.toISOString().slice(0,10); })();
    const primerMes = hoy.slice(0,7) + '-01';

    let movs = (movimientosData.movimientos || []).filter(m => {
      if (tipo && m.tipo !== tipo) return false;
      if (buscar && !(m.producto||'').toLowerCase().includes(buscar)) return false;
      const fStr = (m.fecha || '').slice(0,10);
      if (periodo === 'hoy'    && fStr !== hoy)      return false;
      if (periodo === 'semana' && fStr < lunes)       return false;
      if (periodo === 'mes'    && fStr < primerMes)   return false;
      return true;
    });
    movimientosFiltrados = movs;
    renderMovimientos(movs);
  }

  /* ─── Registrar movimiento ─── */
  async function registrarMovimiento() {
    const tipo     = document.getElementById('mf-tipo').value;
    const prodSel  = document.getElementById('mf-producto').value.trim();
    const cantRaw  = parseInt(document.getElementById('mf-cantidad').value, 10);
    const ubicacion= document.getElementById('mf-ubicacion').value;
    const precio   = parseFloat(document.getElementById('mf-precio').value) || 0;
    const fechaVal = document.getElementById('mf-fecha').value;
    const notas    = document.getElementById('mf-notas').value.trim();
    const recibido_por = document.getElementById('mf-recibido').value.trim();
    if (!prodSel) { mostrarToast('Selecciona un producto', 'err'); return; }
    if (!cantRaw || cantRaw < 1) { mostrarToast('Cantidad invalida', 'err'); return; }
    let cantidad = cantRaw;
    if (tipo === 'ajuste') {
      const signo = parseInt(document.getElementById('mf-signo').value, 10);
      cantidad = cantRaw * signo;
    }
    const fecha = fechaVal ? fechaVal + 'T00:00:00' : '';
    try {
      const res = await fetch('/api/movimientos', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ tipo, producto: prodSel, cantidad, ubicacion, precio_venta: precio, notas, fecha, recibido_por })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if (!movimientosData) movimientosData = { movimientos: [] };
      movimientosData.movimientos.unshift(data.movimiento);
      // Recargar stock y consignacion para reflejar cambios automaticos
      await cargarStock();
      await cargarConsig();
      toggleMovForm();
      filtrarMovimientos();
      mostrarToast('Movimiento registrado — stock actualizado', 'ok');
    } catch(err) {
      mostrarToast('Error al registrar movimiento', 'err');
    }
  }

  /* ─── Eliminar movimiento ─── */
  async function eliminarMovimiento(movId) {
    if (!confirm('Eliminar este movimiento?')) return;
    try {
      const res = await fetch('/api/movimientos/' + movId, { method: 'DELETE' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      movimientosData.movimientos = movimientosData.movimientos.filter(m => m.id !== movId);
      filtrarMovimientos();
      mostrarToast('Movimiento eliminado', 'ok');
    } catch(err) {
      mostrarToast('Error al eliminar', 'err');
    }
  }

  /* ─── Toggle form movimiento ─── */
  function toggleMovForm() {
    const f = document.getElementById('mov-form');
    const visible = f.classList.toggle('visible');
    if (visible) {
      // populate producto select from stock
      const sel = document.getElementById('mf-producto');
      sel.innerHTML = '<option value="">— Seleccionar —</option>';
      if (stockData && stockData.productos) {
        Object.values(stockData.productos).forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.nombre; opt.textContent = p.nombre;
          sel.appendChild(opt);
        });
      }
      const optOtro = document.createElement('option');
      optOtro.value = '__custom__'; optOtro.textContent = 'Otro';
      sel.appendChild(optOtro);
      sel.onchange = function() {
        if (this.value === '__custom__') {
          const v = prompt('Nombre del producto:');
          if (v) { const o = document.createElement('option'); o.value=v; o.textContent=v; o.selected=true; sel.appendChild(o); }
          else this.value = '';
        }
      };
      // default fecha = hoy
      const today = new Date().toISOString().slice(0,10);
      document.getElementById('mf-fecha').value = today;
      if (!consigData) {
        cargarConsig().then(() => onMovTipoChange());
      } else {
        onMovTipoChange();
      }
    } else {
      document.getElementById('mf-cantidad').value = '1';
      document.getElementById('mf-precio').value = '0';
      document.getElementById('mf-notas').value = '';
      document.getElementById('mf-recibido').value = '';
    }
  }

  function onMovTipoChange() {
    const tipo = document.getElementById('mf-tipo').value;
    document.getElementById('mf-precio-wrap').style.display = tipo === 'venta' ? '' : 'none';
    document.getElementById('mf-signo-wrap').style.display = tipo === 'ajuste' ? '' : 'none';
    // Retiro y Reposicion: solo tiendas de consignacion (no Solumedic)
    // Venta y Ajuste: todas las ubicaciones
    const soloConsig = tipo === 'retiro' || tipo === 'reposicion';
    const uSel = document.getElementById('mf-ubicacion');
    uSel.innerHTML = soloConsig ? '<option value="">— Seleccionar tienda —</option>' : '<option value="Solumedic">Solumedic (Stock Principal)</option>';
    if (consigData && consigData.tiendas) {
      consigData.tiendas.filter(t => t.tipo !== 'principal').forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.nombre; opt.textContent = t.nombre;
        uSel.appendChild(opt);
      });
    }
  }

  /* ─── Consignacion state ─── */
  let consigData = null;

  /* ─── Consignacion load ─── */
  async function cargarConsig() {
    try {
      const res = await fetch('/api/consignacion');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      consigData = await res.json();
      renderConsig();
    } catch (err) {
      document.getElementById('consig-stores').innerHTML =
        '<div class="state-msg">Error al cargar consignacion</div>';
      mostrarToast('Error al cargar consignacion', 'err');
    }
  }

  /* ─── Consignacion KPIs ─── */
  function actualizarConsigKPIs() {
    if (!consigData) return;
    const tiendas = (consigData.tiendas || []).filter(t => t.tipo !== 'principal');
    const unidades = tiendas.reduce((sum, t) =>
      sum + (t.productos || []).reduce((s, p) => s + (p.stock || 0), 0), 0);
    document.getElementById('ckpi-tiendas').textContent = tiendas.length;
    document.getElementById('ckpi-unidades').textContent = unidades;
    const fecha = new Date(consigData.ultima_actualizacion).toLocaleString('es-PY', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
    document.getElementById('consig-subtitle').textContent = 'Actualizado ' + fecha;
  }

  /* ─── Render all stores ─── */
  function renderConsig() {
    actualizarConsigKPIs();
    const container = document.getElementById('consig-stores');
    const tiendas = (consigData && consigData.tiendas) || [];
    if (tiendas.length === 0) {
      container.innerHTML = '<div class="state-msg">Sin tiendas registradas. Agrega una con "Nueva tienda".</div>';
      return;
    }
    const tiendasConsig = tiendas.filter(t => t.tipo !== 'principal');
    if (tiendasConsig.length === 0) {
      container.innerHTML = '<div class="state-msg">Sin tiendas en consignacion. Agrega una con "Nueva tienda".</div>';
      return;
    }
    container.innerHTML = tiendasConsig.map(t => renderStoreCard(t)).join('');
  }

  function renderStoreCard(tienda) {
    const sid = tienda.id;
    const esPrincipal = tienda.tipo === 'principal';
    const tipoBadge = esPrincipal
      ? '<span class="badge-tipo principal">Principal</span>'
      : '<span class="badge-tipo consignacion">Consignacion</span>';
    const btnEliminar = !esPrincipal
      ? `<button class="btn-icon danger" onclick="eliminarTienda('${sid}')" title="Eliminar tienda">
           <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
             <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
           </svg>
         </button>` : '';
    const prods = tienda.productos || [];
    const filas = prods.length > 0
      ? prods.map(p => renderProdFila(sid, p, esPrincipal)).join('')
      : esPrincipal
        ? `<tr><td colspan="4" class="consig-empty">Sin productos en Stock Principal.</td></tr>`
        : `<tr><td colspan="4" class="consig-empty">Sin productos. Agrega uno abajo.</td></tr>`;

    const collapsed = !!storeCollapsed[sid];
    return `
      <div class="store-card" id="store-${sid}">
        <div class="store-header" style="cursor:pointer" onclick="toggleStoreCollapse('${sid}')">
          <div class="store-info">
            <div class="store-name">${escapeHtml(tienda.nombre)}</div>
            ${tienda.direccion ? `<div class="store-addr">${escapeHtml(tienda.direccion)}</div>` : ''}
          </div>
          ${tipoBadge}
          <span style="color:var(--text-muted);margin-left:4px;transition:transform .2s;display:inline-block;transform:${collapsed ? 'rotate(-90deg)' : 'rotate(0deg)'}" id="chevron-${sid}">
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
          </span>
          <div class="store-actions" onclick="event.stopPropagation()">
            <button class="btn-icon" onclick="toggleEditStore('${sid}')" title="Editar tienda">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
              </svg>
            </button>
            ${btnEliminar}
          </div>
        </div>
        <div class="edit-store-form" id="edit-form-${sid}">
          <div class="f-nombre">
            <label>Nombre</label>
            <input type="text" id="ef-nombre-${sid}" value="${escapeHtml(tienda.nombre)}" onkeydown="if(event.key==='Enter'){event.preventDefault();guardarEditTienda('${sid}')}">
          </div>
          <div class="f-dir">
            <label>Direccion</label>
            <input type="text" id="ef-dir-${sid}" value="${escapeHtml(tienda.direccion || '')}" onkeydown="if(event.key==='Enter'){event.preventDefault();guardarEditTienda('${sid}')}">
          </div>
          <div class="f-btns">
            <button class="btn-sm primary" onclick="guardarEditTienda('${sid}')">Guardar</button>
            <button class="btn-sm secondary" onclick="toggleEditStore('${sid}')">Cancelar</button>
          </div>
        </div>
        <div class="store-body" id="store-body-${sid}" style="${collapsed ? 'display:none' : ''}">
          <table class="consig-table">
            <thead>
              <tr>
                <th>Producto</th>
                <th class="th-c">Stock</th>
                <th>Notas</th>
                <th class="th-c">Acciones</th>
              </tr>
            </thead>
            <tbody id="tbody-${sid}">
              ${filas}
            </tbody>
          </table>
        </div>
        <div class="inline-form" id="addprod-form-${sid}">
          <div class="f-nombre">
            <label>Producto *</label>
            <select id="ap-select-${sid}" onchange="onProdSelectChange('${sid}')">
              <option value="">— Elegir del catálogo —</option>
              ${getCatalogOptions()}
              <option value="__custom__">✏️ Otro (escribir nombre)</option>
            </select>
            <input type="text" id="ap-nombre-${sid}" placeholder="Nombre personalizado" onkeydown="if(event.key==='Enter'){event.preventDefault();agregarProducto('${sid}')}" style="display:none;margin-top:6px">
          </div>
          <div class="f-stock">
            <label>Stock</label>
            <input type="number" id="ap-stock-${sid}" value="0" min="0" onkeydown="if(event.key==='Enter'){event.preventDefault();agregarProducto('${sid}')}">
          </div>
          <div class="f-notas">
            <label>Notas</label>
            <input type="text" id="ap-notas-${sid}" placeholder="Opcional" onkeydown="if(event.key==='Enter'){event.preventDefault();agregarProducto('${sid}')}">
          </div>
          <div class="f-nombre" style="min-width:130px">
            <label>Fecha entrega</label>
            <input type="date" id="ap-fecha-${sid}" style="font-family:Raleway,sans-serif;font-size:.85rem;padding:7px 9px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:38px;width:100%">
          </div>
          <div class="f-nombre" style="min-width:140px">
            <label>Recibido por</label>
            <input type="text" id="ap-recibido-${sid}" placeholder="Nombre..." onkeydown="if(event.key==='Enter'){event.preventDefault();agregarProducto('${sid}')}" style="font-family:Raleway,sans-serif;font-size:.85rem;padding:7px 9px;border:1.5px solid var(--border);border-radius:var(--radius-sm);background:var(--white);color:var(--text);min-height:38px;width:100%">
          </div>
          <div class="f-btns">
            <button class="btn-sm primary" onclick="agregarProducto('${sid}')">Agregar</button>
            <button class="btn-sm secondary" onclick="toggleAddProd('${sid}')">Cancelar</button>
          </div>
        </div>
        <div id="store-footer-${sid}" style="${collapsed ? 'display:none' : ''}">
          ${esPrincipal
            ? `<div class="store-footer" style="color:var(--text-muted);font-size:.8rem;padding:10px 16px">Gestionado desde la pestana <strong>Stock Principal</strong></div>`
            : `<div class="store-footer"><button class="btn-add-prod" onclick="toggleAddProd('${sid}')">+ Agregar producto</button></div>`
          }
        </div>
      </div>`;
  }

  function renderProdFila(sid, prod, esPrincipal) {
    const pid = prod.id;
    const fechaEntrega = prod.fecha_entrega
      ? new Date(prod.fecha_entrega).toLocaleDateString('es-PY', {day:'2-digit',month:'2-digit',year:'numeric'})
      : '';
    const recibidoPor = prod.recibido_por || '';
    const infoTooltip = (fechaEntrega || recibidoPor)
      ? `Entrega: ${fechaEntrega || '—'}${recibidoPor ? ' · Recibido por: ' + escapeHtml(recibidoPor) : ''}`
      : 'Sin datos de entrega';
    return `
      <tr id="crow-${sid}-${pid}">
        <td style="display:flex;align-items:center;gap:6px">
          <input class="inline-edit" type="text"
            value="${escapeHtml(prod.nombre)}"
            id="cp-nombre-${sid}-${pid}"
            onblur="guardarProd('${sid}','${pid}')"
            onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur()}"
            aria-label="Nombre del producto"
            style="flex:1">
          <span title="${escapeHtml(infoTooltip)}" style="cursor:default;color:var(--text-muted);flex-shrink:0" aria-label="${escapeHtml(infoTooltip)}">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10"/><path stroke-linecap="round" d="M12 16v-4m0-4h.01"/>
            </svg>
          </span>
        </td>
        <td class="td-c">
          <div class="consig-stock-wrap">
            <button class="btn-adj-sm minus" onclick="ajustarProd('${sid}','${pid}',-1)" title="Restar 1">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M20 12H4"/></svg>
            </button>
            <input class="consig-stock-input" type="number"
              id="cp-stock-${sid}-${pid}"
              value="${prod.stock}"
              min="0"
              onblur="guardarProd('${sid}','${pid}')"
              onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur()}">
            <button class="btn-adj-sm" onclick="ajustarProd('${sid}','${pid}',1)" title="Sumar 1">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 4v16m8-8H4"/></svg>
            </button>
          </div>
        </td>
        <td>
          <input class="inline-edit" type="text"
            value="${escapeHtml(prod.notas || '')}"
            id="cp-notas-${sid}-${pid}"
            placeholder="—"
            onblur="guardarProd('${sid}','${pid}')"
            onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur()}"
            aria-label="Notas">
        </td>
        <td class="td-c">
          ${esPrincipal ? '' : `<button class="btn-icon danger" onclick="eliminarProducto('${sid}','${pid}')" title="Eliminar producto">
            <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
            </svg>
          </button>`}
        </td>
      </tr>`;
  }

  /* ─── Colapsar/expandir tienda ─── */
  function toggleStoreCollapse(sid) {
    storeCollapsed[sid] = !storeCollapsed[sid];
    const collapsed = storeCollapsed[sid];
    const body    = document.getElementById('store-body-' + sid);
    const footer  = document.getElementById('store-footer-' + sid);
    const chevron = document.getElementById('chevron-' + sid);
    if (body)    body.style.display    = collapsed ? 'none' : '';
    if (footer)  footer.style.display  = collapsed ? 'none' : '';
    if (chevron) chevron.style.transform = collapsed ? 'rotate(-90deg)' : 'rotate(0deg)';
  }

  /* ─── Toggle helpers ─── */
  function toggleNewStoreForm() {
    const f = document.getElementById('new-store-form');
    const visible = f.classList.toggle('visible');
    if (visible) { document.getElementById('ns-nombre').focus(); }
    else { document.getElementById('ns-nombre').value = ''; document.getElementById('ns-dir').value = ''; }
  }

  function toggleAddProd(sid) {
    const f = document.getElementById('addprod-form-' + sid);
    const visible = f.classList.toggle('visible');
    if (visible) {
      const today = new Date().toISOString().slice(0,10);
      const fechaEl = document.getElementById('ap-fecha-' + sid);
      if (fechaEl) fechaEl.value = today;
    } else {
      document.getElementById('ap-nombre-' + sid).value = '';
      document.getElementById('ap-stock-' + sid).value = '0';
      document.getElementById('ap-notas-' + sid).value = '';
      const fechaEl = document.getElementById('ap-fecha-' + sid);
      if (fechaEl) fechaEl.value = '';
      const recEl = document.getElementById('ap-recibido-' + sid);
      if (recEl) recEl.value = '';
    }
  }

  function toggleEditStore(sid) {
    const f = document.getElementById('edit-form-' + sid);
    f.classList.toggle('visible');
    if (f.classList.contains('visible')) {
      document.getElementById('ef-nombre-' + sid).focus();
    }
  }

  /* ─── Consignacion API calls ─── */
  async function crearTienda() {
    const nombre = document.getElementById('ns-nombre').value.trim();
    if (!nombre) { mostrarToast('El nombre es obligatorio', 'err'); return; }
    const tipo = document.getElementById('ns-tipo').value;
    const dir  = document.getElementById('ns-dir').value.trim();
    try {
      const res = await fetch('/api/consignacion/tiendas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre, tipo, direccion: dir })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      consigData.tiendas.push(data.tienda);
      toggleNewStoreForm();
      renderConsig();
      mostrarToast('Tienda creada', 'ok');
    } catch (err) {
      mostrarToast('Error al crear tienda', 'err');
    }
  }

  async function guardarEditTienda(sid) {
    const nombre = document.getElementById('ef-nombre-' + sid).value.trim();
    const dir    = document.getElementById('ef-dir-' + sid).value.trim();
    if (!nombre) { mostrarToast('El nombre es obligatorio', 'err'); return; }
    try {
      const res = await fetch('/api/consignacion/tiendas/' + sid, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre, direccion: dir })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const idx = consigData.tiendas.findIndex(t => t.id === sid);
      if (idx !== -1) { consigData.tiendas[idx].nombre = data.tienda.nombre; consigData.tiendas[idx].direccion = data.tienda.direccion; }
      renderConsig();
      mostrarToast('Tienda actualizada', 'ok');
    } catch (err) {
      mostrarToast('Error al guardar', 'err');
    }
  }

  async function eliminarTienda(sid) {
    if (!confirm('Eliminar esta tienda y todos sus productos?')) return;
    try {
      const res = await fetch('/api/consignacion/tiendas/' + sid, { method: 'DELETE' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      consigData.tiendas = consigData.tiendas.filter(t => t.id !== sid);
      renderConsig();
      mostrarToast('Tienda eliminada', 'ok');
    } catch (err) {
      mostrarToast('Error al eliminar', 'err');
    }
  }

  function getCatalogOptions() {
    if (!stockData || !stockData.productos) return '';
    return Object.values(stockData.productos)
      .map(p => `<option value="${escapeHtml(p.nombre)}">${escapeHtml(p.nombre)}</option>`)
      .join('');
  }

  function onProdSelectChange(sid) {
    const sel = document.getElementById('ap-select-' + sid);
    const customInput = document.getElementById('ap-nombre-' + sid);
    if (sel.value === '__custom__') {
      customInput.style.display = 'block';
      customInput.focus();
    } else {
      customInput.style.display = 'none';
      customInput.value = '';
    }
  }

  async function agregarProducto(sid) {
    const sel = document.getElementById('ap-select-' + sid);
    const customInput = document.getElementById('ap-nombre-' + sid);
    const nombre = (sel && sel.value && sel.value !== '__custom__')
      ? sel.value
      : customInput.value.trim();
    if (!nombre) { mostrarToast('El nombre es obligatorio', 'err'); return; }
    const stock = parseInt(document.getElementById('ap-stock-' + sid).value, 10) || 0;
    const notas = document.getElementById('ap-notas-' + sid).value.trim();
    const fechaEl = document.getElementById('ap-fecha-' + sid);
    const recibidoEl = document.getElementById('ap-recibido-' + sid);
    const fecha_entrega = fechaEl ? (fechaEl.value ? fechaEl.value + 'T00:00:00' : '') : '';
    const recibido_por = recibidoEl ? recibidoEl.value.trim() : '';
    try {
      const res = await fetch('/api/consignacion/tiendas/' + sid + '/productos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre, stock, notas, fecha_entrega, recibido_por })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const tienda = consigData.tiendas.find(t => t.id === sid);
      if (tienda) tienda.productos.push(data.producto);
      toggleAddProd(sid);
      renderConsig();
      mostrarToast('Producto agregado', 'ok');
    } catch (err) {
      mostrarToast('Error al agregar producto', 'err');
    }
  }

  async function guardarProd(sid, pid) {
    const tienda = consigData && consigData.tiendas.find(t => t.id === sid);
    if (!tienda) return;
    const prod = tienda.productos.find(p => p.id === pid);
    if (!prod) return;
    const nombre = document.getElementById('cp-nombre-' + sid + '-' + pid).value.trim();
    const stockVal = parseInt(document.getElementById('cp-stock-' + sid + '-' + pid).value, 10);
    const notas = document.getElementById('cp-notas-' + sid + '-' + pid).value.trim();
    if (!nombre) return;
    const stock = isNaN(stockVal) || stockVal < 0 ? prod.stock : stockVal;
    // skip if nothing changed
    if (nombre === prod.nombre && stock === prod.stock && notas === (prod.notas || '')) return;
    try {
      const res = await fetch('/api/consignacion/tiendas/' + sid + '/productos/' + pid, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nombre, stock, notas })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      prod.nombre = data.producto.nombre;
      prod.stock  = data.producto.stock;
      prod.notas  = data.producto.notas;
      const row = document.getElementById('crow-' + sid + '-' + pid);
      if (row) { row.classList.remove('flash-ok'); void row.offsetWidth; row.classList.add('flash-ok'); }
      actualizarConsigKPIs();
      mostrarToast('Guardado', 'ok');
    } catch (err) {
      mostrarToast('Error al guardar', 'err');
    }
  }

  async function ajustarProd(sid, pid, delta) {
    const tienda = consigData && consigData.tiendas.find(t => t.id === sid);
    if (!tienda) return;
    const prod = tienda.productos.find(p => p.id === pid);
    if (!prod) return;
    const nuevoStock = Math.max(0, prod.stock + delta);
    if (nuevoStock === prod.stock) return;
    const inputEl = document.getElementById('cp-stock-' + sid + '-' + pid);
    if (inputEl) inputEl.value = nuevoStock;
    try {
      const res = await fetch('/api/consignacion/tiendas/' + sid + '/productos/' + pid, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stock: nuevoStock })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      prod.stock = nuevoStock;
      const row = document.getElementById('crow-' + sid + '-' + pid);
      if (row) { row.classList.remove('flash-ok'); void row.offsetWidth; row.classList.add('flash-ok'); }
      actualizarConsigKPIs();
      mostrarToast('Stock actualizado', 'ok');
    } catch (err) {
      if (inputEl) inputEl.value = prod.stock;
      mostrarToast('Error al guardar', 'err');
    }
  }

  async function eliminarProducto(sid, pid) {
    if (!confirm('Eliminar este producto?')) return;
    try {
      const res = await fetch('/api/consignacion/tiendas/' + sid + '/productos/' + pid, { method: 'DELETE' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const tienda = consigData.tiendas.find(t => t.id === sid);
      if (tienda) tienda.productos = tienda.productos.filter(p => p.id !== pid);
      renderConsig();
      mostrarToast('Producto eliminado', 'ok');
    } catch (err) {
      mostrarToast('Error al eliminar', 'err');
    }
  }

  /* ─── Boot ─── */
  cargarStock(false);
  cargarConsig();
  refreshTimer = setInterval(() => cargarStock(false), 60000);
</script>
</body>
</html>"""
