export function PageHeader({
  title,
  subtitle,
  action,
  actionLabel,
  onActionClick,
}) {
  return (
    <div className="mb-8 flex items-center justify-between">
      <div>
        <h1 className="text-3xl font-bold text-[#18181B]">{title}</h1>
        {subtitle && (
          <p className="text-sm text-[#71717A] mt-1">{subtitle}</p>
        )}
      </div>
      {action && (
        <button
          onClick={onActionClick}
          className="px-4 py-2 bg-[#16A34A] text-white rounded-lg font-medium text-sm hover:bg-[#15803D] transition-colors"
        >
          {actionLabel || "Action"}
        </button>
      )}
    </div>
  );
}
