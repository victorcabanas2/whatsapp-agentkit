import { useLoaderData, useSearchParams } from "react-router";
import { authenticate } from "../shopify.server";
import { getPedidos } from "../lib/bot-api.server";

export const loader = async ({ request }) => {
  const { admin } = await authenticate.admin(request);
  const url = new URL(request.url);
  const estado = url.searchParams.get("estado") || "todos";

  try {
    const pedidos = await getPedidos(estado, 100);
    return { pedidos, estado };
  } catch (e) {
    console.log("Bot API error, using mock data:", e.message);
    const mockPedidos = [
      {
        id: "1",
        telefono: "+595991234567",
        producto: "WHOOP Band",
        precio: 250000,
        metodo_pago: "Tranferencia Itaú",
        estado: "pagado",
        fecha_pedido: "2026-04-11T10:30:00Z",
      },
      {
        id: "2",
        telefono: "+595981234567",
        producto: "Therabody Theragun Elite",
        precio: 450000,
        metodo_pago: "UENO Tarjeta",
        estado: "pendiente",
        fecha_pedido: "2026-04-10T14:15:00Z",
      },
      {
        id: "3",
        telefono: "+595971234567",
        producto: "Foreo Luna",
        precio: 180000,
        metodo_pago: "Efectivo",
        estado: "cancelado",
        fecha_pedido: "2026-04-08T09:45:00Z",
      },
    ];
    return { pedidos: mockPedidos, estado };
  }
};

function getEstadoColor(estado) {
  switch (estado) {
    case "pagado":
      return "bg-[#F0FDF4] text-[#065F46]";
    case "pendiente":
      return "bg-[#FEF3C7] text-[#92400E]";
    case "cancelado":
      return "bg-[#FEF2F2] text-[#991B1B]";
    default:
      return "bg-[#F9FAFB] text-[#52525B]";
  }
}

function formatCurrency(amount) {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "PYG",
    minimumFractionDigits: 0,
  }).format(amount);
}

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

export default function DashboardOrders() {
  const { pedidos, estado } = useLoaderData();
  const [searchParams, setSearchParams] = useSearchParams();

  const filterOptions = [
    { value: "todos", label: "Todos" },
    { value: "pendiente", label: "Pendientes ⏳" },
    { value: "pagado", label: "Pagados ✅" },
    { value: "cancelado", label: "Cancelados ❌" },
  ];

  const stats = {
    total: pedidos.length,
    pagados: pedidos.filter((p) => p.estado === "pagado").length,
    pendientes: pedidos.filter((p) => p.estado === "pendiente").length,
    cancelados: pedidos.filter((p) => p.estado === "cancelado").length,
    ingresos: pedidos
      .filter((p) => p.estado === "pagado")
      .reduce((sum, p) => sum + (p.precio || 0), 0),
  };

  return (
    <div className="p-6 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#18181B]">Pedidos</h1>
        <p className="text-sm text-[#71717A] mt-1">
          {stats.total} órdenes registradas
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-white border border-[#E8E8E5] rounded-lg p-4">
          <p className="text-xs font-semibold text-[#71717A] uppercase tracking-wider">
            Total
          </p>
          <p className="text-2xl font-bold text-[#18181B] mt-2">{stats.total}</p>
        </div>
        <div className="bg-white border border-[#E8E8E5] rounded-lg p-4">
          <p className="text-xs font-semibold text-[#71717A] uppercase tracking-wider">
            Pagados
          </p>
          <p className="text-2xl font-bold text-[#16A34A] mt-2">
            {stats.pagados}
          </p>
        </div>
        <div className="bg-white border border-[#E8E8E5] rounded-lg p-4">
          <p className="text-xs font-semibold text-[#71717A] uppercase tracking-wider">
            Pendientes
          </p>
          <p className="text-2xl font-bold text-[#D97706] mt-2">
            {stats.pendientes}
          </p>
        </div>
        <div className="bg-white border border-[#E8E8E5] rounded-lg p-4">
          <p className="text-xs font-semibold text-[#71717A] uppercase tracking-wider">
            Ingresos
          </p>
          <p className="text-xl font-bold text-[#18181B] mt-2">
            {formatCurrency(stats.ingresos)}
          </p>
        </div>
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

      {/* Orders Table */}
      <div className="bg-white border border-[#E8E8E5] rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-[#FAFAF9] border-b border-[#E8E8E5]">
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Teléfono
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Producto
              </th>
              <th className="px-6 py-3 text-right text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Precio
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-[#71717A] uppercase tracking-wider">
                Método Pago
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
            {pedidos.map((pedido) => (
              <tr
                key={pedido.id}
                className="h-12 border-b border-[#E8E8E5] hover:bg-[#FAFAF9] transition-colors"
              >
                <td className="px-6 py-3 font-mono text-sm text-[#52525B]">
                  {pedido.telefono}
                </td>
                <td className="px-6 py-3 text-sm font-medium text-[#18181B]">
                  {pedido.producto}
                </td>
                <td className="px-6 py-3 text-right text-sm font-medium text-[#18181B]">
                  {formatCurrency(pedido.precio)}
                </td>
                <td className="px-6 py-3 text-sm text-[#71717A]">
                  {pedido.metodo_pago}
                </td>
                <td className="px-6 py-3 text-center">
                  <span
                    className={`inline-block px-3 py-1 rounded text-xs font-semibold ${getEstadoColor(
                      pedido.estado
                    )}`}
                  >
                    {pedido.estado.charAt(0).toUpperCase() +
                      pedido.estado.slice(1)}
                  </span>
                </td>
                <td className="px-6 py-3 text-sm text-[#71717A]">
                  {formatDate(pedido.fecha_pedido)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {pedidos.length === 0 && (
          <div className="px-6 py-12 text-center">
            <p className="text-[#71717A]">No hay pedidos en esta categoría</p>
          </div>
        )}
      </div>
    </div>
  );
}
