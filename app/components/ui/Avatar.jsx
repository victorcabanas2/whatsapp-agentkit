export function Avatar({ name, size = "sm" }) {
  const initials = (name || "?")
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  const sizeClass = {
    sm: "w-8 h-8 text-xs",
    md: "w-10 h-10 text-sm",
    lg: "w-12 h-12 text-base",
  }[size];

  const colors = [
    "bg-red-200 text-red-800",
    "bg-blue-200 text-blue-800",
    "bg-green-200 text-green-800",
    "bg-yellow-200 text-yellow-800",
    "bg-purple-200 text-purple-800",
  ];

  const hash = name
    ? name.charCodeAt(0) + name.charCodeAt(name.length - 1)
    : 0;
  const colorClass = colors[hash % colors.length];

  return (
    <div
      className={`${sizeClass} ${colorClass} rounded-full flex items-center justify-center font-semibold`}
    >
      {initials}
    </div>
  );
}
