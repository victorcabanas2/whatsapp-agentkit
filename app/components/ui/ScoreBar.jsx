export function ScoreBar({ score = 0 }) {
  let color = "#71717A"; // cold
  if (score >= 70) color = "#DC2626"; // hot
  else if (score >= 50) color = "#D97706"; // warm

  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-[#E8E8E5] rounded-full overflow-hidden">
        <div
          className="h-full transition-all duration-300"
          style={{ width: `${Math.min(score, 100)}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-sm font-medium text-[#18181B] min-w-fit">
        {score}
      </span>
    </div>
  );
}
