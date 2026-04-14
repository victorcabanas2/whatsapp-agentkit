# 🔍 DEBUG: Por Qué El Bot No Identifica el Producto Desde Anuncios Meta

## El Problema (Síntomas)
- ✅ Configuraste anuncios Meta para TheraCup, WHOOP PEAK, etc.
- ✅ El bot responde cuando haces clic
- ❌ PERO dice: "¿Qué producto querés información?" (respuesta genérica)
- ❌ NO dice: "Te tengo el WHOOP PEAK..." (respuesta específica del producto)

**Esperado:** Bot sabe qué producto es desde el inicio.
**Actual:** Bot pregunta genéricamente.

---

## Las Causas Posibles (en orden de probabilidad)

### Causa 1 (70% probable): **Meta NO está enviando el contexto del anuncio**

**¿Por qué?** Facebook ha limitado cómo envía contexto de anuncios. El bot NECESITA que hagas una configuración especial en Facebook Ads Manager.

**Síntoma confirma esta causa:**
```
Revisa los LOGS en Railway (ver abajo)
Busca línea: "🔍 DEBUG ANUNCIO - anuncio_id: None, payload: None, contexto_anuncio: None"
↑ Si ves esto, AQUÍ está el problema.
```

**Solución:** Ve a `/docs/ANUNCIOS_SETUP.md` y configura el **payload** en cada anuncio.

---

### Causa 2 (20% probable): **El payload está configurado mal en Facebook**

**Síntoma confirma esta causa:**
```
Revisa los LOGS en Railway
Busca línea: "🔍 DEBUG ANUNCIO - anuncio_id: xyz_weird_id"
↑ Si ves un ID raro que NO coincide con los productos conocidos.
```

**Solución:** Asegúrate que en Facebook Ads Manager usaste EXACTAMENTE estos payloads:
- `whoop_peak` (no `whoop_peak_ad`, no `WHOOP_PEAK`)
- `theragun_mini` (no `Theragun Mini`)
- `jetboots_pro_plus` (exactamente así)
- Ver lista completa en `/docs/ANUNCIOS_SETUP.md` línea 68-90

---

### Causa 3 (10% probable): **El mapeo de producto tiene un bug**

**Síntoma confirma esta causa:**
```
Revisa los LOGS en Railway
Busca línea: "📢 CLIENTE VIENE DE ANUNCIO: xyz_id"
           "Producto del anuncio: xyz_id" ← si el producto es el ID sin mapear
↑ Si el producto es exactamente el mismo que el anuncio_id, el mapeo falló.
```

**Solución:** Ejecuta localmente:
```bash
python3 test_debug_mapping.py
```
Si ves `⚠️ FALLBACK`, ese ID no está en el mapeo. Agrégalo a `agent/brain.py` línea 107.

---

## Cómo Verificar: Revisa los Logs en Railway

### Paso 1: Abre Railway
```
Ve a: https://railway.app
Inicia sesión
Selecciona tu proyecto "whatsapp-agentkit"
```

### Paso 2: Ve a Logs
```
En el dashboard, click izquierda en "Logs"
O ejecuta en terminal: railway logs --follow
```

### Paso 3: Reproduce el error
```
1. Ve a Facebook/Instagram
2. Haz clic en un anuncio Meta de un producto (ej: WHOOP PEAK)
3. Escribe un mensaje al bot
4. Espera 5-10 segundos
```

### Paso 4: Busca en los logs
```
Busca estas líneas en orden:

[A] 📨 WEBHOOK PAYLOAD COMPLETO: {...}
    ↑ Aquí veras qué Meta REALMENTE envía. 
      ¿Contiene "context"? ¿Contiene "referral"? ¿Contiene "payload"?

[B] 🔍 DEBUG ANUNCIO - anuncio_id: ..., payload: ..., contexto_anuncio: ...
    ↑ Aquí veras qué el bot recibió después de parsear.
      ¿Tiene algún valor? ¿O todo es None?

[C] 📢 CLIENTE VIENE DE ANUNCIO: ...
    ↑ Si ves esto, el bot DETECTÓ un anuncio.
      Si NO ves esto, el bot NO detectó nada.

[D] Producto del anuncio: ...
    ↑ ¿Qué producto identificó? ¿Es el correcto?
```

---

## Qué Esperar en los Logs

