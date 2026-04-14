import { useLoaderData } from "react-router";

export const loader = async () => {
  // TODO: Connect to bot API for orders
  return { orders: [] };
};

export default function DevOrders() {
  const { orders } = useLoaderData();

  return (
    <div>
      <h1 style={{ margin: "0 0 20px 0" }}>Pedidos</h1>
      <p style={{ color: "#71717a", marginBottom: "20px" }}>Registro de pedidos realizados</p>

      <div style={{
        marginBottom: "20px",
        display: "flex",
        gap: "10px",
      }}>
        <select style={{
          padding: "10px 12px",
          border: "1px solid #e8e8e5",
          borderRadius: "6px",
          fontSize: "14px",
        }}>
          <option value="">Todos los estados</option>
          <option value="pendiente">Pendiente</option>
          <option value="pagado">Pagado</option>
          <option value="entregado">Entregado</option>
        </select>
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
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>ID</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Cliente</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Producto</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Precio</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Estado</th>
              <th style={{ padding: "12px 16px", textAlign: "left", fontSize: "12px", fontWeight: "600", color: "#71717a" }}>Fecha</th>
            </tr>
          </thead>
          <tbody>
            {(!orders || orders.length === 0) && (
              <tr>
                <td colSpan="6" style={{ padding: "32px 16px", textAlign: "center", color: "#71717a" }}>
                  No hay pedidos registrados
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
