import clsx from "clsx";

interface Props {
  label: string;
  value: number; // 0–1
}

function color(v: number) {
  if (v >= 0.75) return "bg-green-500";
  if (v >= 0.50) return "bg-yellow-400";
  return "bg-red-400";
}

export function ScoreBar({ label, value }: Props) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-36 shrink-0 text-sm text-gray-600">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={clsx("h-full rounded-full transition-all", color(value))}
          style={{ width: `${value * 100}%` }}
        />
      </div>
      <span className="w-10 text-right text-sm font-medium text-gray-700">
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}
