export function StatCard({ label, value, icon }) {
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
