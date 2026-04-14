import React from "react";
import { useLoaderData, useSearchParams } from "react-router";
import { getLeads } from "../lib/bot-api.server";

export const loader = async ({ request }) => {
  const url = new URL(request.url);
  const estado = url.searchParams.get("estado") || "todos";

  try {
    const leads = await getLeads(estado, 500);
    if (estado && estado !== "todos") {
      return { leads: leads.filter(l => l.intencion === estado), estado };
    }
    return { leads, estado };
  } catch (e) {
    console.log("Bot API error:", e.message);
    return { leads: [], estado };
  }
};

function formatDate(isoString) {
  if (!isoString) return "—";
  const date = new Date(isoString);
  return date.toLocaleDateString("es-ES", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function DevLeads() {
  const { leads, estado } = useLoaderData();
  const [searchParams, setSearchParams] = useSearchParams();
  const [botStatus, setBotStatus] = React.useState({});

  const filterOptions = [
    { value: "todos", label: "Todos" },
    { value: "hot", label: "Calientes 🔥" },
    { value: "warm", label: "Tibios 🌡️" },
    { value: "cold", label: "Fríos ❄️" },
  ];

  const toggleBotControl = async (telefono) => {
    const newStatus = !botStatus[telefono];
    setBotStatus({ ...botStatus, [telefono]: newStatus });
    // TODO: Call bot API to toggle control
    console.log(`Bot ${newStatus ? "activado" : "desactivado"} para ${telefono}`);
  };

  return (
    <div>
      <h1 style={{ margin: "0 0 20px 0" }}>Leads</h1>
      <p style={{ color: "#71717a", marginBottom: "20px" }}>{leads?.length || 0} contactos</p>

      <div style={{ marginBottom: "20px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
        {filterOptions.map((option) => (
          <button
            key={option.value}
            onClick={() => setSearchParams({ estado: option.value })}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              fontWeight: "600",
              fontSize: "14px",
              cursor: "pointer",
              background: estado === option.value ? "#18181b" : "#e8e8e5",
              color: estado === option.value ? "#fff" : "#18181b",
            }}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div style={{
        background: "#fff",
        border: "1px solid #e8e8e5",
        borderRadius: "8px",
        overflow: "hidden",
      }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#fafaf9", borderBottom: "1px solid #e8e8e5" }}>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Contacto</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Teléfono</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Score</th>
              <th style={{ padding: "12px 16px", textAlign: "center", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Intención</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>1er Contacto</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Último Msg</th>
              <th style={{ padding: "12px 16px", textAlign: "center", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Control</th>
            </tr>
          </thead>
          <tbody>
            {leads && leads.map((lead) => (
              <tr key={lead.telefono} style={{ borderBottom: "1px solid #e8e8e5" }}>
                <td style={{ padding: "12px 16px" }}>{lead.nombre || "Sin nombre"}</td>
                <td style={{ padding: "12px 16px", fontFamily: "monospace", fontSize: "14px" }}>{lead.telefono}</td>
                <td style={{ padding: "12px 16px" }}>
                  <div style={{
                    width: "100px",
                    height: "8px",
                    background: "#e8e8e5",
                    borderRadius: "4px",
                    overflow: "hidden",
                  }}>
                    <div style={{
                      width: `${(lead.score || 0)}%`,
                      height: "100%",
                      background: lead.score >= 70 ? "#16a34a" : lead.score >= 50 ? "#f59e0b" : "#ef4444",
                    }} />
                  </div>
                </td>
                <td style={{ padding: "12px 16px", textAlign: "center" }}>
                  <span style={{
                    display: "inline-block",
                    padding: "4px 8px",
                    borderRadius: "4px",
                    background: lead.intencion === "hot" ? "#fee2e2" : lead.intencion === "warm" ? "#fef3c7" : "#f3f4f6",
                    color: lead.intencion === "hot" ? "#7f1d1d" : lead.intencion === "warm" ? "#78350f" : "#374151",
                    fontSize: "12px",
                    fontWeight: "600",
                  }}>
                    {lead.intencion}
                  </span>
                </td>
                <td style={{ padding: "12px 16px", fontSize: "14px", color: "#71717a" }}>{formatDate(lead.primer_contacto)}</td>
                <td style={{ padding: "12px 16px", fontSize: "14px", color: "#71717a" }}>{formatDate(lead.ultimo_mensaje)}</td>
                <td style={{ padding: "12px 16px", textAlign: "center" }}>
                  <button
                    onClick={() => toggleBotControl(lead.telefono)}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "4px",
                      border: "1px solid #e8e8e5",
                      background: botStatus[lead.telefono] ? "#16a34a" : "#ef4444",
                      color: "#fff",
                      cursor: "pointer",
                      fontSize: "12px",
                      fontWeight: "600",
                    }}
                  >
                    {botStatus[lead.telefono] ? "✓ Bot ON" : "✗ Bot OFF"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {(!leads || leads.length === 0) && (
          <div style={{ padding: "48px 16px", textAlign: "center", color: "#71717a" }}>
            No hay leads en esta categoría
          </div>
        )}
      </div>
    </div>
  );
}
