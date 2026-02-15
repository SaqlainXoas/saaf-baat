export default function Loading() {
  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="bg-ambient" />
      <div className="relative sb-container px-4 py-5 space-y-4">
        <div className="sb-skeleton h-10 w-56" />
        <div className="sb-skeleton h-56 w-full rounded-[26px]" />
        <div className="sb-skeleton h-36 w-full rounded-[26px]" />
        <div className="sb-skeleton h-36 w-full rounded-[26px]" />
      </div>
    </div>
  );
}
