# AgentKit — Paquete Comercial Completo
**Agente de ventas por WhatsApp con IA**
Versión 1.0 — Mayo 2026

---

## RESUMEN EJECUTIVO

AgentKit es un agente de ventas autónomo que opera por WhatsApp las 24 horas. Responde consultas, recomienda productos, envía imágenes, hace seguimientos automáticos y nunca pierde un lead. No es un chatbot de respuestas predefinidas: usa inteligencia artificial real (Claude de Anthropic) para responder como lo haría un vendedor humano capacitado.

**Problema que resuelve**: Negocios que reciben consultas por WhatsApp fuera de horario, pierden leads por falta de seguimiento, o no tienen personal dedicado a responder mensajes.

**Para quién funciona**: Cualquier negocio que venda productos o servicios con precio definido y volumen de consultas por WhatsApp. Comercios, distribuidores, tiendas online, servicios con catálogo.

**Para quién NO funciona bien**: Servicios muy customizados sin precio fijo, negocios con procesos de venta que requieren reuniones presenciales largas, o donde el cliente necesita hablar siempre con una persona.

---

## PARTE 1: AUDITORÍA DE CAPACIDADES

### Lo que el bot hace en producción (implementado y probado)

#### Comunicacion con el cliente
- Recibe y responde mensajes de texto por WhatsApp
- Recibe y analiza imágenes que manda el cliente (identifica producto, responde preguntas sobre foto)
- Agrupa mensajes rápidos del mismo cliente (espera 10 segundos antes de responder para que el cliente termine de escribir, evita responder a medias)

#### Inteligencia de ventas
- Responde con personalidad y nombre propios (configurables por cliente)
- Conoce el catálogo completo con precios, specs y diferencias entre modelos
- Detecta cuándo el cliente viene de un anuncio de Meta y sabe de qué producto hablar
- Identifica el producto aunque el cliente lo llame de forma diferente ("bota", "pistola", "pulsera", etc.)
- Detecta intención de compra ("quiero comprarlo", "cómo pago", "dale") y marca el lead como caliente
- Detecta objeciones de precio y responde con opciones de cuotas
- Muestra familia de productos cuando el cliente no especifica modelo (sin empujar uno)
- Responde FAQs frecuentes (dirección, datos bancarios, cuotas) sin consumir tokens de IA (más rápido y más barato)

#### Seguimiento automático
- Envía hasta 3 seguimientos automáticos por lead (3 horas, 20-24 horas, 3 días) usando IA para decidir QUÉ decir y SI enviarlo
- NO envía seguimiento si el cliente dijo "te aviso yo" o "cuando llegue stock avísame" (IA detecta el contexto)
- Envía seguimientos dominicales con promos a carritos abandonados
- Encuesta de satisfacción automática 2 horas después de una venta
- Seguimiento puntual: si el cliente dice "escríbeme en 4 minutos", el bot lo hace exactamente

#### Administración
- Panel de control web para el dueño del negocio (ver leads, conversaciones, pedidos)
- El admin puede tomar control de una conversación y el bot se silencia mientras habla un humano
- Lead scoring automático (caliente / tibio / frío / objeción)
- Auditoría completa de todo lo que pasa en el sistema
- Historial completo de conversaciones por cliente
- Vinculación automática de leads a anuncios de Meta (atribución de fuente)

#### Stock e inventario
- Muestra stock en tiempo real en cada respuesta (actualizado desde archivo)
- Integración con Shopify para sincronizar stock automáticamente
- Cuando un producto está agotado, lo dice y ofrece alternativa disponible

---

### Lo que se configura por cliente (sin tocar código)

Todo lo que sigue se cambia editando archivos YAML — no requiere programar:

| Elemento | Archivo | Ejemplo |
|---|---|---|
| Nombre y personalidad del agente | `config/prompts.yaml` | "Sofía", "Lucas", tono formal/casual |
| Información del negocio | `config/business.yaml` | Nombre, dirección, horarios, teléfono |
| Métodos de pago | `config/business.yaml` | Bancos, cuotas, links de pago |
| Mapeo de anuncios | `config/ads.yaml` | ID anuncio → nombre de producto |
| Catálogo de productos | `knowledge/catálogo_completo.json` | Productos, precios, specs, links |
| Stock actual | `knowledge/stock_actual.json` | Disponibilidad en tiempo real |
| Imágenes de productos | `knowledge/imagenes_productos.json` | URLs de fotos por producto |
| Imagen de datos bancarios | Variable en `agent/main.py` | URL de imagen con info de transferencia |

