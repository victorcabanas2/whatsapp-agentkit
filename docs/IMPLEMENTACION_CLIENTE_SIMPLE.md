# AgentKit — De cero a bot funcionando
**Guía para implementar un nuevo cliente**
Tiempo estimado: 30-60 minutos

---

## 01 — Qué es esto

Un agente de ventas para WhatsApp que responde como un vendedor humano. Lo configurás una vez para cada cliente y queda funcionando 24/7 en la nube.

Casos de uso típicos:
- Ferretería que pierde clientes fuera de horario
- Tienda online que no puede responder 100 consultas por día
- Distribuidora que quiere seguimiento automático de leads

---

## 02 — Requisitos

Necesitás tener estas cuentas (se crean una sola vez, sirven para todos los clientes):

| Cuenta | Link | Para qué |
|---|---|---|
| Anthropic | console.anthropic.com | La IA que piensa |
| Railway | railway.app | El servidor en la nube |
| Whapi | whapi.cloud | Conectar el WhatsApp del cliente |

Y del cliente necesitás:
- El número de WhatsApp del negocio (que no lo usen personal)
- Lista de productos con nombre, precio y descripción
- Datos de pago (cuenta bancaria, métodos que aceptan)

---

## 03 — Instalación

Abrís la terminal y corrés los 3 comandos:

**Copiar el proyecto base con el nombre del cliente:**
```bash
cp -r ~/whatsapp-agentkit ~/clientes/nombre-del-cliente
cd ~/clientes/nombre-del-cliente
```

**Instalar dependencias** (solo la primera vez por computadora):
```bash
pip install -r requirements.txt
```

**Correr el script de configuración:**
```bash
python scripts/setup_nuevo_cliente.py
```

---

## 04 — La entrevista

El script te hace preguntas y genera todos los archivos de configuración automáticamente. Son 5 bloques:

```
1 / 5 — El negocio
  Nombre del negocio: Ferretería Pérez
  Qué vende: herramientas, pinturas, materiales de construcción
  Ciudad [Asunción, Paraguay]: 
  Dirección física: Av. España 1234 c/ Brasil
  Sitio web: www.ferreteriaoperez.com.py
  Teléfono: +595 XXX XXXXXX
  Horario lunes a viernes [9:00 AM - 6:00 PM]: 
  Horario sábado [Cerrado]: 8:00 AM - 12:00 PM

2 / 5 — El agente IA
  Nombre del agente: Sofía
  Tono [Amigable, cálido y profesional]: 
  Qué puede hacer el agente: Responder preguntas y tomar pedidos

3 / 5 — Métodos de pago
  Banco para transferencias: Continental
  Número de cuenta: XXXXXXXXXX
  Cuotas sin interés: UENO 12 cuotas

4 / 5 — Credenciales
  ANTHROPIC_API_KEY: sk-ant-...
  WHAPI_TOKEN: TKN_...
  Password para panel de control: *****

5 / 5 — Confirmación
  ¿Todo correcto? (s/n): s
```

Al terminar, el script crea automáticamente:
- `.env` — todas las credenciales
- `config/business.yaml` — datos del negocio
- `config/prompts.yaml` — personalidad del agente (nombre, saludo, escalación)
- Archivos de knowledge reseteados y listos para cargar

---

## 05 — El catálogo

Esta es la única parte manual. Abrís el archivo y reemplazás el ejemplo con los productos reales del cliente.

```bash
open -e knowledge/catálogo_completo.json
```

El formato de cada producto es:

```json
{
  "TALADRO_BOSCH_550W": {
    "nombre": "Taladro Bosch 550W",
    "url": "https://ferreteriaoperez.com.py/taladro-bosch",
    "precio": "450.000 Gs",
    "categoria": "Herramientas eléctricas",
    "especificaciones": [
      "Potencia 550W",
      "Velocidad variable",
      "Incluye 3 brocas"
    ],
    "beneficios": [
      "Ideal para trabajos en el hogar",
      "Garantía 1 año"
    ]
  }
}
```

Repetís ese bloque para cada producto. Si el cliente tiene muchos productos, cargás los 10-15 más vendidos primero.

