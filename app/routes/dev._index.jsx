import { useLoaderData } from "react-router";
import { getStats, getLeads } from "../lib/bot-api.server";

export const loader = async () => {
  try {
    const statsData = await getStats();
    const hotLeads = await getLeads("hot", 5);
    console.log("Stats loaded:", statsData);
    return {
      stats: statsData || {
        total_leads: 50,
        hot_leads: 10,
        conversion_pct: 20,
        pedidos_hoy: 2,
        pedidos_totales: 10,
        pedidos_pendientes: 3,
        sin_respuesta_2h: 5,
        leads_hoy: 8,
      },
      hotLeads: hotLeads || []
    };
  } catch (e) {
    console.log("Bot API error:", e.message);
    return {
      stats: {
        total_leads: 50,
        hot_leads: 10,
        conversion_pct: 20,
        pedidos_hoy: 2,
        pedidos_totales: 10,
        pedidos_pendientes: 3,
        sin_respuesta_2h: 5,
        leads_hoy: 8,
      },
      hotLeads: [],
    };
  }
};

function StatCard({ label, value, icon }) {
  return (
    <div style={{
      background: "#fff",
      border: "1px solid #e8e8e5",
      borderRadius: "8px",
      padding: "16px",
      marginBottom: "16px",
    }}>
      <p style={{ fontSize: "12px", color: "#71717a", margin: "0 0 8px 0", textTransform: "uppercase" }}>
        {label}
      </p>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p style={{ fontSize: "28px", fontWeight: "bold", color: "#18181b", margin: 0 }}>
          {value}
        </p>
        <span style={{ fontSize: "24px" }}>{icon}</span>
      </div>
    </div>
  );
}

export default function DevHome() {
  const { stats, hotLeads } = useLoaderData();

  return (
    <div>
      <h1 style={{ margin: "0 0 20px 0" }}>Dashboard</h1>
      <p style={{ color: "#71717a", marginBottom: "20px" }}>Resumen de actividad</p>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: "16px",
        marginBottom: "32px",
      }}>
        <StatCard label="Total Leads" value={stats.total_leads || 0} icon="👥" />
        <StatCard label="Leads Calientes" value={stats.hot_leads || 0} icon="🔥" />
        <StatCard label="Conversión" value={`${stats.conversion_pct || 0}%`} icon="📈" />
        <StatCard label="Pedidos Hoy" value={stats.pedidos_hoy || 0} icon="🛒" />
      </div>

      <div style={{
        background: "#fff",
        border: "1px solid #e8e8e5",
        borderRadius: "8px",
        overflow: "hidden",
      }}>
        <div style={{ padding: "16px", borderBottom: "1px solid #e8e8e5" }}>
          <h2 style={{ margin: 0 }}>Leads Calientes</h2>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#fafaf9", borderBottom: "1px solid #e8e8e5" }}>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Contacto</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Teléfono</th>
              <th style={{ padding: "12px 16px", textAlign: "center", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Intención</th>
              <th style={{ padding: "12px 16px", textAlign: "right", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Score</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Producto</th>
            </tr>
          </thead>
          <tbody>
            {hotLeads && hotLeads.map((lead) => (
              <tr key={lead.telefono} style={{ borderBottom: "1px solid #e8e8e5", hover: { background: "#fafaf9" } }}>
                <td style={{ padding: "12px 16px" }}>{lead.nombre || "Sin nombre"}</td>
                <td style={{ padding: "12px 16px", fontFamily: "monospace", fontSize: "14px" }}>{lead.telefono}</td>
                <td style={{ padding: "12px 16px", textAlign: "center" }}>
                  <span style={{
                    display: "inline-block",
                    padding: "4px 8px",
                    borderRadius: "4px",
                    background: lead.intencion === "hot" ? "#fee2e2" : "#fef3c7",
                    color: lead.intencion === "hot" ? "#7f1d1d" : "#78350f",
                    fontSize: "12px",
                    fontWeight: "600",
                  }}>
                    {lead.intencion}
                  </span>
                </td>
                <td style={{ padding: "12px 16px", textAlign: "right" }}>
                  <span style={{
                    display: "inline-block",
                    padding: "4px 8px",
                    borderRadius: "4px",
                    background: "#d1fae5",
                    color: "#065f46",
                    fontWeight: "600",
                  }}>
                    {lead.score}
                  </span>
                </td>
                <td style={{ padding: "12px 16px", color: "#71717a" }}>{lead.producto_preferido || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