---

### Límites actuales (importante ser honesto con el cliente)

- Solo WhatsApp (no Instagram DM, no Messenger en este stack)
- No procesa pedidos de voz (audio)
- No hace cobros automáticos ni integración de pagos en tiempo real
- No multi-idioma en el mismo agente (uno por idioma)
- El admin panel es web básico, no mobile-native
- No integra con CRMs externos (Hubspot, Salesforce) sin desarrollo adicional

---

## PARTE 2: COSTOS REALES DE INFRAESTRUCTURA

### Costos fijos por cliente (mensual)

| Servicio | Costo estimado | Para qué sirve |
|---|---|---|
| Whapi.cloud (plan mensajería) | $10–25 USD | Conectar el número de WhatsApp del cliente a la API |
| Railway (hosting del bot) | $5–15 USD | Servidor donde corre el bot (puede compartirse entre 3-5 clientes) |
| Anthropic API (Claude) | $3–25 USD | La inteligencia artificial (varía por volumen de mensajes) |
| **Total infraestructura** | **$18–65 USD** | Depende del volumen de mensajes |

### Estimado de costos de IA por volumen

| Mensajes diarios | Costo Anthropic/mes | Perfil de negocio |
|---|---|---|
| 50–100 | $2–5 | Tienda pequeña, consultas esporádicas |
| 100–300 | $5–12 | Comercio activo con publicidad |
| 300–700 | $12–30 | Distribuidora o tienda con volumen |
| 700+ | $30+ | Requiere plan paid de Anthropic |

**Nota sobre cacheo**: El sistema usa prompt caching de Anthropic — el prompt principal (el más caro) se cachea y cuesta 90% menos en lecturas repetidas. Esto reduce el costo real de IA en ~50-70% vs un sistema sin cache.

### Costos de tu tiempo por cliente (estimado)

| Tarea | Tiempo estimado |
|---|---|
| Setup inicial nuevo cliente | 8–20 horas |
| Mantenimiento mensual (ajustes, soporte) | 1–3 horas/mes |
| Ajuste de catálogo / precios | 0.5–1 hora por actualización |

---

## PARTE 3: TIERS DE SERVICIO

### Modelo recomendado: Tú gestionas todo (Managed Service)

Es más rentable a largo plazo porque:
- Controlas la calidad y el cliente no puede romper nada
- Acumulás clientes sobre la misma infraestructura (Railway compartido)
- Podes vender el mantenimiento como servicio recurrente
- La escalación de clientes te da economías de escala reales

**Cuándo ofrecer DIY**: Solo cuando el cliente tiene un equipo técnico, presupuesto más alto, y quiere control total. Precio premium por el código + guía.

---

### Tier 1 — "Starter" (Solo consultas)

**Precio**: $200 USD setup + $79 USD/mes

**Qué incluye**:
- Agente con nombre y personalidad propia del negocio
- Responde preguntas de catálogo, precios, stock
- FAQs pre-escritas (dirección, horarios, métodos de pago)
- Saludo automático y primer contacto inteligente
- Historial de conversaciones (hasta 8 mensajes de contexto)
- Sin seguimientos automáticos
- Sin imágenes
- Hasta 150 mensajes/día

**Para quién**: Negocios que quieren empezar, con volumen bajo, que principalmente necesitan que alguien responda fuera de horario.

**Tu costo real**: ~$20–30 USD/mes infraestructura
**Tu margen**: ~$49–59 USD/mes

---

### Tier 2 — "Pro" (Vendedora completa)

**Precio**: $350 USD setup + $129 USD/mes

**Qué incluye todo lo de Starter más**:
- Envío de imágenes de productos automático
- Recepción y análisis de imágenes del cliente
- Seguimiento automático 3 pasos (con IA que decide si enviar y qué decir)
- Detección de intención de compra y lead scoring
- Admin puede tomar control de conversaciones (modo silencio)
- Panel de control web para ver leads y conversaciones
- Envío de datos bancarios automático al confirmar pago
- Hasta 400 mensajes/día

**Para quién**: La mayoría de los clientes que venden productos con catálogo definido y quieren que el bot cierre ventas, no solo responda.