### ✅ Caso CORRECTO (bot identificó el producto)
```
📨 WEBHOOK PAYLOAD COMPLETO: {..., "text": {"body": "Hola", "context": {"id": "whoop_peak"}}, ...}
🔍 DEBUG ANUNCIO - anuncio_id: whoop_peak, payload: whoop_peak, contexto_anuncio: {'payload': 'whoop_peak'}
📢 CLIENTE VIENE DE ANUNCIO: whoop_peak
Producto del anuncio: WHOOP PEAK 5.0
✅ TÚ CONOCES el producto que vio. NO preguntes 'de qué producto es'.
```

Respuesta del bot:
```
"Te tengo el WHOOP PEAK 5.0... [detalles del producto]"
```

### ❌ Caso INCORRECTO (bot NO identificó producto)
```
📨 WEBHOOK PAYLOAD COMPLETO: {..., "text": {"body": "Hola"}, ...}
   ↑ SIN "context" ni "referral" — Meta NO envió contexto del anuncio

🔍 DEBUG ANUNCIO - anuncio_id: None, payload: None, contexto_anuncio: None
   ↑ El bot NO recibió contexto

Respuesta del bot:
```
"¿Qué producto querés información?" ← respuesta genérica
```

---

## Próximos Pasos Según Tu Caso

### Si ves Caso CORRECTO
```
Excelente! El bot está funcionando correctamente.
Si aún no vende, probablemente es el prompt o la estrategia de venta.
Revisa: /docs/ESTRATEGIA_VENTA.md
```

### Si ves Caso INCORRECTO con None, None, None
```
❌ CAUSA: Meta NO está enviando contexto del anuncio

SOLUCIÓN:
1. Ve a /docs/ANUNCIOS_SETUP.md
2. Sigue "Paso a Paso: Configurar en Facebook Ads Manager"
3. En cada anuncio, configura el PAYLOAD:
   - En el botón CTA, agregar: "Payload: theragun_mini"
   - O via URL: "?product=theragun_mini"
   - O via Whapi.cloud Dashboard (sección Custom Fields)
4. Recrear el anuncio con el payload
5. Reintentar desde tu teléfono
6. Revisar logs nuevamente
```

### Si ves Caso INCORRECTO con ID raro
```
❌ CAUSA: Payload mal configurado en Facebook

SOLUCIÓN:
1. Revisa qué payload enviaste en Facebook
2. Compara con la lista de payloads válidos en /docs/ANUNCIOS_SETUP.md línea 68-90
3. Asegúrate que sea:
   - Minúsculas y guiones (theragun_mini, NO Theragun Mini)
   - Exacto (no agregar sufijos como _ad, _campaign)
4. Edita el anuncio en Facebook y corrige el payload
5. Reintentar
```

---

## Test Local (sin necesidad de Facebook real)

Si quieres probar sin tener un anuncio de verdad:

```bash
# Test 1: Simula un webhook con contexto de anuncio
python3 test_debug_ads.py

# Test 2: Verifica el mapeo de productos
python3 test_debug_mapping.py

# Test 3: Chat interactivo local
python3 tests/test_local.py
# Escribe: "[CLIENTE VIENE DE ANUNCIO DE: whoop_peak] Hola"
# Esperado: Bot responde sobre WHOOP PEAK sin preguntar
```

---

## Checklist de Diagnóstico

Marca lo que ya verificaste:

- [ ] Revisar logs en Railway y buscar las líneas [A], [B], [C], [D]
- [ ] Determinar si Meta está enviando context/payload/referral
- [ ] Si NO: Configurar payload en Facebook Ads Manager (ANUNCIOS_SETUP.md)
- [ ] Si SÍ pero ID raro: Corregir nombre del payload en Facebook
- [ ] Ejecutar test_debug_ads.py y test_debug_mapping.py localmente
- [ ] Recrear el anuncio con payload configurado
- [ ] Hacer clic desde teléfono real y revisar logs
- [ ] Confirmar que bot responde específicamente sobre el producto

---

## Contacto / Más Ayuda

Si después de todo esto sigue sin funcionar:

1. **Copiar el log completo** donde ves el webhook (línea [A])
2. **Copiar qué dice el bot** cuando haces clic en el anuncio
3. **Describir:** ¿Qué producto es el anuncio? ¿Qué payload configuraste?

Con esa info puedo debuggear más a fondo.

---

**Última actualización:** 2026-04-08  
**Debug script:** test_debug_ads.py, test_debug_mapping.py, agent/main.py (línea 391 con debug logging)
