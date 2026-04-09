"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export default function Header() {
  const [currentTime, setCurrentTime] = useState("");
  const pathname = usePathname();

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

  const navLinks = [
    { href: "/", label: "Dashboard" },
    { href: "/history", label: "History" },
    { href: "/bets", label: "Bet Tracker" },
    { href: "/simulation", label: "Simulation" },
    { href: "/accuracy", label: "Model Accuracy" },
  ];

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
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className={`hover:text-[#2979FF] transition-colors ${
                  pathname === link.href ? "text-[#e2e8f0]" : "text-[#94a3b8]"
                }`}
              >
                {link.label}
              </a>
            ))}
          </nav>
          <span className="text-xs text-[#64748b] font-mono">{currentTime}</span>
        </div>
      </div>
    </header>
  );
}
