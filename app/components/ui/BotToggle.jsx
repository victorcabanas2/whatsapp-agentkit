import { useFetcher } from "react-router";
import { useEffect, useState } from "react";

export function BotToggle({ telefono, initialControl }) {
  const fetcher = useFetcher();
  const [localControl, setLocalControl] = useState(initialControl);

  // Optimistic update: toggle immediately on click
  const handleToggle = () => {
    const newControl = localControl === "bot" ? "admin" : "bot";
    setLocalControl(newControl);
    fetcher.submit({ intent: "toggle", telefono }, { method: "POST" });
  };

  // If fetcher fails, revert optimistic update
  useEffect(() => {
    if (fetcher.data?.error) {
      setLocalControl(initialControl);
      alert(`Error: ${fetcher.data.error}`);
    }
  }, [fetcher.data?.error, initialControl]);

  const isActive = localControl === "bot";

  return (
    <button
      onClick={handleToggle}
      disabled={fetcher.state === "submitting"}
      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
        isActive
          ? "bg-[#D1FAE5] text-[#065F46] hover:bg-[#A7F3D0]"
          : "bg-[#FEE2E2] text-[#991B1B] hover:bg-[#FECACA]"
      } ${fetcher.state === "submitting" ? "opacity-50 cursor-not-allowed" : ""}`}
    >
      {isActive ? "✓ Bot" : "⏸ Pausado"}
    </button>
  );
}
