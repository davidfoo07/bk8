"use client";

import Header from "@/components/Header";

export default function ModelAccuracy() {
  return (
    <div className="min-h-screen bg-[#0a0e17]">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-6">
        <h1 className="text-xl font-bold text-[#e2e8f0] mb-6">Model Accuracy</h1>

        <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-8 text-center">
          <p className="text-[#94a3b8] mb-4">
            Model accuracy tracking requires 50+ resolved bets.
          </p>
          <p className="text-sm text-[#64748b]">
            Once you&apos;ve placed enough bets, this page will show:
          </p>
          <ul className="text-sm text-[#64748b] mt-3 space-y-1">
            <li>Calibration curve (predicted vs actual outcomes)</li>
            <li>ROI by edge threshold</li>
            <li>ROI by market type (spread vs moneyline vs total)</li>
            <li>Running P&L chart over time</li>
          </ul>
        </div>

        {/* Placeholder charts */}
        <div className="grid grid-cols-2 gap-6 mt-6">
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4 h-64 flex items-center justify-center">
            <span className="text-[#64748b] text-sm">Calibration Curve — Coming soon</span>
          </div>
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4 h-64 flex items-center justify-center">
            <span className="text-[#64748b] text-sm">P&L Over Time — Coming soon</span>
          </div>
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4 h-64 flex items-center justify-center">
            <span className="text-[#64748b] text-sm">ROI by Edge Threshold — Coming soon</span>
          </div>
          <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-4 h-64 flex items-center justify-center">
            <span className="text-[#64748b] text-sm">ROI by Market Type — Coming soon</span>
          </div>
        </div>
      </main>
    </div>
  );
}
