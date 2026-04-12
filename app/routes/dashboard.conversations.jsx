import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { getLeads, toggleControl } from "../lib/bot-api.server";
import { BotToggle } from "../components/ui/BotToggle";
import { Avatar } from "../components/ui/Avatar";
import { IntentBadge } from "../components/ui/IntentBadge";

export const loader = async ({ request }) => {
  const { admin } = await authenticate.admin(request);
  try {
    const leads = await getLeads("todos", 200);
    return { leads };
  } catch (e) {
    console.log("Bot API error, using mock data:", e.message);
    return { leads: [] };
  }
};

export const action = async ({ request }) => {
  const { admin } = await authenticate.admin(request);
  const form = await request.formData();
  const intent = form.get("intent");
  const telefono = form.get("telefono");

  if (intent === "toggle") {
    const result = await toggleControl(telefono);
    return result;
  }

  return null;
};

export default function ConversationsPage() {
  const { leads } = useLoaderData();

  const formatTime = (iso) => {
    if (!iso) return "—";
    const date = new Date(iso);
    return date.toLocaleTimeString("es-PY", { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-[#18181B]">Conversaciones</h1>
        <p className="text-sm text-[#71717A] mt-1">{leads.length} contactos</p>
      </div>

      {/* Table */}
      <div className="bg-white border border-[#E8E8E5] rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[#FAFAF9] border-b border-[#E8E8E5]">
              <th className="table-header text-left">Contacto</th>
              <th className="table-header text-left">Teléfono</th>
              <th className="table-header text-left">Última actividad</th>
              <th className="table-header text-center">Intención</th>
              <th className="table-header text-right">Score</th>
              <th className="table-header text-center">Estado Bot</th>
            </tr>
          </thead>
          <tbody>
            {leads.map((lead) => (
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
                <td className="table-cell text-[#71717A] text-xs">
                  {formatTime(lead.ultimo_mensaje)}
                </td>
                <td className="table-cell text-center">
                  <IntentBadge intencion={lead.intencion} />
                </td>
                <td className="table-cell text-right font-mono">
                  <span className="bg-[#F3F4F6] px-2 py-1 rounded text-[#18181B] font-medium">
                    {lead.score || 0}
                  </span>
                </td>
                <td className="table-cell text-center">
                  <BotToggle telefono={lead.telefono} initialControl="bot" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {leads.length === 0 && (
        <div className="text-center py-12">
          <p className="text-[#71717A]">No hay conversaciones</p>
        </div>
      )}
    </div>
  );
}
