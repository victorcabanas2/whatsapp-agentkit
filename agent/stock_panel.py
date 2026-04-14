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
STOCK_FILE = "knowledge/stock_actual.json"


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
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Panel de Stock — Rebody</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                padding: 30px;
            }

            h1 {
                color: #333;
                margin-bottom: 10px;
                text-align: center;
            }

            .ultima-actualizacion {
                text-align: center;
                color: #666;
                font-size: 12px;
                margin-bottom: 30px;
            }

            .tabla-container {
                overflow-x: auto;
            }

            table {
                width: 100%;
                border-collapse: collapse;
            }

            th {
                background: #667eea;
                color: white;
                padding: 15px;
                text-align: left;
                font-weight: 600;
            }

            td {
                padding: 12px 15px;
                border-bottom: 1px solid #eee;
            }

            tr:hover {
                background: #f9f9f9;
            }

            .nombre {
                font-weight: 500;
                color: #333;
            }

            .stock-cell {
                display: flex;
                align-items: center;
                gap: 10px;
            }

            .stock-input {
                width: 80px;
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                text-align: center;
            }

            button {
                background: #667eea;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                transition: background 0.2s;
            }

            button:hover {
                background: #764ba2;
            }

            button.less {
                background: #e74c3c;
            }

            button.less:hover {
                background: #c0392b;
            }

            button.save {
                background: #27ae60;
                width: 100%;
            }

            button.save:hover {
                background: #229954;
            }

            .agotado {
                color: #e74c3c;
                font-weight: bold;
            }

            .disponible {
                color: #27ae60;
                font-weight: bold;
            }

            .bajo-stock {
                color: #f39c12;
                font-weight: bold;
            }

            .estado {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 600;
            }

            .estado.ok {
                background: #d4edda;
                color: #155724;
            }

            .estado.bajo {
                background: #fff3cd;
                color: #856404;
            }

            .estado.agotado {
                background: #f8d7da;
                color: #721c24;
            }

            .loading {
                text-align: center;
                padding: 40px;
                color: #666;
            }

            .error {
                background: #f8d7da;
                color: #721c24;
                padding: 15px;
                border-radius: 4px;
                margin-bottom: 20px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📦 Panel de Stock — Rebody</h1>
            <div class="ultima-actualizacion" id="fecha"></div>
            <div id="error"></div>
            <div class="tabla-container" id="tabla-container">
                <div class="loading">Cargando stock...</div>
            </div>
        </div>

        <script>
            let stockData = {};

            async function cargarStock() {
                try {
                    const response = await fetch('/api/stock');
                    const data = await response.json();
                    stockData = data;
                    renderTabla();
                } catch (error) {
                    console.error('Error:', error);
                    document.getElementById('error').innerHTML =
                        `<div class="error">Error cargando stock: ${error.message}</div>`;
                }
            }

            function renderTabla() {
                const productos = Object.values(stockData.productos || {});
                const fecha = new Date(stockData.ultima_actualizacion).toLocaleString('es-PY');

                document.getElementById('fecha').textContent = `Última actualización: ${fecha}`;

                let html = `
                    <table>
                        <thead>
                            <tr>
                                <th>Producto</th>
                                <th>Stock</th>
                                <th>Estado</th>
                                <th>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                `;

                productos.forEach(prod => {
                    let estadoClass = 'ok';
                    let estadoTexto = 'Disponible';

                    if (prod.stock === 0) {
                        estadoClass = 'agotado';
                        estadoTexto = 'Agotado';
                    } else if (prod.stock <= 2) {
                        estadoClass = 'bajo';
                        estadoTexto = 'Bajo stock';
                    }

                    html += `
                        <tr>
                            <td class="nombre">${prod.nombre}</td>
                            <td>
                                <div class="stock-cell">
                                    <input type="number" class="stock-input"
                                           id="stock-${prod.id}"
                                           value="${prod.stock}"
                                           min="0">
                                </div>
                            </td>
                            <td>
                                <span class="estado ${estadoClass}">${estadoTexto}</span>
                            </td>
                            <td>
                                <button onclick="restarStock('${prod.id}', 1)" class="less">−1</button>
                                <button onclick="sumarStock('${prod.id}', 1)">+1</button>
                                <button onclick="guardarStock('${prod.id}')" class="save">Guardar</button>
                            </td>
                        </tr>
                    `;
                });

                html += `
                        </tbody>
                    </table>
                `;

                document.getElementById('tabla-container').innerHTML = html;
            }

            async function sumarStock(productId, cantidad) {
                try {
                    const response = await fetch(`/api/stock/${productId}/add?cantidad=${cantidad}`, {
                        method: 'POST'
                    });
                    const data = await response.json();
                    stockData.productos[productId] = data.producto;
                    renderTabla();
                } catch (error) {
                    alert('Error: ' + error.message);
                }
            }

            async function restarStock(productId, cantidad) {
                try {
                    const response = await fetch(`/api/stock/${productId}/subtract?cantidad=${cantidad}`, {
                        method: 'POST'
                    });
                    const data = await response.json();
                    stockData.productos[productId] = data.producto;
                    renderTabla();
                } catch (error) {
                    alert('Error: ' + error.message);
                }
            }

            async function guardarStock(productId) {
                const nuevoStock = parseInt(document.getElementById(`stock-${productId}`).value);

                try {
                    const response = await fetch(`/api/stock/${productId}?stock=${nuevoStock}`, {
                        method: 'POST'
                    });
                    const data = await response.json();
                    stockData.productos[productId] = data.producto;
                    renderTabla();
                } catch (error) {
                    alert('Error: ' + error.message);
                }
            }

            // Cargar stock al iniciar
            cargarStock();

            // Actualizar cada 30 segundos
            setInterval(cargarStock, 30000);
        </script>
    </body>
    </html>
    """
