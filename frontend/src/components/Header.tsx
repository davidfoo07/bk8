"use client";

import { useEffect, useState } from "react";

export default function Header() {
  const [currentTime, setCurrentTime] = useState("");

  useEffect(() => {
    const update = () => {
      const now = new Date();
      const sgt = now.toLocaleString("en-US", {
        timeZone: "Asia/Singapore",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      });
      setCurrentTime(sgt + " SGT");
    };
    update();
    const timer = setInterval(update, 60000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="border-b border-[#1e293b] bg-[#111827] px-6 py-4">
      <div className="flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight text-[#e2e8f0]">
            <span className="text-[#2979FF]">COURT</span>EDGE
          </h1>
          <span className="text-xs px-2 py-0.5 rounded bg-[#2979FF]/20 text-[#2979FF] font-mono">
            v0.1
          </span>
        </div>
        <div className="flex items-center gap-6">
          <nav className="flex gap-4 text-sm">
            <a href="/" className="text-[#e2e8f0] hover:text-[#2979FF] transition-colors">
              Dashboard
            </a>
            <a href="/bets" className="text-[#94a3b8] hover:text-[#2979FF] transition-colors">
              Bet Tracker
            </a>
            <a href="/accuracy" className="text-[#94a3b8] hover:text-[#2979FF] transition-colors">
              Model Accuracy
            </a>
          </nav>
          <span className="text-xs text-[#64748b] font-mono">{currentTime}</span>
        </div>
      </div>
    </header>
  );
}
