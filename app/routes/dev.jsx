import { Outlet } from "react-router";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }) => {
  await authenticate.admin(request);
  return null;
};

export default function DevLayout() {
  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <nav style={{
        width: "200px",
        background: "#f0f0f0",
        padding: "20px",
        borderRight: "1px solid #ddd",
      }}>
        <h2 style={{ marginTop: 0 }}>Dashboard</h2>
        <ul style={{ listStyle: "none", padding: 0 }}>
          <li><a href="/dev" style={{ textDecoration: "none", color: "#2c5aa0" }}>Home</a></li>
          <li><a href="/dev/leads" style={{ textDecoration: "none", color: "#2c5aa0" }}>Leads</a></li>
          <li><a href="/dev/campaigns" style={{ textDecoration: "none", color: "#2c5aa0" }}>Campaigns</a></li>
          <li><a href="/dev/messages" style={{ textDecoration: "none", color: "#2c5aa0" }}>Messages</a></li>
          <li><a href="/dev/orders" style={{ textDecoration: "none", color: "#2c5aa0" }}>Orders</a></li>
        </ul>
      </nav>
      <main style={{ flex: 1, padding: "20px", overflow: "auto" }}>
        <Outlet />
      </main>
    </div>
  );
}
