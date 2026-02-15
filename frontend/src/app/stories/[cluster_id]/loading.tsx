export default function StoryLoading() {
  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="bg-ambient" />
      <div className="relative sb-container px-4 py-6 space-y-4">
        <div className="sb-skeleton h-7 w-32" />
        <div className="sb-skeleton h-72 w-full rounded-[26px]" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="sb-skeleton h-40 w-full rounded-[22px]" />
          <div className="sb-skeleton h-40 w-full rounded-[22px]" />
        </div>
        <div className="sb-skeleton h-56 w-full rounded-[22px]" />
      </div>
    </div>
  );
}
