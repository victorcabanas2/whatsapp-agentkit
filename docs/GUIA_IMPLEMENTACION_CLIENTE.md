# Guía de Implementación — Nuevo Cliente
**De cero a bot funcionando en WhatsApp**

---

## ANTES DE EMPEZAR — Cuentas que necesitás tener (una sola vez)

Estas cuentas las creás UNA vez y las usás para todos los clientes:

| Cuenta | Para qué | Costo |
|---|---|---|
| [GitHub](https://github.com) | Guardar y copiar el código | Gratis |
| [Railway](https://railway.app) | Hospedar el bot | Gratis hasta $5, luego ~$5-15/mes |
| [Anthropic](https://console.anthropic.com) | La IA (Claude) | Pago por uso |
| [Whapi](https://whapi.cloud) | Conectar WhatsApp | ~$10-25/mes por número |

Si ya tenés estas cuentas, saltá directo al Paso 1.

---

## CHECKLIST ANTES DE EMPEZAR CON EL CLIENTE

Pedile esto al cliente ANTES de tocar código. Sin estos materiales no podés empezar:

- [ ] Número de WhatsApp del negocio (que no lo usen para mensajes personales)
- [ ] Lista de productos: nombre, precio, descripción, link web si tiene
- [ ] Datos bancarios (si acepta transferencias)
- [ ] Las preguntas más frecuentes que reciben y las respuestas correctas
- [ ] Nombre que quieren para el agente ("Sofía", "Lucas", etc.)
- [ ] Tono preferido (formal con "usted" / informal con "vos")
- [ ] Datos del negocio: dirección, horarios, métodos de pago

---

## PASO 1 — COPIAR EL PROYECTO BASE

Cada cliente es una copia independiente del proyecto. Nunca modificás el proyecto original.

### 1.1 Abrir la terminal

En Mac: presionás `Cmd + Espacio`, escribís "Terminal", Enter.

### 1.2 Ir a la carpeta donde guardás los proyectos de clientes

```bash
cd ~/Desktop
```
(o donde prefieras tener los proyectos)

### 1.3 Copiar el proyecto base con el nombre del cliente

```bash
cp -r ~/whatsapp-agentkit nombre-del-cliente-bot
```

Ejemplo real:
```bash
cp -r ~/whatsapp-agentkit ferreteria-perez-bot
```

### 1.4 Entrar a la carpeta del cliente

```bash
cd ferreteria-perez-bot
```

### 1.5 Eliminar la base de datos vieja (datos de Rebody)

```bash
rm -f agentkit.db agentkit_memory.log
```

Listo. Tenés una copia limpia del proyecto lista para configurar.

---

## PASO 2 — CREAR EL ARCHIVO DE CONFIGURACIÓN (.env)

El archivo `.env` contiene todas las "contraseñas" y configuraciones privadas del cliente. Nunca lo subís a GitHub.

### 2.1 Crear el archivo

```bash
cp .env.example .env
```

### 2.2 Abrirlo para editar

```bash
open -e .env
```
(Abre el bloc de notas en Mac. También podés usar VS Code si lo tenés.)

### 2.3 Completar estos valores

Abrís el archivo y completás los valores. Vas a ver líneas como `ANTHROPIC_API_KEY=sk-ant-...`. Reemplazás lo que está después del `=` con el valor real:

```
ANTHROPIC_API_KEY=        ← tu clave de Anthropic (siempre la misma para todos los clientes)
WHATSAPP_PROVIDER=whapi
WHAPI_TOKEN=              ← el token de Whapi del número del cliente (lo obtenés en el Paso 3)
PORT=8000
ENVIRONMENT=production
DATABASE_URL=sqlite+aiosqlite:////app/data/agentkit.db
VENDEDOR_WHATSAPP=595XXXXXXXXX   ← número del dueño para alertas (con código de país, sin +)
ADMIN_PASSWORD=           ← contraseña para el panel de control del cliente
ADMIN_WHATSAPP=+595XXXXXXXXX     ← número del admin (vos o el cliente)
```

**Sobre la clave de Anthropic**: es la misma para todos los clientes. La encontrás en [console.anthropic.com](https://console.anthropic.com) → API Keys.

Guardás el archivo (`Cmd + S`) y lo cerrás.

---

## PASO 3 — CONECTAR EL WHATSAPP DEL CLIENTE EN WHAPI

Aquí es donde el número de WhatsApp del cliente se "activa" para poder recibir y enviar mensajes por API.

### 3.1 Entrar a Whapi

Ir a [whapi.cloud](https://whapi.cloud) y loguearte.

### 3.2 Crear un nuevo canal

- Clic en **"New Channel"** o **"Agregar canal"**
- Elegís el plan (el básico sirve para empezar)
- Le ponés un nombre al canal: "Ferretería Pérez" (solo para tu organización interna)

### 3.3 Conectar el número del cliente

- Whapi te muestra un **código QR**
- El cliente abre WhatsApp en su celular
- Va a: Ajustes → Dispositivos vinculados → Vincular dispositivo
- Escanea el QR con el celular

**Importante**: el WhatsApp queda abierto en el celular normalmente, el bot usa una "sesión paralela". El dueño puede seguir usando su WhatsApp.

### 3.4 Copiar el token del canal

Una vez conectado, Whapi te muestra el **token** del canal. Es un texto largo tipo `TKN_xxxxxxxxxxxxxxxxxxx`.

Copiás ese token y lo pegás en el `.env` en `WHAPI_TOKEN=`.

---

## PASO 4 — CONFIGURAR EL NEGOCIO DEL CLIENTE

### 4.1 Abrir el archivo de negocio

```bash
open -e config/business.yaml
```

### 4.2 Reemplazar los datos de Rebody por los del cliente

Vas a ver el archivo con datos de Rebody. Los reemplazás todos. El formato es exactamente este:

```yaml
negocio:
  nombre: Ferretería Pérez          ← nombre del negocio
  descripcion: |
    Ferretería con 20 años en el mercado. Vendemos
    herramientas, materiales de construcción y
    artículos del hogar.              ← descripción corta del negocio

  local_fisico:
    nombre: "Ferretería Pérez"
    direccion: "Av. España 1234 c/ Brasil"
    ciudad: "Asunción, Paraguay"

  web: www.ferreteriaoperez.com.py   ← sitio web (si no tiene, eliminar la línea)
  telefono: "+595 XXX XXXXXX"
  telefono_comercial: "+595 XXX XXXXXX"
  email: contacto@ferreteriaoperez.com.py

  horario:
    lunes_viernes: "8:00 AM - 6:00 PM"
    sabado: "8:00 AM - 12:00 PM"
    domingo: "Cerrado"

agente:
  nombre: Sofia                      ← nombre que eligió el cliente
  tono: "Amigable, cálido, profesional"
  descripcion: |
    Soy Sofía, tu vendedora de Ferretería Pérez.
    Estoy aquí para ayudarte a encontrar lo que
    necesitás. Podés preguntarme por precios,
    disponibilidad y hacer tu pedido por acá.

pago:
  metodos:
    transferencia:
      banco: "Banco Continental"
      cuenta: "Ferretería Pérez S.A."
      numero_cuenta: "XXXXXXXXXX"
      ruc: "XXXXXXXX-X"
      descripcion: "Transferencia bancaria"

    efectivo:
      tipo: "Pago contra entrega"
      ubicacion: "Local Ferretería Pérez, Av. España 1234"
      descripcion: "Pago en efectivo en nuestro local"

    tarjeta_ueno:                    ← si el cliente tiene este banco
      banco: "UENO BANK"
      cuotas: 12
      interes: "sin intereses"
      metodo: "Link Pagopar"
```

Si el cliente no tiene cuotas, eliminás esas secciones.

Guardás el archivo.

---

## PASO 5 — CONFIGURAR LA PERSONALIDAD DEL AGENTE

### 5.1 Abrir el archivo de prompts

```bash
open -e config/prompts.yaml
```

### 5.2 Editar la primera parte — la presentación

Al inicio del archivo vas a ver la línea que empieza con `system_prompt: |`. Debajo hay texto que empieza con `Soy Belén, vendedora de Rebody...`

Reemplazás esa primera oración por los datos del cliente:

**Antes (Rebody):**
```
Soy Belén, vendedora de Rebody en Paraguay. Vendo WHOOP, JetBoots, Theragun, Foreo y más wellness. Atiendo 24/7 por WhatsApp.
```

**Después (cliente nuevo):**
```
Soy Sofía, vendedora de Ferretería Pérez en Paraguay. Vendo herramientas, materiales de construcción y artículos del hogar. Atiendo 24/7 por WhatsApp.
```

### 5.3 Actualizar el saludo del primer mensaje

Buscás esta línea:
```
Me presento: "Hola, soy Belén, la agente de Rebody 😊"
```

La reemplazás:
```
Me presento: "Hola, soy Sofía, la agente de Ferretería Pérez 😊"
```

### 5.4 Limpiar los datos de productos del cliente anterior

El archivo tiene mucha información específica de Rebody (specs de WHOOP, JetBoots, etc.). Buscás la sección que empieza con:

```
## ESPECIFICACIONES WHOOP — SOLO USAR ESTA INFORMACIÓN, NUNCA INVENTAR
```

Todo eso es específico de Rebody. Lo reemplazás con las especificaciones de los productos del nuevo cliente si tienen datos técnicos importantes que el bot necesita conocer exactamente. Si no tienen specs técnicas complejas, podés borrarlo y dejar solo:

```
## PRODUCTOS
Conocés el catálogo completo del negocio. Ante preguntas específicas de specs que no conozcas, decís: "Eso te lo confirmo 👌" y avisás al equipo.
```

### 5.5 Actualizar el número de escalación

Buscás en el archivo:
```
"Te paso con el equipo: +595 993 233 333 😊"
```

Reemplazás con el número del cliente.

Guardás el archivo.

---

## PASO 6 — CARGAR EL CATÁLOGO DE PRODUCTOS

El catálogo es el corazón del bot — sin esto no sabe qué vender.

### 6.1 Abrir el catálogo ejemplo

```bash
open -e knowledge/catálogo_completo.json
```

Vas a ver la estructura. Cada producto tiene este formato:

```json
{
  "NOMBRE_CLAVE": {
    "nombre": "Nombre del producto como aparece en la tienda",
    "url": "https://www.tiendadelcliente.com/producto",
    "precio": "250.000 Gs",
    "categoria": "Herramientas",
    "especificaciones": [
      "Característica 1",
      "Característica 2"
    ],
    "beneficios": [
      "Para qué sirve",
      "Qué problema resuelve"
    ],
    "como_se_usa": "Descripción breve de uso"
  }
}
```

### 6.2 Reemplazar todo el contenido con los productos del cliente

Borrás todo el contenido del archivo y lo reemplazás con los productos del cliente. Ejemplo real para una ferretería:

```json
{
  "TALADRO_BOSCH": {
    "nombre": "Taladro Bosch 550W",
    "url": "https://ferreteriaoperez.com.py/taladro-bosch-550w",
    "precio": "450.000 Gs",
    "categoria": "Herramientas electricas",
    "especificaciones": [
      "Potencia 550W",
      "Velocidad variable",
      "Empuñadura ergonómica",
      "Incluye 3 brocas"
    ],
    "beneficios": [
      "Ideal para trabajos en el hogar",
      "Liviano y fácil de usar",
      "Garantía 1 año"
    ],
    "como_se_usa": "Enchufar, seleccionar velocidad, presionar gatillo."
  },
  "PINTURA_ALBA_BLANCO": {
    "nombre": "Pintura Alba Interior Blanco 20L",
    "url": "https://ferreteriaoperez.com.py/pintura-alba-20l",
    "precio": "280.000 Gs",
    "categoria": "Pinturas",
    "especificaciones": [
      "Rendimiento: 12m² por litro",
      "Secado: 2 horas",
      "Lavable",
      "Base agua"
    ],
    "beneficios": [
      "Cobertura excelente en una mano",
      "Sin olor fuerte",
      "Resistente a la humedad"
    ],
    "como_se_usa": "Agitar, diluir 10% con agua si es necesario, aplicar con rodillo."
  }
}
```

**Tip**: Si el cliente tiene muchos productos (50+), podés pedirle una lista en Excel y convertirla. O cargás los 10-15 más vendidos primero y agregás el resto después.

### 6.3 Actualizar el stock actual

```bash
open -e knowledge/stock_actual.json
```

Reemplazás con los productos y su disponibilidad actual:

```json
{
  "productos": {
    "taladro_bosch": {
      "nombre": "Taladro Bosch 550W",
      "stock": 8,
      "disponible": true
    },
    "pintura_alba": {
      "nombre": "Pintura Alba Interior Blanco 20L",
      "stock": 0,
      "disponible": false
    }
  },
  "ultima_actualizacion": "2026-05-02"
}
```

### 6.4 (Opcional) Configurar imágenes de productos

```bash
open -e knowledge/imagenes_productos.json
```

Si el cliente quiere que el bot mande fotos de productos, cargás las URLs de las imágenes:

```json
{
  "TALADRO_BOSCH": "https://ferreteriaoperez.com.py/images/taladro-bosch.jpg",
  "PINTURA_ALBA_BLANCO": "https://ferreteriaoperez.com.py/images/pintura-alba.jpg"
}
```

Si no tiene imágenes todavía, dejás el archivo vacío: `{}`

---

## PASO 7 — LIMPIAR LOS DATOS DE REBODY DEL AGENTE

Algunos archivos tienen referencias directas a Rebody que hay que limpiar.

### 7.1 Actualizar el mapeo de anuncios (si el cliente usa Meta Ads)

```bash
open -e config/ads.yaml
```

Si el cliente hace publicidad en Facebook/Instagram, agregás aquí los IDs de sus anuncios. Si no hace publicidad todavía, borrás el contenido y dejás:

```yaml
ad_products: {}
```

### 7.2 Actualizar la imagen de datos bancarios

Abrís el archivo `agent/main.py` en VS Code o el editor de texto. Buscás esta línea (cerca de la línea 85):

```python
IMAGEN_DATOS_BANCARIOS = "https://i.imgur.com/WYPWrdl.png"
```

Reemplazás la URL con la imagen que tiene los datos bancarios del cliente. Para subir la imagen del cliente podés usar [imgbb.com](https://imgbb.com) (gratis, sin cuenta) y copiar el link directo.

---

## PASO 8 — PROBAR QUE TODO FUNCIONA EN TU COMPUTADORA

Antes de subir a Railway, probás localmente.

### 8.1 Instalar dependencias (solo la primera vez por proyecto)

```bash
pip install -r requirements.txt
```

Si da error con pip, probar:
```bash
pip3 install -r requirements.txt
```

### 8.2 Arrancar el bot

```bash
uvicorn agent.main:app --reload --port 8000
```

Vas a ver en la terminal algo como:
```
INFO:     Started server process
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Si no hay errores rojos, el bot está corriendo.

### 8.3 Probar el bot como si fuera un cliente

Abrís otra pestaña de terminal (sin cerrar la anterior) y escribís:

```bash
python tests/test_local.py
```

Se abre un chat interactivo en la terminal. Escribís mensajes como si fueras el cliente:

```
Vos: hola
Bot: Hola, soy Sofía, la agente de Ferretería Pérez 😊 ¿En qué te puedo ayudar?

Vos: tienen taladros?
Bot: ¡Sí! Tenemos el Taladro Bosch 550W a 450.000 Gs...
```

Si las respuestas tienen sentido y mencionan los productos correctos, está todo bien. Apretás `Ctrl + C` para salir.

### 8.4 Apagar el servidor local

En la terminal donde está corriendo el bot, apretás `Ctrl + C`.

---

## PASO 9 — SUBIR A RAILWAY (DEPLOY)

Railway es donde el bot va a vivir 24/7 en internet.

### 9.1 Instalar Railway CLI (solo la primera vez)

```bash
npm install -g @railway/cli
```

Si no tenés Node.js, instalalo desde [nodejs.org](https://nodejs.org) primero.

### 9.2 Loguearte en Railway

```bash
railway login
```

Se abre el browser, confirmás con tu cuenta de Railway.

### 9.3 Crear un nuevo proyecto en Railway para este cliente

```bash
railway init
```

Te pregunta:
- **Project name**: escribís el nombre del cliente (ej: `ferreteria-perez`)
- Te crea el proyecto automáticamente

### 9.4 Configurar el volumen para la base de datos

El bot usa SQLite (base de datos en archivo). Para que los datos no se borren cuando Railway reinicia el servidor, necesitás un volumen persistente.

En el browser, ir a [railway.app](https://railway.app):
1. Abrís tu proyecto recién creado
2. Clic en **"+ Add"** → **"Volume"**
3. En **Mount Path** escribís: `/app/data`
4. Clic en **"Add"**

### 9.5 Subir las variables de entorno a Railway

Copiás cada variable de tu `.env` local y la cargás en Railway. Hay dos formas:

**Opción A (más rápida) — Pegar todo de una vez:**

```bash
railway variables set \
  ANTHROPIC_API_KEY="tu-clave-aqui" \
  WHAPI_TOKEN="token-del-cliente" \
  WHATSAPP_PROVIDER="whapi" \
  ENVIRONMENT="production" \
  DATABASE_URL="sqlite+aiosqlite:////app/data/agentkit.db" \
  VENDEDOR_WHATSAPP="595XXXXXXXXX" \
  ADMIN_PASSWORD="password-del-cliente" \
  ADMIN_WHATSAPP="+595XXXXXXXXX"
```

**Opción B — Desde el dashboard de Railway:**
1. Ir al proyecto en railway.app
2. Clic en tu servicio → pestaña **"Variables"**
3. Clic en **"Raw Editor"**
4. Pegar el contenido de tu `.env` (excepto las líneas comentadas con `#`)

### 9.6 Hacer el deploy

```bash
railway up
```

Railway va a compilar y subir el código. Ves los logs en tiempo real. El proceso tarda 2-4 minutos. Al final ves algo como:

```
✓ Build complete
✓ Deploy complete
Service URL: https://ferreteria-perez-production.up.railway.app
```

**Copiás esa URL** — la necesitás en el siguiente paso.

### 9.7 Verificar que está corriendo

Abrís esa URL en el browser. Vas a ver texto JSON como:
```json
{"status": "ok", "agent": "Sofia", "version": "1.0"}
```

Si ves eso, el bot está vivo en internet.

---

## PASO 10 — CONECTAR WHAPI CON EL BOT

Ahora hay que decirle a Whapi: "cuando llegue un mensaje al WhatsApp del cliente, mandalo a esta URL".

### 10.1 Ir al dashboard de Whapi

Entrar a [whapi.cloud](https://whapi.cloud) → tu canal del cliente.

### 10.2 Configurar el webhook

1. Clic en **"Settings"** o **"Configuración"** del canal
2. Buscás la sección **"Webhook"**
3. En **Webhook URL** pegás la URL de Railway + `/webhook`:
   ```
   https://ferreteria-perez-production.up.railway.app/webhook
   ```
4. En **Events** / **Eventos** marcás: `messages` (mensajes recibidos)
5. Guardás

### 10.3 Probar con WhatsApp real

Desde tu propio celular, mandás un mensaje al WhatsApp del cliente:

```
Hola
```

En 2-3 segundos deberías recibir la respuesta del bot. Si responde correctamente, todo está funcionando.

---

## PASO 11 — ENTREGA AL CLIENTE

### 11.1 Darle acceso al panel de control

El cliente puede ver sus leads, conversaciones y pedidos en el panel de control. La URL es:

```
https://ferreteria-perez-production.up.railway.app/admin
```

Les das:
- La URL del panel
- El password que configuraste en `ADMIN_PASSWORD`

### 11.2 Mostrarle cómo silenciar el bot para responder manualmente

Si el dueño quiere responder él mismo una conversación sin que el bot interfiera, en el panel puede presionar "Silenciar" en esa conversación. El bot no responde mientras está silenciado.

### 11.3 Decirle cómo actualizar stock

Cuando cambia el stock, el cliente te avisa y vos editás `knowledge/stock_actual.json` y hacés un `railway up` para actualizar. O si querés, le enseñás a editar el archivo directamente.

---

## RESUMEN RÁPIDO — Cada vez que arranca un cliente nuevo

```
1. cp -r ~/whatsapp-agentkit nombre-cliente-bot
2. cd nombre-cliente-bot
3. rm -f agentkit.db agentkit_memory.log
4. cp .env.example .env  → completar valores
5. Conectar número en Whapi → copiar token al .env
6. Editar config/business.yaml → datos del negocio
7. Editar config/prompts.yaml → nombre agente, saludo, escalación
8. Editar knowledge/catálogo_completo.json → productos
9. Editar knowledge/stock_actual.json → stock inicial
10. Editar agent/main.py línea 85 → imagen datos bancarios
11. python tests/test_local.py → probar localmente
12. railway init → crear proyecto Railway
13. Crear volumen /app/data en Railway dashboard
14. railway variables set → cargar .env en Railway
15. railway up → deploy
16. Whapi → configurar webhook con la URL de Railway
17. Test con WhatsApp real → mandar "hola"
18. Entregar URL del panel al cliente
```

---

## SOLUCIÓN DE PROBLEMAS FRECUENTES

### El bot no responde en WhatsApp

1. Verificar que el webhook está configurado en Whapi con la URL correcta
2. Ir a Railway → Logs → buscar si hay errores rojos
3. Verificar que `WHAPI_TOKEN` es el correcto en las variables de Railway

### El bot responde cosas de Rebody en vez del cliente

Revisaste el `config/prompts.yaml` y el `config/business.yaml`? Probablemente quedó texto de Rebody. Editás, guardás, y hacés `railway up` de nuevo.

### El bot responde "no tengo ese producto"

El catálogo no está cargado correctamente. Revisás `knowledge/catálogo_completo.json` y verificás que el JSON sea válido (sin comas faltantes). Para validar el JSON: [jsonlint.com](https://jsonlint.com).

### El deploy de Railway falla

Revisás los logs del build en Railway. El error más común es que falta alguna variable de entorno. Verificás que todas las variables del `.env` estén cargadas en Railway.

### Perdí los datos (conversaciones, leads)

Si configuraste el volumen persistente en el Paso 9.4, los datos están seguros. Si no lo configuraste, los datos se perdieron con el reinicio. Configurar el volumen antes de continuar.

### El cliente me dice que el bot "se desconectó"

Whapi cierra la sesión si el celular del cliente no tiene internet por mucho tiempo, o si alguien cerró la sesión desde el celular. Hay que reconectar escaneando QR de nuevo en Whapi.

---

## MANTENIMIENTO MENSUAL

Lo que hacés cada mes para cada cliente:

| Tarea | Tiempo | Cuándo |
|---|---|---|
| Actualizar stock | 10-15 min | Cuando el cliente avisa cambios |
| Agregar productos nuevos al catálogo | 20-30 min | Cuando agregan productos |
| Revisar logs en Railway por errores | 5 min | Cada 2 semanas |
| Verificar que el número de Whapi sigue activo | 2 min | Mensual |
| Reunión de revisión de métricas (Tier 3) | 30 min | Mensual |

---

*Guía creada Mayo 2026 — Para uso interno.*
