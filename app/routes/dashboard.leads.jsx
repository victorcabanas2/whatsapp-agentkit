import { useLoaderData, useNavigate } from "react-router";
import { useSearchParams } from "react-router-dom";
import { authenticate } from "../shopify.server";
import { getLeads } from "../lib/bot-api.server";
import { Avatar } from "../components/ui/Avatar";
import { IntentBadge } from "../components/ui/IntentBadge";
import { ScoreBar } from "../components/ui/ScoreBar";

export const loader = async ({ request }) => {
  const { admin } = await authenticate.admin(request);
  const url = new URL(request.url);
  const estado = url.searchParams.get("estado") || "todos";

  try {
    const leads = await getLeads(estado, 500);
    // Filter by estado if provided
    if (estado && estado !== "todos") {
      return { leads: leads.filter(l => l.intencion === estado), estado };
    }
    return { leads, estado };
  } catch (e) {
    console.log("Bot API error, using mock data:", e.message);
    // Mock data for development
    const allMocks = [
      {
        id: "1",
        telefono: "+595991234567",
        nombre: "Juan Pérez",
        primer_contacto: "2026-04-10T14:30:00Z",
        ultimo_mensaje: "2026-04-11T09:15:00Z",
        fue_cliente: true,
        score: 85,
        intencion: "hot",
        producto_preferido: "WHOOP Band",
      },
      {
        id: "2",
        telefono: "+595981234567",
        nombre: "María González",
        primer_contacto: "2026-04-08T10:00:00Z",
        ultimo_mensaje: "2026-04-10T16:45:00Z",
        fue_cliente: false,
        score: 65,
        intencion: "warm",
        producto_preferido: null,
      },
      {
        id: "3",
        telefono: "+595971234567",
        nombre: "Carlos López",
        primer_contacto: "2026-03-25T11:20:00Z",
        ultimo_mensaje: "2026-03-28T13:00:00Z",
        fue_cliente: false,
        score: 30,
        intencion: "cold",
        producto_preferido: null,
      },
    ];
    return { leads: mockLeads, estado };
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

export default function DashboardLeads() {
  const { leads, estado } = useLoaderData();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const filterOptions = [
    { value: "todos", label: "Todos" },
    { value: "nuevos", label: "Nuevos" },
    { value: "hot", label: "Calientes 🔥" },
    { value: "warm", label: "Tibios 🌡️" },
    { value: "cold", label: "Fríos ❄️" },
  ];

  const handleFilterChange = (e) => {
    setSearchParams({ estado: e.target.value });
  };

  return (
    <div className="p-6 max-w-7xl">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[#18181B]">Leads</h1>
          <p className="text-sm text-[#71717A] mt-1">
            {leads.length} contactos
          </p>
        </div>
        <button
          onClick={() => navigate("/dashboard/leads/import")}
          className="px-4 py-2 bg-[#16A34A] text-white rounded-lg font-medium text-sm hover:bg-[#15803D] transition-colors"
        >
          📥 Importar Excel
        </button>
      </div>

      {/* Filter Bar */}
      <div className="mb-6 flex gap-3 flex-wrap">
        {filterOptions.map((option) => (
          <button
            key={option.value}
            onClick={() => setSearchParams({ estado: option.value })}
            className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
              estado === option.value
                ? "bg-[#18181B] text-white"
                : "bg-[#E8E8E5] text-[#18181B] hover:bg-[#D8D8D5]"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Leads Table */}
      <div className="bg-white border border-[#E8E8E5] rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[#FAFAF9] border-b border-[#E8E8E5]">
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Contacto
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Teléfono
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Score
              </th>
              <th className="px-6 py-3 text-center text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Intención
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                1er Contacto
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Último Msg
              </th>
              <th className="px-6 py-3 text-center text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Cliente
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Preferencia
              </th>
            </tr>
          </thead>
          <tbody>
            {leads.map((lead) => (
              <tr
                key={lead.telefono}
                className="h-11 border-b border-[#E8E8E5] hover:bg-[#FAFAF9] transition-colors"
              >
                <td className="px-6 py-3">
                  <div className="flex items-center gap-3">
                    <Avatar name={lead.nombre} size="sm" />
                    <span className="font-medium text-[#18181B]">
                      {lead.nombre || "Sin nombre"}
                    </span>
                  </div>
                </td>
                <td className="px-6 py-3 font-mono text-sm text-[#52525B]">
                  {lead.telefono}
                </td>
                <td className="px-6 py-3">
                  <ScoreBar score={lead.score || 0} />
                </td>
                <td className="px-6 py-3 text-center">
                  <IntentBadge intencion={lead.intencion} />
                </td>
                <td className="px-6 py-3 text-sm text-[#71717A]">
                  {formatDate(lead.primer_contacto)}
                </td>
                <td className="px-6 py-3 text-sm text-[#71717A]">
                  {formatDate(lead.ultimo_mensaje)}
                </td>
                <td className="px-6 py-3 text-center">
                  {lead.fue_cliente ? (
                    <span className="inline-block w-2 h-2 bg-[#16A34A] rounded-full" />
                  ) : (
                    <span className="inline-block w-2 h-2 bg-[#E8E8E5] rounded-full" />
                  )}
                </td>
                <td className="px-6 py-3 text-sm text-[#71717A]">
                  {lead.producto_preferido || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {leads.length === 0 && (
          <div className="px-6 py-12 text-center">
            <p className="text-[#71717A]">No hay leads en esta categoría</p>
          </div>
        )}
      </div>
    </div>
  );
}
