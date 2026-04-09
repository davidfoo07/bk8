"use client";

import type { TopEdge } from "@/types/api";
import { getVerdictBg, formatEdge, formatPrice } from "@/lib/utils";

interface TopEdgesProps {
  edges: TopEdge[];
  onEdgeClick?: (gameId: string) => void;
}

export default function TopEdges({ edges, onEdgeClick }: TopEdgesProps) {
  if (edges.length === 0) return null;

  return (
    <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4 mb-6">
      <h2 className="text-sm font-semibold text-[#94a3b8] uppercase tracking-wider mb-3">
        Top Edges
      </h2>
      <div className="flex flex-wrap gap-3">
        {edges.slice(0, 5).map((edge, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onEdgeClick?.(edge.game_id)}
            className="flex items-center gap-2 px-3 py-2 rounded-md bg-[#1a2235] border border-[#1e293b] hover:border-[#334155] hover:bg-[#1e293b] transition-colors cursor-pointer text-left"
          >
            <span
              className={`text-xs px-2 py-0.5 rounded border font-semibold ${getVerdictBg(edge.verdict)}`}
            >
              {edge.verdict}
            </span>
            <span className="text-sm text-[#e2e8f0] font-medium">
              {edge.selection}
            </span>
            <span className="text-xs text-[#94a3b8] font-mono">
              @ {formatPrice(edge.price)}
            </span>
            <span className="text-xs text-[#4CAF50] font-mono font-semibold">
              {formatEdge(edge.edge)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