**Tu costo real**: ~$30–50 USD/mes infraestructura
**Tu margen**: ~$79–99 USD/mes

---

### Tier 3 — "Business" (Operacion completa)

**Precio**: $500 USD setup + $199 USD/mes

**Qué incluye todo lo de Pro más**:
- Atribución de anuncios Meta (sabe de qué anuncio viene cada lead)
- Seguimientos dominicales con promos y carritos abandonados
- Encuesta de satisfacción post-venta automática
- Seguimientos programados por el cliente ("escríbeme en 4 minutos")
- Sincronización de stock con Shopify (si el cliente tiene Shopify)
- Hasta 1000 mensajes/día
- 1 reunión mensual de revisión de métricas (30 min)

**Para quién**: Negocios con publicidad activa en Meta, volumen de leads alto, y que quieren el sistema de ventas más completo.

**Tu costo real**: ~$45–80 USD/mes infraestructura
**Tu margen**: ~$119–154 USD/mes

---

### Tier 4 — "Enterprise / Codigo" (DIY o Agencia)

**Precio**: $1,500–3,000 USD único (sin mensualidad de ti, ellos pagan su propia infra)

**Qué incluye**:
- Código fuente completo del proyecto
- 2 sesiones de setup asistido (4 horas total)
- Documentación de configuración
- Soporte por 30 días post-entrega
- Ellos pagan directamente Whapi, Railway, Anthropic

**Para quién**: Agencias de marketing que quieren revender, o empresas con equipo técnico propio.

**Cuándo ofrecerlo**: Cuando el cliente pide el código explícitamente, o cuando el volumen es tan alto que el managed service no les conviene financieramente.

---

### Tabla comparativa de tiers

| Funcionalidad | Starter | Pro | Business | Enterprise |
|---|:---:|:---:|:---:|:---:|
| Responde consultas 24/7 | Si | Si | Si | Si |
| Personalidad configurable | Si | Si | Si | Si |
| FAQs pre-escritas | Si | Si | Si | Si |
| Envio de imagenes | No | Si | Si | Si |
| Recibe imágenes del cliente | No | Si | Si | Si |
| Seguimiento 3 pasos con IA | No | Si | Si | Si |
| Lead scoring | No | Si | Si | Si |
| Admin toma control | No | Si | Si | Si |
| Panel de control web | No | Si | Si | Si |
| Atribucion anuncios Meta | No | No | Si | Si |
| Carritos abandonados | No | No | Si | Si |
| Encuesta post-venta | No | No | Si | Si |
| Sync Shopify stock | No | No | Si | Si |
| Seguimiento dinamico cliente | No | No | Si | Si |
| Código fuente | No | No | No | Si |
| Precio setup | $200 | $350 | $500 | $1,500+ |
| Precio mensual | $79 | $129 | $199 | $0 (ellos pagan infra) |

---

## PARTE 4: CUESTIONARIO DE ONBOARDING

Usar en la primera reunión con el cliente (dura 30-60 minutos). Las respuestas de estas preguntas son todo lo que necesitás para configurar el bot.

### Bloque 1: El negocio

1. ¿Cuál es el nombre de tu empresa/negocio?
2. ¿Qué vendés exactamente? (productos, servicios, ambos)
3. ¿Tienen local físico, solo online, o ambos?
4. ¿Cuál es su dirección y horario de atención?
5. ¿Cuál es su sitio web o link de tienda online?

### Bloque 2: El cliente y el volumen

6. ¿Cuántos mensajes de WhatsApp reciben por día aproximadamente hoy?
7. ¿En qué horarios llegan la mayoría de consultas?
8. ¿Cuáles son las 5 preguntas que más te hacen los clientes?
9. ¿Tienen clientes que compran frecuentemente o es mayormente primera vez?

### Bloque 3: El catálogo

10. ¿Cuántos productos/servicios tienen? (número aproximado)
11. ¿Tienen los precios de venta definidos y actualizados?
12. ¿Tienen imágenes de sus productos disponibles (link web o fotos)?
13. ¿El precio varía por cliente, zona, o volumen? (Si sí, ¿cómo?)
14. ¿Con qué frecuencia cambian precios o agregan productos?

### Bloque 4: Pagos

