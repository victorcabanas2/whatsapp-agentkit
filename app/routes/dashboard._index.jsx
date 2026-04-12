import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { getStats, getLeads } from "../lib/bot-api.server";
import { Avatar } from "../components/ui/Avatar";
import { IntentBadge } from "../components/ui/IntentBadge";

export const loader = async ({ request }) => {
  const { admin } = await authenticate.admin(request);
  try {
    const stats = await getStats();
    const hotLeads = await getLeads("hot", 5);
    return { stats, hotLeads };
  } catch (e) {
    console.log("Bot API error, using mock data:", e.message);
    return {
      stats: {
        total_leads: 654,
        hot_leads: 42,
        conversion_pct: 8.5,
        pedidos_hoy: 3,
        pedidos_totales: 120,
        pedidos_pendientes: 5,
        sin_respuesta_2h: 12,
        leads_hoy: 15,
      },
      hotLeads: [],
    };
  }
};

function StatCard({ label, value, icon }) {
  return (
    <div className="bg-white border border-[#E8E8E5] rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-[#71717A] uppercase tracking-wider">
            {label}
          </p>
          <p className="text-2xl font-bold text-[#18181B] mt-2">{value}</p>
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
    </div>
  );
}

export default function DashboardHome() {
  const { stats, hotLeads } = useLoaderData();

  return (
    <div className="p-6 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#18181B]">Dashboard</h1>
        <p className="text-sm text-[#71717A] mt-1">Resumen de actividad</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Leads" value={stats.total_leads} icon="👥" />
        <StatCard label="Leads Calientes" value={stats.hot_leads} icon="🔥" />
        <StatCard
          label="Conversión"
          value={`${stats.conversion_pct}%`}
          icon="📈"
        />
        <StatCard label="Pedidos Hoy" value={stats.pedidos_hoy} icon="🛒" />
      </div>

      {/* Hot Leads Table */}
      <div className="bg-white border border-[#E8E8E5] rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-[#E8E8E5]">
          <h2 className="text-lg font-semibold text-[#18181B]">Leads Calientes</h2>
        </div>
        <table className="w-full">
          <thead>
            <tr className="bg-[#FAFAF9] border-b border-[#E8E8E5]">
              <th className="table-header text-left">Contacto</th>
              <th className="table-header text-left">Teléfono</th>
              <th className="table-header text-center">Intención</th>
              <th className="table-header text-right">Score</th>
              <th className="table-header text-left">Producto Preferido</th>
            </tr>
          </thead>
          <tbody>
            {hotLeads.map((lead) => (
              <tr
                key={lead.telefono}
                className="table-row-hover border-b border-[#E8E8E5]"
              >
                <td className="table-cell">
                  <div className="flex items-center gap-3">
                    <Avatar name={lead.nombre} size="sm" />
                    <span className="font-medium text-[#18181B]">
                      {lead.nombre || "Sin nombre"}
                    </span>
                  </div>
                </td>
                <td className="table-cell font-mono text-[#52525B]">
                  {lead.telefono}
                </td>
                <td className="table-cell text-center">
                  <IntentBadge intencion={lead.intencion} />
                </td>
                <td className="table-cell text-right">
                  <span className="bg-[#D1FAE5] text-[#065F46] px-2 py-1 rounded font-medium">
                    {lead.score}
                  </span>
                </td>
                <td className="table-cell text-[#71717A]">
                  {lead.producto_preferido || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
