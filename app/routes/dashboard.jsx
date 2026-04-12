import { Outlet, useLocation } from "react-router";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }) => {
  const { admin } = await authenticate.admin(request);
  return null;
};

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
  { href: "/dashboard/conversations", label: "Conversaciones", icon: "💬" },
  { href: "/dashboard/leads", label: "Clientes", icon: "👥" },
  { href: "/dashboard/messages", label: "Mensajes", icon: "📱" },
  { href: "/dashboard/campaigns", label: "Campañas", icon: "📢" },
  { href: "/dashboard/orders", label: "Pedidos", icon: "🛒" },
];

export default function DashboardLayout() {
  const location = useLocation();

  return (
    <div className="flex h-screen bg-[#FAFAF9]">
      {/* Sidebar */}
      <div className="w-60 bg-[#0F0F0E] text-white flex flex-col border-r border-[#1A1A18]">
        {/* Logo */}
        <div className="px-6 py-6 border-b border-[#1A1A18]">
          <h1 className="text-xl font-bold">🏥 Rebody</h1>
          <p className="text-xs text-[#A1A09A] mt-1">CRM Dashboard</p>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <a
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors text-sm font-medium ${
                  isActive
                    ? "bg-[#18181B] text-white border-l-2 border-[#16A34A]"
                    : "text-[#A1A09A] hover:bg-[#18181B] hover:text-white"
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </a>
            );
          })}
        </nav>

        {/* Bottom */}
        <div className="px-6 py-4 border-t border-[#1A1A18] text-xs text-[#71717A]">
          <p>Rebody Admin</p>
        </div>
      </div>

      {/* Content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
