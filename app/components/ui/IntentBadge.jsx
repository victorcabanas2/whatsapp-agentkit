export function IntentBadge({ intencion }) {
  const styles = {
    hot: "bg-[#FEE2E2] text-[#991B1B]",
    warm: "bg-[#FEF3C7] text-[#92400E]",
    cold: "bg-[#F3F4F6] text-[#374151]",
  };

  const labels = {
    hot: "🔥 Caliente",
    warm: "⚠️ Tibio",
    cold: "❄️ Frío",
  };

  return (
    <span className={`badge px-2 py-1 rounded-full text-xs font-medium ${styles[intencion] || styles.cold}`}>
      {labels[intencion] || "Desconocido"}
    </span>
  );
}
