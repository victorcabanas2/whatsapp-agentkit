# 📢 Configurar Anuncios de Facebook/Instagram con Belén

Cuando alguien clickea un CTA/botón en un anuncio de Facebook o Instagram, ahora Belén sabe automáticamente sobre qué producto se trata y responde directamente sin hacer preguntas innecesarias.

---

## ¿Cómo Funciona?

### SIN configurar payload:
```
Anuncio: "Theragun Mini 3.0 - Descubre más"
Cliente: Clickea botón
Bot recibe: "Descubre más"
Bot pregunta: "¿Qué producto te interesa?" ❌
```

### CON configurar payload (recomendado):
```
Anuncio: "Theragun Mini 3.0 - Descubre más"
Cliente: Clickea botón
Bot recibe: "[Vino desde anuncio de: theragun_mini] Descubre más"
Bot responde: "Hola! El Theragun Mini 3.0 es el más compacto..." ✅
```

---

## Paso a Paso: Configurar en Facebook Ads Manager

### 1. Ve a **Ads Manager** → **Crear Campaña**

Elige objetivo: **Mensajes** (Messages)

### 2. En **Configuración de Anuncio**:

Busca la sección de **Botón de CTA** (Call to Action)

- **Tipo de botón**: "Enviar mensaje" (Send Message)
- **Texto del botón**: Ej: "Consultar precio" o "Quiero Info"

### 3. **IMPORTANTE - Agregar Mensaje Personalizado**:

En el campo de **Mensaje Inicial** o **Contexto del Mensaje**, debes especificar el payload del producto.

**Si tu proveedor es Whapi.cloud:**

Usa este formato en el CTA:

```
Payload: theragun_mini
```

O si Whapi.cloud permite parámetros:

```
?product=theragun_mini
```

### 4. Productos y sus Payloads (usa estos nombres)

Copia exactamente estos nombres para que Claude sepa de qué habla:

**Masajeadores:**
- `theragun_mini` → Theragun Mini 3.0
- `theragun_sense` → Theragun Sense
- `theragun_pro_plus` → Theragun PRO PLUS
- `wavesolo` → WaveSolo

**Botas de Compresión:**
- `jetboots_prime` → RecoveryAir JetBoots Prime
- `jetboots_pro_plus` → Jetboots Pro Plus

**Cuidado Facial:**
- `theraface_depuffing_wand` → TheraFace Depuffing Wand
- `theraface_pro` → TheraFace PRO
- `theraface_mask` → TheraFace Mask

**Wearables:**
- `smartgoggles` → SmartGoggles 2.0
- `whoop_peak` → WHOOP Peak 5.0
- `whoop_one` → WHOOP One 5.0
- `whoop_life_mg` → WHOOP Life MG
- `foreo_faq_221` → FOREO FAQ 221
- `foreo_faq_211` → FOREO FAQ 211

---

## Método 1: Via Facebook Ads Manager (si Meta lo soporta)

1. En el anuncio, busca la opción de **URL de Callback** o **Webhook Params**
2. Agrega: `?product=theragun_mini`
3. Whapi.cloud recibirá esto como payload

**Nota**: Facebook ha limitado esto en versiones recientes. Si no aparece la opción, usa el Método 2.

---

## Método 2: Via Whapi.cloud Dashboard (RECOMENDADO)

1. Ve a **whapi.cloud** → Dashboard
2. En **Integraciones**, busca **Meta** o **Facebook**
3. Si existe opción de **Custom Fields**, agrega:
   ```
   product: theragun_mini
   ```
4. Cada vez que alguien clickea un CTA, Whapi pasará este valor al bot

---

## Método 3: Manual - Editar en Facebook Ads Manager

Si quieres que Whapi.cloud reciba el payload automáticamente:

1. En **Ads Manager**, ve a **Anuncio** → **Crear Campaña**
2. En **Públicos** y **Ubicaciones**, antes de crear el anuncio:
3. Edita el **Texto del Botón CTA**:

   ```
   Botón: "¿Cuánto cuesta?"
   URL Destino: https://wa.me/595991234567?text=Viendo%20anuncio%20de%20theragun_mini
   ```

   (Whapi.cloud reconocerá el parámetro en la URL)

---

## Verificar que Funciona

### Test Local:

1. Para probar sin anuncio real, ejecuta:

```bash
python tests/test_local.py
```

2. Escribe:
```
[Vino desde anuncio de: theragun_mini] Hola
```

3. El bot debería responder:
```
"Hola! El Theragun Mini 3.0 es increíble... [info del producto]"
```

### Test en Producción:

1. Publica un anuncio con payload configurado
2. Clickea desde tu teléfono personal
3. El bot responde directamente sobre el producto ✅

---

## Solución de Problemas

### ❌ El bot pregunta "¿Qué producto te interesa?"

**Significa**: El payload NO se pasó correctamente.

**Soluciones**:
- Verifica que usaste exactamente el nombre del producto (ej: `theragun_mini`, no `theragun-mini`)
- Confirma que el CTA está conectado a Whapi.cloud
- Revisa los logs en Railway: `railway logs --follow`

### ❌ El bot responde sobre producto incorrecto

**Significa**: El payload fue incorrecto.

**Solución**: Usa la lista de payloads arriba exactamente como está.

### ✅ El bot responde correctamente

Perfecto! Ya está configurado. Ahora todo anuncio de producto resultará en una conversación fluida sin preguntas innecesarias.

---

## Tips

1. **Usa payloads en MINÚSCULAS con GUIONES**: `theragun_mini` ✅, no `Theragun Mini` ❌
2. **Cada producto debe tener su propio anuncio con payload diferente**
3. **Los mensajes se guardan en SQLite** — puedes verlos en el panel admin
4. **Claude sabe todos los precios y especificaciones** — el bot responderá con datos correctos automáticamente

---

## Proximos Pasos

- [ ] Crear 5 anuncios de prueba (uno para cada producto top)
- [ ] Configurar payloads en cada anuncio
- [ ] Probar haciendo clic desde tu teléfono
- [ ] Monitorear respuestas en Railway logs
- [ ] Escalar presupuesto cuando veas que funciona

¿Preguntas sobre setup?
