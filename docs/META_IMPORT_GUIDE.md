# 💬 Guía de Importación desde Meta/Facebook

## Resumen

El sistema ahora puede importar automáticamente clientes de tu historial de conversaciones de Meta/Facebook. Extrae números de teléfono, nombres de clientes y productos mencionados en las conversaciones.

## ¿Qué hace el parser Meta?

Cuando cargas datos de Meta, el sistema:

1. **Extrae teléfonos**: Busca números en formato internacional (595...)
2. **Obtiene nombres**: Lee el nombre del cliente desde contact_info
3. **Identifica productos**: Detecta productos mencionados (WHOOP, TheraFace, JetBoots, etc.)
4. **Crea registros**: Guarda cada cliente como "cliente pasado" (es_cliente_previo=True)
5. **Evita duplicados**: No re-importa clientes que ya existen

## Formato de datos esperado

El sistema acepta datos tab-separados con esta estructura:

```
contact_info                        message_content                              message_timestamp    profile_image
"Juan Pérez"                        "Hola, me interesa el Whoop band"           "2:14 pm"           "https://..."
"Susana Quevedo (595991234567)"    "¿Cuánto cuesta la TheraFace?"              "3:30 pm"           "https://..."
"Victor Cabañas"                    "Quiero comprar JetBoots y Depuffing Wand"  "4:45 pm"           "https://..."
```

### Requisitos:
- **Columna 1 (contact_info)**: Nombre del cliente, opcionalmente con teléfono
  - Formatos válidos:
    - "Juan Pérez"
    - "Juan Pérez (595991234567)"
    - "Juan Pérez 595991234567"
- **Columna 2 (message_content)**: Contenido del último mensaje
- **Columna 3 (message_timestamp)**: Timestamp del mensaje (cualquier formato)
- **Columna 4 (profile_image)**: URL de imagen del perfil (opcional)

## Cómo importar

### Opción 1: Pegar texto directamente

1. Ve al **Dashboard Admin** → Tab "📥 Importados"
2. En la sección "💬 Desde Meta/Facebook", pega los datos en el textarea
3. Haz clic en "💬 Importar desde Meta"
4. Confirma en el popup que aparezca

### Opción 2: Cargar un archivo .txt

1. Guarda tus datos Meta en un archivo `clientes_meta.txt`
2. Ve al Dashboard → Tab "📥 Importados"
3. Haz clic en "📁 Cargar archivo .txt"
4. Selecciona el archivo
5. El contenido se cargará automáticamente en el textarea
6. Haz clic en "💬 Importar desde Meta"

## Extracción automática de teléfonos

El parser usa esta lógica para extraer teléfonos:

1. **En contact_info** (prioritario):
   - Busca números que empiecen con 595 (formato internacional Paraguay)
   - Formatos reconocidos: "595991234567", "(595991234567)", "595 99 1234567"

2. **En message_content**:
   - Si no encuentra en contact_info, busca en el mensaje

3. **Teléfono generado**:
   - Si no hay teléfono en los datos, crea uno basado en el nombre (hash)
   - Esto evita duplicados pero permite importar igual

## Extracción automática de productos

El parser detecta estos productos:

| Palabra clave | Producto |
|---|---|
| whoop | WHOOP Band |
| jetboots | JetBoots |
| theraface | TheraFace |
| depuffing | Depuffing Wand |
| faq | FAQ 211 |
| foreo | FOREO |
| therabody | Therabody |
| massage | Massage Gun |
| fascia | Fascia Gun |

**Nota**: La búsqueda es case-insensitive, así que "Whoop", "WHOOP" y "whoop" se detectan igual.

## Resultado de importación

Después de importar, verás un resumen como:

```
✓ Importados: 45 | Duplicados: 3 | Errores: 2
```

### Significados:

- **Importados**: Clientes nuevos agregados a la BD
- **Duplicados**: Clientes que ya existían (no se re-importan)
- **Errores**: Filas que no se pudieron procesar (nombre vacío, formato inválido, etc.)

