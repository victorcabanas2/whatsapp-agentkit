# agent/meta_parser.py — Parser para importar clientes desde exportación Meta/Facebook

"""
Funciones para parsear la exportación de conversaciones de Meta/Facebook
y cargar los clientes en la base de datos como "clientes pasados".
"""

import re
import logging
from datetime import datetime
from agent.memory import marcar_cliente_como_antiguo, async_session, Lead
from sqlalchemy import select

logger = logging.getLogger("agentkit")


async def importar_desde_meta(datos_texto: str) -> dict:
    """
    Parsea datos tab-separados de Meta/Facebook y carga clientes en la BD.

    Formato esperado (tab-separated):
    contact_info        message_content        message_timestamp    profile_image
    "Susana Quevedo"    "[mensaje]"            "3:14 pm"           "[url]"
    "Victor Cabañas"    "Hola"                 "2:38 pm"           "[url]"

    Extrae:
    - Nombre del cliente: contact_info (antes del paréntesis si existe)
    - Teléfono: intenta extraer números en formato internacional (595...)
    - Productos: palabras clave encontradas en message_content
    - Historial: últimos 3 mensajes del cliente

    Returns:
        {
            "exitosos": int,
            "errores": int,
            "duplicados": int,
            "total": int,
            "detalles": []
        }
    """
    # Palabras clave de productos Rebody
    PALABRAS_CLAVE_PRODUCTOS = {
        "whoop": "WHOOP Band",
        "jetboots": "JetBoots",
        "theraface": "TheraFace",
        "depuffing": "Depuffing Wand",
        "faq": "FAQ 211",
        "foreo": "FOREO",
        "therabody": "Therabody",
        "massage": "Massage Gun",
        "fascia": "Fascia Gun",
    }

    exitosos = 0
    errores = 0
    duplicados = 0
    detalles = []
    clientes_procesados = {}  # Para evitar duplicados en esta sesión

    try:
        # Dividir por líneas
        lineas = datos_texto.strip().split("\n")

        if len(lineas) < 2:
            return {"error": "Formato inválido — se esperan al menos 2 líneas"}

        # Primera línea = headers (ignorar)
        headers = lineas[0].split("\t")
        logger.info(f"Headers detectados: {headers}")

        # Procesar cada línea de datos
        async with async_session() as session:
            for idx, linea in enumerate(lineas[1:], start=2):
                try:
                    # Separar por tabs
                    partes = linea.split("\t")

                    if len(partes) < 2:
                        detalles.append({"fila": idx, "error": "Formato inválido (menos de 2 columnas)"})
                        errores += 1
                        continue

                    contact_info = partes[0].strip().strip('"')
                    message_content = partes[1].strip().strip('"') if len(partes) > 1 else ""
                    message_timestamp = partes[2].strip().strip('"') if len(partes) > 2 else ""
                    profile_image = partes[3].strip().strip('"') if len(partes) > 3 else ""

                    # ═══════════════════════════════════════════════════════════
                    # EXTRAER NOMBRE DEL CLIENTE
                    # ═══════════════════════════════════════════════════════════

                    nombre = contact_info

                    # Si contact_info tiene paréntesis (nombre (número)), extraer solo el nombre
                    if "(" in nombre and ")" in nombre:
                        nombre = nombre.split("(")[0].strip()

                    if not nombre or nombre == "Unknown" or nombre.lower() == "unknown contact":
                        detalles.append({"fila": idx, "error": "Nombre vacío o desconocido"})
                        errores += 1
                        continue

                    # ═══════════════════════════════════════════════════════════
                    # EXTRAER TELÉFONO
                    # ═══════════════════════════════════════════════════════════

                    telefono = None

                    # Buscar números de teléfono: formato internacional 595... o (595...)
                    matches_telefono = re.findall(r"595\d{7,12}", contact_info)
                    if matches_telefono:
                        telefono = matches_telefono[0]
                    else:
                        # Si no está en contact_info, buscar en message_content o profile_image
                        matches_telefono = re.findall(r"595\d{7,12}", f"{message_content} {profile_image}")
                        if matches_telefono:
                            telefono = matches_telefono[0]

                    # Si no encontramos teléfono, usar un ID basado en el nombre
                    if not telefono:
                        # Generar teléfono dummy basado en nombre para evitar duplicados
                        nombre_hash = str(hash(nombre))[-10:]
                        telefono = f"595{nombre_hash}"
                        logger.debug(f"Teléfono no encontrado para {nombre}, usando ID generado: {telefono}")

                    telefono_limpio = telefono.replace("+", "").replace(" ", "").replace("-", "")

                    # ═══════════════════════════════════════════════════════════
                    # BUSCAR TELÉFONO DUPLICADO EN BD
                    # ═══════════════════════════════════════════════════════════

                    # Evitar duplicados en esta sesión
                    if telefono_limpio in clientes_procesados:
                        duplicados += 1
                        detalles.append({
                            "fila": idx,
                            "nombre": nombre,
                            "telefono": telefono_limpio,
                            "status": "duplicado en importación"
                        })
                        continue

                    # Verificar si ya existe en BD
                    query = select(Lead).where(Lead.telefono == telefono_limpio)
                    result = await session.execute(query)
                    lead_existente = result.scalar_one_or_none()

                    if lead_existente and lead_existente.es_cliente_previo:
                        duplicados += 1
                        detalles.append({
                            "fila": idx,
                            "nombre": nombre,
                            "telefono": telefono_limpio,
                            "status": "ya existe en BD"
                        })
                        continue

                    # ═══════════════════════════════════════════════════════════
                    # EXTRAER PRODUCTOS MENCIONADOS
                    # ═══════════════════════════════════════════════════════════

                    productos_encontrados = []
                    contenido_lower = message_content.lower()

                    for palabra_clave, nombre_producto in PALABRAS_CLAVE_PRODUCTOS.items():
                        if palabra_clave in contenido_lower and nombre_producto not in productos_encontrados:
                            productos_encontrados.append(nombre_producto)

                    productos_str = ", ".join(productos_encontrados) if productos_encontrados else "—"

                    # ═══════════════════════════════════════════════════════════
                    # CREAR RESUMEN HISTÓRICO
                    # ═══════════════════════════════════════════════════════════

                    historial_resumen = f"Último mensaje: {message_content[:100]}... ({message_timestamp})"

                    # ═══════════════════════════════════════════════════════════
                    # GUARDAR COMO CLIENTE ANTIGUO
                    # ═══════════════════════════════════════════════════════════

                    success = await marcar_cliente_como_antiguo(
                        telefono=telefono_limpio,
                        nombre=nombre,
                        productos_comprados=productos_str,
                        historial_resumen=historial_resumen
                    )

                    if success:
                        exitosos += 1
                        clientes_procesados[telefono_limpio] = True
                        detalles.append({
                            "fila": idx,
                            "nombre": nombre,
                            "telefono": telefono_limpio,
                            "productos": productos_str,
                            "status": "✓ Importado desde Meta"
                        })
                        logger.info(f"✓ Cliente Meta importado: {nombre} ({telefono_limpio}) - Productos: {productos_str}")
                    else:
                        errores += 1
                        detalles.append({
                            "fila": idx,
                            "nombre": nombre,
                            "telefono": telefono_limpio,
                            "error": "Error al guardar en BD"
                        })
                        logger.error(f"Error guardando cliente Meta: {nombre} ({telefono_limpio})")

                except Exception as e:
                    errores += 1
                    detalles.append({"fila": idx, "error": str(e)})
                    logger.error(f"Error procesando línea {idx}: {e}")

        return {
            "exitosos": exitosos,
            "errores": errores,
            "duplicados": duplicados,
            "total": exitosos + errores + duplicados,
            "detalles": detalles
        }

    except Exception as e:
        logger.error(f"Error al parsear datos Meta: {e}")
        return {"error": str(e)}
