export default function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="text-6xl mb-4">🏀</div>
      <h2 className="text-xl font-semibold text-[#e2e8f0] mb-2">No Games Today</h2>
      <p className="text-sm text-[#94a3b8] max-w-md">
        There are no NBA games scheduled for today, or data hasn&apos;t loaded yet.
        Check back later or verify your API connection.
      </p>
    </div>
  );
}