Para ver los detalles de cada fila:
- Abre la consola del navegador (F12)
- Busca el log que contiene "detalles"

## Casos de uso

### Caso 1: Migración desde Meta
Tienes 500 conversaciones en Meta y quieres cargarlas en el sistema como "clientes pasados".

```bash
1. Exporta el historial de Meta
2. Copia y pega en el dashboard
3. Haz clic en "Importar desde Meta"
4. Los 500 clientes estarán disponibles para seguimiento
```

### Caso 2: Recuperar clientes perdidos
Perdiste tu base de datos pero tienes el historial de Meta.

```bash
1. Exporta Meta completo
2. Importa todos los clientes
3. El bot verá que son "clientes pasados" y los tratará diferente
4. Puedes reactivarlos con mensajes personalizados
```

### Caso 3: Combinar fuentes
Ya tienes clientes de Excel, ahora quieres agregar los de Meta.

```bash
1. Importa el Excel (tab "Importados" → "📥 Importar desde Excel")
2. Luego importa Meta (sección "💬 Desde Meta")
3. El sistema detecta automáticamente duplicados y no los re-importa
```

## Solución de problemas

### Error: "Formato inválido"
- Verificar que los datos están separados por TABS (no espacios)
- En Excel, copiar y pegar mantiene los tabs
- Si editas en un editor de texto, asegúrate de usar tabs (\t)

### Problema: No se detectan teléfonos
- Si faltan teléfonos, el sistema genera IDs basados en el nombre
- Los clientes se importan igual, pero sin número real
- Solución: Agregá los teléfonos a contact_info manualmente si es posible

### Problema: Algunos clientes no se importan
- Revisa el resumen: "Duplicados" y "Errores"
- Duplicados = cliente ya existe (checkeá la tabla de clientes)
- Errores = fila incompleta o con formato inválido
- Solución: Revisar la fila original en Meta/Excel

## API

### POST /api/admin/importar-meta

Importa datos Meta via API.

**Request:**
```json
{
  "datos": "contact_info\tmessage_content\t...\n..."
}
```

O como form-data:
- `datos`: string con datos tab-separados
- `archivo`: file (.txt) alternativa a `datos`

**Response:**
```json
{
  "exitosos": 45,
  "errores": 2,
  "duplicados": 3,
  "total": 50,
  "detalles": [
    {
      "fila": 2,
      "nombre": "Juan Pérez",
      "telefono": "595991234567",
      "productos": "WHOOP Band, TheraFace",
      "status": "✓ Importado desde Meta"
    }
  ]
}
```

## Información técnica

- **Archivo**: `agent/meta_parser.py`
- **Endpoint**: `POST /api/admin/importar-meta`
- **Database**: Tabla `leads` con `es_cliente_previo=True`
- **Validación**: Teléfono requerido (generado si falta)
- **Duplicados**: Basado en teléfono único
- **Transacciones**: Cada cliente en transacción atómica

## Preguntas frecuentes

**P: ¿Pierdo datos si importo dos veces lo mismo?**  
R: No. El sistema detecta duplicados por teléfono y no los re-importa.

**P: ¿Puedo editar los datos importados?**  
R: Sí. Los clientes importados aparecen en la tabla "Clientes Importados". Puedes buscar, ver detalles, y si quieres eliminar, usa la opción de eliminar cliente.

**P: ¿Qué pasa si no hay teléfono?**  
R: Se genera un ID basado en el nombre. El cliente se importa igual pero no podrá recibir mensajes hasta que agregues su teléfono real.

**P: ¿Importa automáticamente o necesito hacer algo?**  
R: Importa cuando lo solicitas. No es automático.

**P: ¿Puedo importar desde WhatsApp directo?**  
R: No por ahora. Necesitas exportar desde Meta primero, luego importar aquí.
