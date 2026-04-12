import { useLoaderData, useNavigate } from "react-router";
import db from "../db.server";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }) => {
  const { admin } = await authenticate.admin(request);

  try {
    const campaigns = await db.campaign.findMany({
      include: {
        recipients: true,
      },
      orderBy: {
        creadoEn: "desc",
      },
    });

    return {
      campaigns: campaigns.map((c) => ({
        ...c,
        total: c.recipients.length,
        exitosos: c.recipients.filter((r) => r.estado === "enviado").length,
        fallidos: c.recipients.filter((r) => r.estado === "error").length,
      })),
    };
  } catch (e) {
    console.log("DB error, using mock data:", e.message);
    return {
      campaigns: [
        {
          id: "1",
          nombre: "Campaña de bienvenida",
          audiencia: "todos",
          total: 654,
          exitosos: 623,
          fallidos: 31,
          estado: "completada",
          creadoEn: new Date("2026-04-10T10:00:00"),
        },
        {
          id: "2",
          nombre: "Leads calientes - Therabody",
          audiencia: "hot",
          total: 42,
          exitosos: 41,
          fallidos: 1,
          estado: "completada",
          creadoEn: new Date("2026-04-08T14:30:00"),
        },
      ],
    };
  }
};

function getEstadoColor(estado) {
  switch (estado) {
    case "completada":
      return "#16A34A";
    case "enviando":
      return "#D97706";
    case "borrador":
      return "#71717A";
    default:
      return "#71717A";
  }
}

function formatDate(date) {
  if (!date) return "—";
  const d = new Date(date);
  return d.toLocaleDateString("es-ES", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getProgressPercent(exitosos, total) {
  if (total === 0) return 0;
  return Math.round((exitosos / total) * 100);
}

export default function DashboardCampaigns() {
  const { campaigns } = useLoaderData();
  const navigate = useNavigate();

  return (
    <div className="p-6 max-w-7xl">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[#18181B]">Campañas</h1>
          <p className="text-sm text-[#71717A] mt-1">
            {campaigns.length} campañas registradas
          </p>
        </div>
        <button
          onClick={() => navigate("/dashboard/campaigns/new")}
          className="px-4 py-2 bg-[#16A34A] text-white rounded-lg font-medium text-sm hover:bg-[#15803D] transition-colors"
        >
          ➕ Nueva Campaña
        </button>
      </div>

      {/* Campaigns Table */}
      <div className="bg-white border border-[#E8E8E5] rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[#FAFAF9] border-b border-[#E8E8E5]">
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Nombre
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Audiencia
              </th>
              <th className="px-6 py-3 text-center text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Total
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Progreso
              </th>
              <th className="px-6 py-3 text-center text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Estado
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Fecha
              </th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((campaign) => {
              const percent = getProgressPercent(campaign.exitosos, campaign.total);
              return (
                <tr
                  key={campaign.id}
                  className="h-14 border-b border-[#E8E8E5] hover:bg-[#FAFAF9] transition-colors cursor-pointer"
                >
                  <td className="px-6 py-3">
                    <p className="font-medium text-[#18181B]">
                      {campaign.nombre}
                    </p>
                  </td>
                  <td className="px-6 py-3">
                    <span className="text-sm text-[#71717A] capitalize">
                      {campaign.audiencia}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-center">
                    <span className="text-sm font-medium text-[#18181B]">
                      {campaign.total}
                    </span>
                  </td>
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-32 h-2 bg-[#E8E8E5] rounded-full overflow-hidden">
                        <div
                          className="h-full bg-[#16A34A] transition-all duration-300"
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                      <div className="min-w-fit text-xs text-[#71717A]">
                        <span className="font-medium text-[#16A34A]">
                          {campaign.exitosos}
                        </span>
                        {campaign.fallidos > 0 && (
                          <>
                            {" "}
                            /{" "}
                            <span className="text-[#DC2626]">
                              {campaign.fallidos} err
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-3 text-center">
                    <span
                      className="inline-block px-2 py-1 rounded text-xs font-medium text-white capitalize"
                      style={{ backgroundColor: getEstadoColor(campaign.estado) }}
                    >
                      {campaign.estado}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-sm text-[#71717A]">
                    {formatDate(campaign.creadoEn)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {campaigns.length === 0 && (
          <div className="px-6 py-12 text-center">
            <p className="text-[#71717A]">No hay campañas aún</p>
            <button
              onClick={() => navigate("/dashboard/campaigns/new")}
              className="mt-4 text-sm text-[#16A34A] font-medium hover:underline"
            >
              Crear la primera →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
