"use client";

import { useEffect, useState } from "react";
import { getQueueDepth } from "@/lib/api";
import { Activity } from "lucide-react";

export function QueueDepthBadge() {
  const [depth, setDepth] = useState<number | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const data = await getQueueDepth();
        setDepth(data.depth);
      } catch { /* ignore */ }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  if (depth === null) return null;

  return (
    <div className="flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-600 shadow-sm">
      <Activity className="h-3.5 w-3.5 text-brand-500" />
      <span>{depth} in queue</span>
    </div>
  );
}