15. ¿Qué métodos de pago aceptan? (transferencia, efectivo, tarjeta, cuotas)
16. ¿Con qué bancos tienen acuerdo de cuotas sin interés?
17. ¿Tienen un número de cuenta o alias para transferencias?
18. ¿Mandan un comprobante o imagen con los datos de pago?

### Bloque 5: Publicidad y fuentes de leads

19. ¿Hacen publicidad en Meta (Facebook/Instagram)? (Importante para Tier 3)
20. ¿De dónde vienen la mayoría de sus clientes hoy? (Instagram, referidos, Google, etc.)
21. ¿Tienen el número de WhatsApp al que van a conectar el bot definido?

### Bloque 6: El equipo

22. ¿Hay alguien que hoy responde los mensajes de WhatsApp? ¿Cuánto tiempo le dedica?
23. ¿Quién va a usar el panel de control para ver leads y conversaciones?
24. ¿Quién va a ser el escalation contact cuando el bot no pueda resolver algo?
25. ¿Tienen integración con algún sistema que quieran conectar? (Shopify, MercadoLibre, etc.)

### Bloque 7: Preferencias del agente

26. ¿Quieren que el agente tenga nombre propio? ¿Cuál?
27. ¿Prefieren tono formal ("usted") o informal ("vos/tú")?
28. ¿Hay algo que el bot NUNCA debería decir o prometer?
29. ¿Hay algún producto o servicio que prefieren que el bot no mencione?

---

## PARTE 5: PROCESO DE IMPLEMENTACIÓN

### Timeline por tier

**Tier 1 (Starter)** — 3 días hábiles

| Dia | Tarea | Tiempo |
|---|---|---|
| 1 | Reunión onboarding + recolectar materiales | 1.5h |
| 1 | Configurar `business.yaml` y `prompts.yaml` | 1h |
| 2 | Cargar catálogo en JSON + FAQs pre-escritas | 2h |
| 2 | Test local con conversaciones simuladas | 1h |
| 3 | Deploy Railway + conectar Whapi + test real | 1.5h |
| 3 | Entrega y capacitación del cliente (30 min) | 0.5h |
| **Total** | | **~7.5h** |

**Tier 2 (Pro)** — 4 días hábiles

| Dia | Tarea | Tiempo |
|---|---|---|
| 1-2 | Todo lo de Tier 1 | ~7.5h |
| 2 | Configurar imágenes de productos en JSON | 1h |
| 3 | Ajustar seguimientos (reglas de cuándo enviar) | 1h |
| 3 | Test de seguimientos automáticos | 1h |
| 4 | Ajuste fino de respuestas + edge cases | 1.5h |
| **Total** | | **~12h** |

**Tier 3 (Business)** — 5 días hábiles

| Dia | Tarea | Tiempo |
|---|---|---|
| 1-4 | Todo lo de Tier 2 | ~12h |
| 4 | Configurar mapeo de anuncios Meta | 1h |
| 5 | Test flujo completo con anuncios reales | 1.5h |
| 5 | Configurar Shopify sync (si aplica) | 1h |
| 5 | Documentar para el cliente cómo actualizar catálogo | 0.5h |
| **Total** | | **~16h** |

---

### Checklist de materiales a pedir al cliente antes de empezar

Antes de tocar nada, pedirle que te mande todo esto:

- [ ] Número de WhatsApp del negocio (que no estén usando para mensajes personales)
- [ ] Logo de la empresa (para panel de control)
- [ ] Lista de productos con: nombre, precio, descripción corta, link web si tiene
- [ ] Imágenes de los productos (mínimo una por producto)
- [ ] Imagen de datos de pago (con cuenta bancaria, si usan transferencias)
- [ ] Lista de preguntas frecuentes que reciben y las respuestas correctas
- [ ] Datos del negocio: nombre legal, dirección, horarios, métodos de pago

Sin estos materiales no se puede empezar. Si el cliente no los tiene listos, el timeline se corre.

---

## PARTE 6: ESCALABILIDAD Y UPGRADES

### Escalas disponibles (lo que se puede agregar después)

Estos son módulos que podés cobrar como add-ons o upgrades de tier:

