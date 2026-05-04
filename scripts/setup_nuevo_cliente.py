#!/usr/bin/env python3
"""
setup_nuevo_cliente.py — Configura AgentKit para un nuevo cliente en minutos.
Ejecutar desde la raiz del proyecto: python scripts/setup_nuevo_cliente.py
"""

import os
import json
import shutil
from pathlib import Path

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def p(pregunta: str, default: str = "") -> str:
    sufijo = f" [{default}]" if default else ""
    respuesta = input(f"  {pregunta}{sufijo}: ").strip()
    return respuesta if respuesta else default

def titulo(texto: str):
    print(f"\n{'─'*50}")
    print(f"  {texto}")
    print(f"{'─'*50}")

def ok(texto: str):
    print(f"  ✓ {texto}")

def aviso(texto: str):
    print(f"  ! {texto}")

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

def main():
    print("\n")
    print("  ╔══════════════════════════════════════════╗")
    print("  ║   AgentKit — Configuracion nuevo cliente  ║")
    print("  ╚══════════════════════════════════════════╝")
    print("\n  Respondé las preguntas. Enter = valor por defecto.")
    print("  Esto toma menos de 5 minutos.\n")

    # ── 1. DATOS DEL NEGOCIO ─────────────────
    titulo("1 / 5 — El negocio")
    nombre_negocio   = p("Nombre del negocio")
    descripcion      = p("Qué vende (ej: ropa deportiva, muebles, servicios de limpieza)")
    ciudad           = p("Ciudad", "Asunción, Paraguay")
    direccion        = p("Dirección física (Enter si no tiene local)", "")
    web              = p("Sitio web (Enter si no tiene)", "")
    telefono         = p("Teléfono de contacto (+595...)")
    horario_semana   = p("Horario lunes a viernes", "9:00 AM - 6:00 PM")
    horario_sabado   = p("Horario sábado (Enter si no atiende)", "Cerrado")
    email            = p("Email de contacto (Enter si no tiene)", "")

    # ── 2. EL AGENTE ─────────────────────────
    titulo("2 / 5 — El agente IA")
    nombre_agente   = p("Nombre del agente (ej: Sofia, Lucas, Ana)")
    tono            = p("Tono", "Amigable, cálido y profesional")
    casos           = p("En una frase: qué puede hacer el agente", f"Responder preguntas y tomar pedidos de {nombre_negocio}")
    escalacion_tel  = p("Número para derivar consultas complejas (+595...)", telefono)

    # ── 3. PAGOS ─────────────────────────────
    titulo("3 / 5 — Métodos de pago")
    banco_tf   = p("Banco para transferencias (Enter si no acepta)")
    cuenta_tf  = p("Número de cuenta") if banco_tf else ""
    nombre_tf  = p("Nombre de la cuenta") if banco_tf else ""
    ruc        = p("RUC (Enter si no aplica)", "") if banco_tf else ""
    efectivo   = p("¿Acepta pago en efectivo en local? (s/n)", "s").lower() == "s"
    cuotas     = p("Cuotas sin interés (ej: UENO 12 cuotas, Familiar 6 cuotas / Enter si no)")

    # ── 4. CREDENCIALES ──────────────────────
    titulo("4 / 5 — Credenciales (solo se guardan en .env)")
    anthropic_key    = p("ANTHROPIC_API_KEY (tu clave, la misma para todos los clientes)")
    whapi_token      = p("WHAPI_TOKEN (del canal Whapi del número del cliente)")
    admin_password   = p("Password para el panel de control del cliente")
    vendedor_wa      = p("Tu WhatsApp para alertas (595XXXXXXXXX sin +)")
    admin_wa         = p("WhatsApp del admin del cliente (+595...)", telefono)

    # ── 5. CONFIRMACION ──────────────────────
    titulo("5 / 5 — Confirmación")
    print(f"\n  Negocio:  {nombre_negocio}")
    print(f"  Agente:   {nombre_agente} — {tono}")
    print(f"  Ciudad:   {ciudad}")
    if direccion:
        print(f"  Dirección: {direccion}")
    if banco_tf:
        print(f"  Pago:     Transferencia {banco_tf} / Cuenta: {cuenta_tf}")
    if cuotas:
        print(f"  Cuotas:   {cuotas}")
    print()
    continuar = input("  ¿Todo correcto? Generamos los archivos (s/n): ").strip().lower()
    if continuar != "s":
        print("\n  Cancelado. Podés volver a correr el script.\n")
        return

    # ──────────────────────────────────────────
    # GENERAR ARCHIVOS
    # ──────────────────────────────────────────

    titulo("Generando archivos...")

    # ── .env ─────────────────────────────────
    env_contenido = f"""# Generado por setup_nuevo_cliente.py — {nombre_negocio}
# NUNCA subir este archivo a GitHub

ANTHROPIC_API_KEY={anthropic_key}
WHATSAPP_PROVIDER=whapi
WHAPI_TOKEN={whapi_token}
PORT=8000
ENVIRONMENT=production
DATABASE_URL=sqlite+aiosqlite:////app/data/agentkit.db
VENDEDOR_WHATSAPP={vendedor_wa}
ADMIN_PASSWORD={admin_password}
ADMIN_WHATSAPP={admin_wa}
"""
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_contenido)
    ok(".env creado")

    # ── config/business.yaml ─────────────────
    pagos_yaml = "  metodos:\n"

    if banco_tf:
        pagos_yaml += f"""    transferencia:
      banco: "{banco_tf}"
      cuenta: "{nombre_tf}"
      numero_cuenta: "{cuenta_tf}"
      ruc: "{ruc}"
      descripcion: "Transferencia bancaria"
"""

    if efectivo:
        pagos_yaml += f"""    efectivo:
      tipo: "Pago contra entrega"
      ubicacion: "{f'Local {nombre_negocio}, {direccion}' if direccion else nombre_negocio}"
      descripcion: "Pago en efectivo"
"""

    # Parsear cuotas
    if cuotas:
        for parte in cuotas.split(","):
            parte = parte.strip()
            if not parte:
                continue
            partes = parte.split()
            banco_c = partes[0] if partes else "Banco"
            num_c = partes[1] if len(partes) > 1 else "12"
            key_c = banco_c.lower().replace(" ", "_")
            pagos_yaml += f"""    {key_c}_cuotas:
      banco: "{banco_c}"
      cuotas: {num_c}
      interes: "sin intereses"
      descripcion: "{banco_c} {num_c} cuotas sin interés"
"""

    web_line   = f"  web: {web}" if web else ""
    email_line = f"  email: {email}" if email else ""
    dir_line   = f"""  local_fisico:
    nombre: "{nombre_negocio}"
    direccion: "{direccion}"
    ciudad: "{ciudad}"
""" if direccion else f"""  ciudad: "{ciudad}"
"""

    business_yaml = f"""# Configurado por setup_nuevo_cliente.py

negocio:
  nombre: {nombre_negocio}
  descripcion: |
    {descripcion}

{dir_line}
{web_line}
  telefono: "{telefono}"
{email_line}

  horario:
    lunes_viernes: "{horario_semana}"
    sabado: "{horario_sabado}"
    domingo: "Cerrado"

agente:
  nombre: {nombre_agente}
  tono: "{tono}"
  descripcion: |
    Soy {nombre_agente}, tu agente de {nombre_negocio}.
    {casos}

  casos_de_uso:
    - "Responder preguntas sobre productos y servicios"
    - "Informar precios y disponibilidad"
    - "Tomar pedidos y coordinar entregas"
    - "Atención al cliente 24/7"

pago:
{pagos_yaml}
metadata:
  version: "1.0"
  zona: "{ciudad}"
  idioma: "Español"
"""

    os.makedirs("config", exist_ok=True)
    with open("config/business.yaml", "w", encoding="utf-8") as f:
        f.write(business_yaml)
    ok("config/business.yaml generado")

    # ── config/prompts.yaml (solo edita las partes variables) ────
    prompts_path = Path("config/prompts.yaml")
    if prompts_path.exists():
        with open(prompts_path, "r", encoding="utf-8") as f:
            prompts = f.read()

        reemplazos = {
            "Soy Belén, vendedora de Rebody en Paraguay. Vendo WHOOP, JetBoots, Theragun, Foreo y más wellness. Atiendo 24/7 por WhatsApp.":
                f"Soy {nombre_agente}, agente de {nombre_negocio}. {casos}. Atiendo 24/7 por WhatsApp.",

            '"Hola, soy Belén, la agente de Rebody 😊"':
                f'"Hola, soy {nombre_agente}, la agente de {nombre_negocio} 😊"',

            '"Hola, soy Belén, la agente de Rebody 😊" — integrado naturalmente. Solo en el primer mensaje.':
                f'"Hola, soy {nombre_agente}, la agente de {nombre_negocio} 😊" — integrado naturalmente. Solo en el primer mensaje.',

            '"Te paso con el equipo: +595 993 233 333 😊"':
                f'"Te paso con el equipo: {escalacion_tel} 😊"',

            "Te paso con el equipo: +595 993 233 333":
                f"Te paso con el equipo: {escalacion_tel}",
        }

        for viejo, nuevo in reemplazos.items():
            prompts = prompts.replace(viejo, nuevo)

        # También reemplazar la línea de respuesta de saludos pre-escritos en brain.py
        with open(prompts_path, "w", encoding="utf-8") as f:
            f.write(prompts)
        ok("config/prompts.yaml actualizado")
    else:
        aviso("config/prompts.yaml no encontrado — generando uno básico")
        prompts_basico = f"""system_prompt: |
  Soy {nombre_agente}, agente de {nombre_negocio}. {casos}. Atiendo 24/7 por WhatsApp.

  ## PRIMER MENSAJE
  Me presento: "Hola, soy {nombre_agente}, la agente de {nombre_negocio} 😊" — solo en el primer mensaje.

  ## FORMATO
  Texto conversacional, párrafos cortos, emojis ocasionales. Sin markdown.

  ## CONSULTAS FUERA DE MI ALCANCE
  "Te paso con el equipo: {escalacion_tel} 😊"

fallback_message: "Disculpá, no entendí bien. ¿Podés escribirlo de otra forma?"
"""
        with open("config/prompts.yaml", "w", encoding="utf-8") as f:
            f.write(prompts_basico)
        ok("config/prompts.yaml creado")

    # ── Actualizar saludo en brain.py ────────
    brain_path = Path("agent/brain.py")
    if brain_path.exists():
        with open(brain_path, "r", encoding="utf-8") as f:
            brain = f.read()
        brain = brain.replace(
            'return "Hola, soy Belén, la agente de Rebody 😊 ¿En qué te puedo ayudar?"',
            f'return "Hola, soy {nombre_agente}, la agente de {nombre_negocio} 😊 ¿En qué te puedo ayudar?"'
        )
        with open(brain_path, "w", encoding="utf-8") as f:
            f.write(brain)
        ok("agent/brain.py actualizado (saludo)")

    # ── knowledge/stock_actual.json ──────────
    stock_inicial = {"productos": {}, "ultima_actualizacion": "pendiente"}
    os.makedirs("knowledge", exist_ok=True)
    with open("knowledge/stock_actual.json", "w", encoding="utf-8") as f:
        json.dump(stock_inicial, f, ensure_ascii=False, indent=2)
    ok("knowledge/stock_actual.json reseteado")

    # ── knowledge/catálogo_completo.json ─────
    catalogo_vacio = {
        "_EJEMPLO": {
            "nombre": "Nombre del producto",
            "url": "https://tutienda.com/producto",
            "precio": "0 Gs",
            "categoria": "General",
            "especificaciones": ["Característica 1", "Característica 2"],
            "beneficios": ["Para qué sirve", "Qué problema resuelve"],
            "como_se_usa": "Descripción breve"
        }
    }
    with open("knowledge/catálogo_completo.json", "w", encoding="utf-8") as f:
        json.dump(catalogo_vacio, f, ensure_ascii=False, indent=2)
    ok("knowledge/catálogo_completo.json reseteado con ejemplo")

    # ── knowledge/imagenes_productos.json ────
    with open("knowledge/imagenes_productos.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    ok("knowledge/imagenes_productos.json reseteado")

    # ── Limpiar DB vieja ─────────────────────
    for archivo in ["agentkit.db", "agentkit_memory.log"]:
        if Path(archivo).exists():
            os.remove(archivo)
            ok(f"{archivo} eliminado (datos del cliente anterior)")

    # ── ads.yaml vacío ───────────────────────
    with open("config/ads.yaml", "w", encoding="utf-8") as f:
        f.write("ad_products: {}\n")
    ok("config/ads.yaml reseteado")

    # ──────────────────────────────────────────
    # RESULTADO FINAL
    # ──────────────────────────────────────────

    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║            ✅  Configuración lista        ║")
    print("  ╚══════════════════════════════════════════╝")
    print()
    print(f"  Negocio: {nombre_negocio}")
    print(f"  Agente:  {nombre_agente}")
    print()
    print("  PRÓXIMO PASO OBLIGATORIO:")
    print("  → Cargar el catálogo de productos:")
    print("     Editar: knowledge/catálogo_completo.json")
    print("     (borrar el ejemplo _EJEMPLO y agregar los productos reales)")
    print()
    print("  OPCIONAL:")
    print("  → Agregar imagen de datos bancarios en agent/main.py línea ~85")
    print("     IMAGEN_DATOS_BANCARIOS = 'URL de la imagen'")
    print()
    print("  CUANDO EL CATÁLOGO ESTÉ LISTO:")
    print("  → Probar localmente:   python tests/test_local.py")
    print("  → Deploy a Railway:    railway up")
    print()

if __name__ == "__main__":
    main()