Cuando termines, validá que el JSON está bien formado en [jsonlint.com](https://jsonlint.com).

---

## 06 — Conectar WhatsApp

Antes de desplegar, conectás el número del cliente en Whapi.

1. Ir a [whapi.cloud](https://whapi.cloud) → New Channel
2. Ponerle nombre al canal (solo para tu organización)
3. El cliente abre su WhatsApp → Ajustes → Dispositivos vinculados → Escanear QR
4. Copiar el token que aparece en Whapi
5. Ese token ya está en tu `.env` si lo pusiste en la entrevista. Si no, editarlo:

```bash
open -e .env
# Pegar el token en: WHAPI_TOKEN=TKN_xxxxxxxxxxxxx
```

---

## 07 — Prueba local

Antes de publicar, probás que el bot responde bien.

```bash
uvicorn agent.main:app --reload --port 8000
```

En otra terminal:

```bash
python tests/test_local.py
```

Escribís mensajes como si fueras el cliente. Si el agente responde con los datos correctos del negocio y conoce los productos, está listo.

Para cerrar: `Ctrl + C` en ambas terminales.

---

## 08 — Deploy en Railway

Publicás el bot en la nube para que corra 24/7.

**Instalar Railway CLI** (solo la primera vez):
```bash
npm install -g @railway/cli
railway login
```

**Crear el proyecto del cliente en Railway:**
```bash
railway init
```
Nombre del proyecto: nombre-del-cliente (ej: `ferreteria-perez`)

**Crear volumen para la base de datos** (en el browser):
1. Ir al proyecto en railway.app
2. Click en + Add → Volume
3. Mount Path: `/app/data`
4. Click Add

**Subir las variables de entorno:**
```bash
railway variables set --from .env
```

**Publicar:**
```bash
railway up
```

Al terminar ves la URL del bot. Algo como:
```
https://ferreteria-perez-production.up.railway.app
```

Confirmás que está vivo abriendo esa URL en el browser. Tenés que ver:
```json
{"status": "ok"}
```

---

## 09 — Conectar el webhook

Le decís a Whapi que mande los mensajes de WhatsApp a tu bot.

1. Ir a [whapi.cloud](https://whapi.cloud) → tu canal → Settings
2. En Webhook URL pegar:
```
https://nombre-del-cliente-production.up.railway.app/webhook
```
3. En Events marcar: `messages`
4. Guardar

**Test final**: Mandá un mensaje al WhatsApp del cliente desde tu celular. En 2-3 segundos el bot responde. Si responde, está todo listo.

---

## 10 — Entrega al cliente

Le das dos cosas:

**URL del panel de control:**
```
https://nombre-del-cliente-production.up.railway.app/admin
```

**Password**: el que pusiste en la entrevista.

Desde el panel pueden ver leads, conversaciones y pedidos. También pueden silenciar el bot cuando quieren responder ellos mismos.

---

## FAQs

**¿El bot suena a robot?**
No. Usa Claude de Anthropic — la misma IA que ChatGPT pero de Anthropic. Responde en el dialecto del país, recuerda el contexto de la conversación, y maneja preguntas libres.

**¿El dueño puede seguir usando su WhatsApp normalmente?**
Sí. Whapi conecta el número sin bloquear el uso normal del celular. El bot y el dueño pueden coexistir en el mismo número.

**¿Qué pasa si el cliente actualiza precios?**
Editás `knowledge/catálogo_completo.json` y corrés `railway up` de nuevo. Toma 3 minutos.

**¿Cuánto cuesta por mes al cliente?**
La infraestructura real cuesta entre $20-60 USD/mes dependiendo del volumen. El resto es tu margen.

**¿Funciona para cualquier negocio?**
Para cualquiera que venda productos o servicios con precio definido y reciba consultas por WhatsApp. No funciona bien para servicios con cotización muy personalizada o procesos de venta muy largos.

**¿Puedo tener múltiples clientes en el mismo Railway?**
Sí. Cada cliente es un proyecto Railway separado. El costo de Railway se divide entre proyectos activos.

**¿El bot aprende con el tiempo?**
No aprende solo, pero vos podés mejorarlo: editar el catálogo, agregar FAQs al prompt, ajustar la personalidad. Cada cambio toma minutos.
