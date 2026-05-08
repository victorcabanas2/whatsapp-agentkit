#!/bin/sh
# Inicializa DATA_DIR con los archivos por defecto si no existen.
# Esto corre antes de uvicorn en cada deploy.
# En Railway, DATA_DIR apunta al volumen persistente (/app/data).
# En local, DATA_DIR no está seteado y este script no hace nada útil.

set -e

DATA_DIR="${DATA_DIR:-}"

if [ -n "$DATA_DIR" ]; then
    mkdir -p "$DATA_DIR"
    for f in stock_actual.json consignacion.json movimientos.json; do
        if [ ! -f "$DATA_DIR/$f" ]; then
            if [ -f "/app/knowledge/$f" ]; then
                cp "/app/knowledge/$f" "$DATA_DIR/$f"
                echo "[entrypoint] Inicializado $DATA_DIR/$f desde defaults"
            fi
        fi
    done
fi

exec uvicorn agent.main:app --host 0.0.0.0 --port "${PORT:-8000}"