| Add-on | Descripcion | Precio sugerido |
|---|---|---|
| Integracion Shopify stock | Sync automático de inventario | +$30/mes o incluir en Tier 3 |
| Instagram DM | Mismo bot en Instagram (requiere otro stack) | Cotizar por separado |
| Envio masivo (campanas) | Mensajes a lista de clientes | +$29/mes (requiere Whapi Enterprise) |
| Panel CRM avanzado | React dashboard con métricas de ventas | +$50/mes o desarrollo pago |
| Multi-idioma | Bot que responde en inglés y español | +$49/mes (segundo agente) |
| Integracion Google Calendar | Agendar reuniones o demostraciones | Desarrollo custom |
| Pasarela de pago | Link de pago automático (MercadoPago, Stripe) | Desarrollo custom |

### Migración entre tiers

Un cliente puede empezar en Starter y subir a Pro o Business en cualquier momento. La migración técnica toma menos de 1 hora (ya tienen la base configurada). Cobrás la diferencia de setup:

- Starter → Pro: $150 USD de migración
- Starter → Business: $300 USD de migración
- Pro → Business: $150 USD de migración

---

## PARTE 7: ARGUMENTOS DE VENTA

### Para cerrar el cliente

**El argumento principal (ROI)**:
"¿Cuánto te cuesta tener a alguien respondiendo WhatsApp 8 horas al día? Con el bot, tenés cobertura 24/7 por menos de lo que cuesta un vendedor part-time, y nunca pierde un lead por estar ocupado o dormido."

**Para el dueño que dice 'lo respondo yo solo'**:
"¿Cuántas veces dijiste 'le respondo después' y ese cliente ya compró en otro lado? El bot responde en segundos a las 2 de la mañana. Vos respondés lo que realmente necesita atención humana."

**Para el que dice 'es caro'**:
"Si el bot cierra una sola venta por mes que antes perdías, ya pagó el servicio. ¿Cuánto vale tu producto promedio?" [Calcular juntos el punto de equilibrio].

**Para el que pregunta si 'suena a robot'**:
"El bot tiene nombre propio, habla como hablaría un vendedor de tu negocio, y usa el dialecto de tu zona. La mayoría de los clientes no saben que están hablando con IA — y no lo descubren porque la experiencia es buena."

---

### Lo que diferencia esto de otros chatbots

| Chatbot tradicional | AgentKit |
|---|---|
| Respuestas pre-definidas en árboles de decisión | IA real que entiende preguntas libres |
| Se cae si el cliente escribe diferente | Maneja variaciones, errores y coloquialismos |
| No aprende contexto de la conversación | Recuerda todo lo que se habló en la sesión |
| No hace seguimiento | 3 seguimientos automáticos inteligentes |
| El admin no puede intervenir | Admin puede tomar control en cualquier momento |
| Requiere semanas de entrenamiento | Configurado en días con los materiales del cliente |

---

## PARTE 8: OFERTA PARA AGENCIAS Y REVENDEDORES

Si querés vender esto como agencia a tus propios clientes:

**Modelo white-label**: El bot lleva el nombre que vos elijas (no "AgentKit"), el agente tiene el nombre del negocio del cliente, y vos sos el proveedor.

**Precio de reventa**: Comprás el código base (Tier Enterprise, $1,500–3,000) y desplegás instancias propias para cada cliente, cobrando tus propios precios. Tu margen es todo lo que cargues por encima de los costos de infraestructura.

**Modelo de agencia referido**: Si no querés gestionar tú mismo la parte técnica, enviás los clientes y te llevás una comisión del setup (15-25% del precio de setup).

---

## APENDICE: STACK TECNICO (para conversaciones técnicas)

Si el cliente tiene un equipo técnico y pregunta:

- **Lenguaje**: Python 3.11
- **Framework**: FastAPI + Uvicorn
- **IA**: Claude Sonnet 4.6 (Anthropic) con prompt caching activado
- **WhatsApp**: Whapi.cloud (API comercial de WhatsApp)
- **Base de datos**: SQLite en producción simple, migrable a PostgreSQL
- **Hosting**: Railway (Docker)
- **Integraciones**: Shopify Storefront API, Meta Ads API
- **Configuración**: YAML files (sin tocar código Python para ajustes normales)
- **Tiempo de respuesta**: 1-3 segundos por mensaje (incluyendo llamada a Claude)

---

*Documento generado en Mayo 2026. Costos de infraestructura sujetos a cambios de proveedores (Whapi, Anthropic, Railway).*
