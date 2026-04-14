import React, { useState } from "react";
import { useLoaderData } from "react-router";
import { getLeads } from "../lib/bot-api.server";

export const loader = async () => {
  try {
    const leads = await getLeads("todos", 500);
    return { leads: leads || [] };
  } catch (e) {
    return { leads: [] };
  }
};

export default function DevMessages() {
  const { leads } = useLoaderData();
  const [selectedLead, setSelectedLead] = useState("");
  const [manualPhone, setManualPhone] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [imagen, setImagen] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const [estado, setEstado] = useState("");

  const handleImageUpload = (e) => {
    setImagen(e.target.files[0]);
  };

  const normalizarTelefono = (tel) => {
    // Acepta: 595986147509, 0986147509, +595986147509
    tel = tel.replace(/\D/g, ""); // Quitar espacios y caracteres especiales
    if (tel.startsWith("0")) {
      tel = "595" + tel.substring(1); // 0986... → 595986...
    }
    if (!tel.startsWith("595")) {
      tel = "595" + tel; // Si falta 595, agregarlo
    }
    return "+" + tel; // Agregar + al inicio
  };

  const enviarMensaje = async () => {
    let telefono = manualPhone.trim() || selectedLead;

    if (manualPhone.trim()) {
      telefono = normalizarTelefono(manualPhone);
    }

    if (!telefono || (!mensaje.trim() && !imagen)) {
      alert("Ingresa un teléfono (manual o de la lista) y agrega un mensaje o imagen");
      return;
    }

    setEnviando(true);
    const formData = new FormData();
    formData.append("telefono", telefono);
    formData.append("mensaje", mensaje);
    if (imagen) {
      formData.append("imagen", imagen);
    }

    try {
      const endpoint = imagen ? "/api/admin/enviar-imagen" : "/api/admin/enviar-mensaje";
      const response = await fetch(`http://localhost:8001${endpoint}`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) throw new Error(`Error: ${response.status}`);
      setEstado("✅ Mensaje enviado");
      setMensaje("");
      setImagen(null);
    } catch (error) {
      setEstado(`❌ ${error.message}`);
    } finally {
      setEnviando(false);
    }
  };

  const selectedLeadData = leads.find(l => l.telefono === selectedLead);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: "20px" }}>
      {/* Lista de leads */}
      <div style={{
        background: "#fff",
        border: "1px solid #e8e8e5",
        borderRadius: "8px",
        overflow: "hidden",
        maxHeight: "600px",
        display: "flex",
        flexDirection: "column",
      }}>
        <div style={{ padding: "16px", borderBottom: "1px solid #e8e8e5" }}>
          <h3 style={{ margin: 0, fontSize: "14px" }}>Contactos ({leads.length})</h3>
        </div>
        <div style={{ overflow: "auto", flex: 1 }}>
          {leads.map((lead) => (
            <button
              key={lead.telefono}
              onClick={() => setSelectedLead(lead.telefono)}
              style={{
                width: "100%",
                padding: "12px",
                border: "none",
                borderBottom: "1px solid #f0f0f0",
                background: selectedLead === lead.telefono ? "#e0e0ff" : "#fff",
                textAlign: "left",
                cursor: "pointer",
                fontSize: "12px",
              }}
            >
              <div style={{ fontWeight: "600", color: "#18181b" }}>{lead.nombre}</div>
              <div style={{ color: "#71717a", fontSize: "11px" }}>{lead.telefono}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Área de composición */}
      <div>
        <h1 style={{ margin: "0 0 20px 0" }}>Mensajes Individuales</h1>

        {/* Input manual para teléfono */}
        <div style={{
          background: "#fff",
          border: "1px solid #e8e8e5",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "20px",
        }}>
          <label style={{ display: "block", marginBottom: "8px", fontWeight: "600" }}>
            📞 O ingresa un teléfono manualmente:
          </label>
          <input
            type="tel"
            value={manualPhone}
            onChange={(e) => {
              setManualPhone(e.target.value);
              setSelectedLead("");
            }}
            placeholder="+595986147509 o 0986147509"
            style={{
              width: "100%",
              padding: "10px",
              border: "1px solid #e8e8e5",
              borderRadius: "6px",
              fontSize: "14px",
              fontFamily: "monospace",
            }}
          />
          {manualPhone && (
            <p style={{ fontSize: "12px", color: "#16a34a", marginTop: "4px" }}>
              ✓ Enviarás a: {manualPhone}
            </p>
          )}
        </div>

        {(selectedLeadData || manualPhone) ? (
          <div style={{
            background: "#fff",
            border: "1px solid #e8e8e5",
            borderRadius: "8px",
            padding: "20px",
          }}>
            {!manualPhone && selectedLeadData && (
              <div style={{ marginBottom: "16px", padding: "12px", background: "#f5f5f5", borderRadius: "6px" }}>
                <p style={{ margin: 0, fontSize: "12px", color: "#71717a" }}>Enviando a:</p>
                <p style={{ margin: "4px 0 0 0", fontSize: "14px", fontWeight: "600" }}>
                  {selectedLeadData.nombre} ({selectedLeadData.telefono})
                </p>
              </div>
            )}

            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", marginBottom: "8px", fontWeight: "600" }}>
                📝 Mensaje
              </label>
              <textarea
                value={mensaje}
                onChange={(e) => setMensaje(e.target.value)}
                placeholder="Escribe tu mensaje..."
                style={{
                  width: "100%",
                  minHeight: "150px",
                  padding: "12px",
                  border: "1px solid #e8e8e5",
                  borderRadius: "6px",
                  fontSize: "14px",
                }}
              />
            </div>

            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", marginBottom: "8px", fontWeight: "600" }}>
                🖼️ Imagen (opcional)
              </label>
              <input
                type="file"
                accept="image/*"
                onChange={handleImageUpload}
                style={{
                  padding: "10px",
                  border: "1px solid #e8e8e5",
                  borderRadius: "6px",
                }}
              />
              {imagen && <p style={{ fontSize: "12px", color: "#71717a", marginTop: "4px" }}>✓ {imagen.name}</p>}
            </div>

            <button
              onClick={enviarMensaje}
              disabled={enviando}
              style={{
                padding: "10px 20px",
                background: enviando ? "#ccc" : "#2c5aa0",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: enviando ? "not-allowed" : "pointer",
                fontWeight: "600",
              }}
            >
              {enviando ? "Enviando..." : "✈️ Enviar"}
            </button>

            {estado && (
              <div style={{
                marginTop: "16px",
                padding: "12px",
                borderRadius: "6px",
                background: estado.includes("✅") ? "#dcfce7" : "#fee2e2",
                color: estado.includes("✅") ? "#166534" : "#991b1b",
              }}>
                {estado}
              </div>
            )}
          </div>
        ) : (
          <div style={{
            background: "#fff",
            border: "1px solid #e8e8e5",
            borderRadius: "8px",
            padding: "40px",
            textAlign: "center",
            color: "#71717a",
          }}>
            <p>Selecciona un contacto o ingresa un teléfono para enviar un mensaje</p>
          </div>
        )}
      </div>
    </div>
  );
}
