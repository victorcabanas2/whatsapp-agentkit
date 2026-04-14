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

export default function DevCampaigns() {
  const { leads } = useLoaderData();
  const [modo, setModo] = useState("todos"); // "todos", "individual", "custom", "manual"
  const [mensaje, setMensaje] = useState("");
  const [imagen, setImagen] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const [estado, setEstado] = useState("");
  const [selectedIndividual, setSelectedIndividual] = useState("");
  const [selectedCustom, setSelectedCustom] = useState(new Set());
  const [manualNumbers, setManualNumbers] = useState("");

  const handleImageUpload = (e) => {
    setImagen(e.target.files[0]);
  };

  const toggleCustomSelect = (telefono) => {
    const newSet = new Set(selectedCustom);
    if (newSet.has(telefono)) {
      newSet.delete(telefono);
    } else {
      newSet.add(telefono);
    }
    setSelectedCustom(newSet);
  };

  const getSelectedLeads = () => {
    if (modo === "todos") return leads;
    if (modo === "individual") {
      const lead = selectedIndividual ? leads.find(l => l.telefono === selectedIndividual) : null;
      return lead ? [lead] : [];
    }
    if (modo === "custom") return leads.filter(l => selectedCustom.has(l.telefono));
    if (modo === "manual") {
      // Parsear números ingresados manualmente
      return manualNumbers
        .split("\n")
        .map(tel => tel.trim())
        .filter(tel => tel.length > 0)
        .map(tel => ({
          telefono: normalizarTelefono(tel),
          nombre: "Cliente manual",
        }));
    }
    return [];
  };

  const enviarCampana = async () => {
    if (!mensaje.trim() && !imagen) {
      alert("Agrega al menos un mensaje o una imagen");
      return;
    }

    const selectedLeads = getSelectedLeads();
    if (selectedLeads.length === 0) {
      alert("Selecciona al menos un contacto");
      return;
    }

    setEnviando(true);
    setEstado("Enviando...");

    // Elegir endpoint según modo
    let endpoint = "/api/admin/enviar-masivo";
    let body;

    if (modo === "todos") {
      // Usar FormData para modo todos (con imagen)
      const formData = new FormData();
      formData.append("mensaje", mensaje);
      if (imagen) {
        formData.append("imagen", imagen);
      }
      body = formData;
    } else {
      // Usar JSON para números específicos
      endpoint = "/api/admin/enviar-a-numeros";
      body = JSON.stringify({
        mensaje,
        telefonos: selectedLeads.map(l => l.telefono),
        imagen: imagen ? await imagen.arrayBuffer().then(buf => btoa(String.fromCharCode(...new Uint8Array(buf)))) : null
      });
    }

    try {
      const options = {
        method: "POST",
        body,
      };
      if (modo !== "todos") {
        options.headers = { "Content-Type": "application/json" };
      }
      const response = await fetch(`http://localhost:8001${endpoint}`, options);

      if (!response.ok) throw new Error(`Error: ${response.status}`);
      const result = await response.json();
      const exitosos = result.exitosos || 0;
      const fallidos = result.fallidos || 0;
      setEstado(`✅ Enviado a ${selectedLeads.length} contactos: ${exitosos} éxito, ${fallidos} fallo`);
      setMensaje("");
      setImagen(null);
    } catch (error) {
      setEstado(`❌ ${error.message}`);
    } finally {
      setEnviando(false);
    }
  };

  const selectedLeads = getSelectedLeads();

  return (
    <div>
      <h1 style={{ margin: "0 0 20px 0" }}>Campañas Masivas</h1>

      {/* Opciones de envío */}
      <div style={{
        background: "#fff",
        border: "1px solid #e8e8e5",
        borderRadius: "8px",
        padding: "16px",
        marginBottom: "20px",
      }}>
        <label style={{ display: "block", marginBottom: "12px", fontWeight: "600" }}>
          📤 Enviar a:
        </label>
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
            <input
              type="radio"
              name="modo"
              value="todos"
              checked={modo === "todos"}
              onChange={(e) => setModo(e.target.value)}
            />
            <span>Todos ({leads.length})</span>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
            <input
              type="radio"
              name="modo"
              value="individual"
              checked={modo === "individual"}
              onChange={(e) => setModo(e.target.value)}
            />
            <span>Individual</span>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
            <input
              type="radio"
              name="modo"
              value="custom"
              checked={modo === "custom"}
              onChange={(e) => setModo(e.target.value)}
            />
            <span>Selección ({selectedCustom.size})</span>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
            <input
              type="radio"
              name="modo"
              value="manual"
              checked={modo === "manual"}
              onChange={(e) => setModo(e.target.value)}
            />
            <span>Escribir números</span>
          </label>
        </div>
      </div>

      {/* Selección individual */}
      {modo === "individual" && (
        <div style={{
          background: "#fff",
          border: "1px solid #e8e8e5",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "20px",
        }}>
          <label style={{ display: "block", marginBottom: "8px", fontWeight: "600" }}>
            Selecciona un contacto:
          </label>
          <select
            value={selectedIndividual}
            onChange={(e) => setSelectedIndividual(e.target.value)}
            style={{
              width: "100%",
              padding: "10px",
              border: "1px solid #e8e8e5",
              borderRadius: "6px",
              fontSize: "14px",
            }}
          >
            <option value="">-- Elige un contacto --</option>
            {leads.map((lead) => (
              <option key={lead.telefono} value={lead.telefono}>
                {lead.nombre} ({lead.telefono})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Números manuales */}
      {modo === "manual" && (
        <div style={{
          background: "#fff",
          border: "1px solid #e8e8e5",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "20px",
        }}>
          <label style={{ display: "block", marginBottom: "12px", fontWeight: "600" }}>
            ✏️ Ingresa números de teléfono (uno por línea):
          </label>
          <textarea
            value={manualNumbers}
            onChange={(e) => setManualNumbers(e.target.value)}
            placeholder={`595986147509\n0986147509\n+595991234567\n...`}
            style={{
              width: "100%",
              minHeight: "120px",
              padding: "12px",
              border: "1px solid #e8e8e5",
              borderRadius: "6px",
              fontSize: "14px",
              fontFamily: "monospace",
            }}
          />
          <p style={{ fontSize: "12px", color: "#71717a", marginTop: "8px" }}>
            Acepta formatos: 595986147509, 0986147509 o +595986147509
          </p>
        </div>
      )}

      {/* Selección personalizada */}
      {modo === "custom" && (
        <div style={{
          background: "#fff",
          border: "1px solid #e8e8e5",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "20px",
          maxHeight: "300px",
          overflow: "auto",
        }}>
          <label style={{ display: "block", marginBottom: "12px", fontWeight: "600" }}>
            Selecciona contactos ({selectedCustom.size}/{leads.length}):
          </label>
          {leads.map((lead) => (
            <label
              key={lead.telefono}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                padding: "8px",
                cursor: "pointer",
                borderBottom: "1px solid #f0f0f0",
              }}
            >
              <input
                type="checkbox"
                checked={selectedCustom.has(lead.telefono)}
                onChange={() => toggleCustomSelect(lead.telefono)}
              />
              <span style={{ flex: 1 }}>
                <strong>{lead.nombre}</strong>
                <br />
                <small style={{ color: "#71717a" }}>{lead.telefono}</small>
              </span>
            </label>
          ))}
        </div>
      )}

      {/* Compose */}
      <div style={{
        background: "#fff",
        border: "1px solid #e8e8e5",
        borderRadius: "8px",
        padding: "20px",
        marginBottom: "20px",
      }}>
        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", marginBottom: "8px", fontWeight: "600" }}>
            📝 Mensaje
          </label>
          <textarea
            value={mensaje}
            onChange={(e) => setMensaje(e.target.value)}
            placeholder="Escribe tu mensaje aquí..."
            style={{
              width: "100%",
              minHeight: "120px",
              padding: "12px",
              border: "1px solid #e8e8e5",
              borderRadius: "6px",
              fontSize: "14px",
              fontFamily: "system-ui",
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
              cursor: "pointer",
            }}
          />
          {imagen && <p style={{ fontSize: "12px", color: "#71717a", marginTop: "4px" }}>✓ {imagen.name}</p>}
        </div>

        <div style={{ marginBottom: "16px" }}>
          <p style={{ fontSize: "12px", color: "#71717a" }}>
            Se enviará a <strong>{selectedLeads.length}</strong> contacto{selectedLeads.length !== 1 ? "s" : ""}
          </p>
        </div>

        <button
          onClick={enviarCampana}
          disabled={enviando || selectedLeads.length === 0}
          style={{
            padding: "10px 20px",
            background: enviando || selectedLeads.length === 0 ? "#ccc" : "#16a34a",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            cursor: enviando || selectedLeads.length === 0 ? "not-allowed" : "pointer",
            fontWeight: "600",
          }}
        >
          {enviando ? "Enviando..." : "✈️ Enviar Campaña"}
        </button>

        {estado && (
          <div style={{
            marginTop: "16px",
            padding: "12px",
            borderRadius: "6px",
            background: estado.includes("✅") ? "#dcfce7" : "#fee2e2",
            color: estado.includes("✅") ? "#166534" : "#991b1b",
            fontSize: "14px",
          }}>
            {estado}
          </div>
        )}
      </div>
    </div>
  );
}
