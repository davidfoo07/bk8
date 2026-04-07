/** Utility functions for CourtEdge frontend. */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind CSS classes with conflict resolution */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Get verdict color class */
export function getVerdictColor(verdict: string): string {
  switch (verdict) {
    case "STRONG BUY":
      return "text-[#00C853]";
    case "BUY":
      return "text-[#4CAF50]";
    case "LEAN":
      return "text-[#FFD600]";
    case "NO EDGE":
      return "text-[#78909C]";
    default:
      return "text-[#78909C]";
  }
}

/** Get verdict background class */
export function getVerdictBg(verdict: string): string {
  switch (verdict) {
    case "STRONG BUY":
      return "bg-[#00C853]/20 text-[#00C853] border-[#00C853]/30";
    case "BUY":
      return "bg-[#4CAF50]/20 text-[#4CAF50] border-[#4CAF50]/30";
    case "LEAN":
      return "bg-[#FFD600]/20 text-[#FFD600] border-[#FFD600]/30";
    case "NO EDGE":
      return "bg-[#78909C]/20 text-[#78909C] border-[#78909C]/30";
    default:
      return "bg-[#78909C]/20 text-[#78909C] border-[#78909C]/30";
  }
}

/** Get NRtg delta indicator */
export function getDeltaIndicator(delta: number): string {
  if (delta > 0.5) return "▲";
  if (delta < -0.5) return "▼";
  return "─";
}

/** Get delta color */
export function getDeltaColor(delta: number): string {
  if (delta > 0.5) return "text-[#4CAF50]";
  if (delta < -0.5) return "text-[#FF1744]";
  return "text-[#78909C]";
}

/** Format percentage */
export function formatPct(value: number, decimals: number = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Format price as Polymarket price */
export function formatPrice(value: number): string {
  return `${(value * 100).toFixed(0)}¢`;
}

/** Format edge with sign */
export function formatEdge(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}%`;
}

/** Format date for SGT display */
export function formatSGT(isoString: string | null): string {
  if (!isoString) return "TBD";
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZone: "Asia/Singapore",
    }) + " SGT";
  } catch {
    return "TBD";
  }
}

/** Format date for ET display */
export function formatET(isoString: string | null): string {
  if (!isoString) return "TBD";
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZone: "America/New_York",
    }) + " ET";
  } catch {
    return "TBD";
  }
}

/** Copy text to clipboard */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for older browsers
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    const success = document.execCommand("copy");
    document.body.removeChild(textarea);
    return success;
  }
}
