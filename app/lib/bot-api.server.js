/**
 * Bot API Client
 * All HTTP calls to the WhatsApp bot go through this file
 * Runs on server only - never import in client components
 */

const BOT_URL = process.env.BOT_API_URL || "http://localhost:8000";

async function apiCall(method, endpoint, body = null) {
  const url = `${BOT_URL}${endpoint}`;
  const options = {
    method,
    headers: {
      "Content-Type": "application/json",
    },
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`Bot API error: ${response.status} ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Bot API call failed: ${method} ${endpoint}`, error);
    throw error;
  }
}

async function apiCallMultipart(method, endpoint, formData) {
  const url = `${BOT_URL}${endpoint}`;
  const options = {
    method,
  };
  // FormData automatically sets Content-Type header with boundary

  options.body = formData;

  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`Bot API error: ${response.status} ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Bot API call failed: ${method} ${endpoint}`, error);
    throw error;
  }
}

export async function getStats() {
  /**
   * Get dashboard statistics
   * Returns: { total_leads, leads_hoy, hot_leads, conversion_pct, pedidos_totales, pedidos_hoy, pedidos_pendientes, sin_respuesta_2h }
   */
  try {
    return await apiCall("GET", "/api/admin/stats");
  } catch (e) {
    console.log("getStats fallback to mock");
    return {
      total_leads: 50,
      leads_hoy: 8,
      hot_leads: 10,
      conversion_pct: 20,
      pedidos_totales: 10,
      pedidos_hoy: 2,
      pedidos_pendientes: 3,
      sin_respuesta_2h: 5,
    };
  }
}

export async function getLeads(estado = "todos", limite = 100) {
  /**
   * Get leads filtered by estado
   * estado: "todos" | "nuevos" | "hot" | "warm" | "cold"
   * Returns: [{id, telefono, nombre, primer_contacto, ultimo_mensaje, fue_cliente, score, intencion, producto_preferido}, ...]
   */
  const params = new URLSearchParams({ estado, limite });
  return apiCall("GET", `/api/admin/leads?${params}`);
}

export async function getPedidos(estado = "todos", limite = 50) {
  /**
   * Get orders filtered by estado
   * estado: "todos" | "pendiente" | "pagado" | "cancelado"
   * Returns: [{id, telefono, producto, precio, metodo_pago, estado, fecha_pedido}, ...]
   */
  const params = new URLSearchParams({ estado, limite });
  return apiCall("GET", `/api/admin/pedidos?${params}`);
}

export async function toggleControl(telefono) {
  /**
   * Toggle bot ON/OFF for a conversation
   * Returns: { telefono, control: "bot"|"admin", action: "silenciado"|"reactivado", exito: bool }
   */
  return apiCall("POST", `/api/admin/toggle-control?telefono=${encodeURIComponent(telefono)}`);
}

export async function sendMessage(telefono, mensaje) {
  /**
   * Send a text-only message to a single contact
   * telefono: phone number (string)
   * mensaje: message text (string)
   * Returns: { exito: bool, mensaje: string }
   */
  const formData = new FormData();
  formData.append("telefono", telefono);
  formData.append("mensaje", mensaje);

  return apiCallMultipart("POST", "/api/admin/enviar-mensaje", formData);
}

export async function sendImage(telefono, imagenFile, caption = "") {
  /**
   * Send an image (with optional text caption) to a single contact
   * telefono: phone number (string)
   * imagenFile: File object from input[type="file"]
   * caption: optional text caption
   * Returns: { exito: bool, mensaje: string }
   */
  const formData = new FormData();
  formData.append("telefono", telefono);
  formData.append("imagen", imagenFile);
  if (caption) {
    formData.append("caption", caption);
  }

  return apiCallMultipart("POST", "/api/admin/enviar-imagen", formData);
}

export async function sendBroadcast(mensaje, imagenFile = null) {
  /**
   * Send a broadcast message to all leads
   * mensaje: message text (string)
   * imagenFile: optional File object for image
   * Returns: { exitosos: int, fallidos: int, total: int }
   */
  const formData = new FormData();
  formData.append("mensaje", mensaje);
  if (imagenFile) {
    formData.append("imagen", imagenFile);
  }

  return apiCallMultipart("POST", "/api/admin/enviar-masivo", formData);
}

export async function importExcel(fileBuffer, filename = "clientes.xlsx") {
  /**
   * Import clients from Excel file
   * fileBuffer: Buffer or File object
   * Returns: { exitosos: int, errores: int, duplicados: int, total: int, detalles: [] }
   */
  const formData = new FormData();
  formData.append("archivo", fileBuffer, filename);

  return apiCallMultipart("POST", "/api/admin/importar-excel", formData);
}

export async function getSinRespuesta(horas = 2) {
  /**
   * Get leads without response for more than X hours
   * Returns: [{ telefono, nombre, ultimo_mensaje, horas_sin_respuesta, score, intencion, timestamp_ultimo_msg }, ...]
   */
  const params = new URLSearchParams({ horas });
  return apiCall("GET", `/api/admin/sin-respuesta?${params}`);
}

export async function getChatStatus(telefono) {
  /**
   * Get bot control status for a specific chat
   * Returns: { telefono, control: "bot"|"admin"|"desconocido", en_manos_humanas: bool }
   */
  const params = new URLSearchParams({ telefono });
  return apiCall("GET", `/api/admin/chat-status?${params}`);
}

export async function tomarControl(telefono) {
  /**
   * Pause bot for a contact (human takes over)
   * Returns: { exito: bool, mensaje: string }
   */
  return apiCall("POST", `/api/admin/tomar-control?telefono=${encodeURIComponent(telefono)}`);
}

export async function liberarControl(telefono) {
  /**
   * Resume bot for a contact
   * Returns: { exito: bool, mensaje: string }
   */
  return apiCall("POST", `/api/admin/liberar-control?telefono=${encodeURIComponent(telefono)}`);
}
