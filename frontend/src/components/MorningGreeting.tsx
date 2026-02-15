"use client";

import { useEffect, useState } from "react";
import FocusControl from "@/components/FocusControl";
import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";

export default function MorningGreeting({
  storyCount,
  availableSources = [],
}: {
  storyCount: number;
  availableSources?: string[];
}) {
  const greeting = "Subah Bakhair";
  const city = process.env.NEXT_PUBLIC_CITY_NAME || "Islamabad";
  const [dateStr, setDateStr] = useState("");

  useEffect(() => {
    const now = new Date();
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    setDateStr(`${days[now.getDay()]}, ${months[now.getMonth()]} ${now.getDate()}`);
  }, []);

  return (
    <header className="px-2 pt-3 pb-1">
      <div className="flex items-start justify-between">
        <h1
          className="text-2xl font-bold tracking-tight leading-tight"
          style={{ color: "var(--ink)" }}
        >
          {greeting},<br />
          {city}.
        </h1>
        <Logo size={22} decorative className="mt-1" />
      </div>

      <div className="flex items-center justify-between gap-3 mt-2">
        <div className="flex items-center gap-2 flex-wrap text-xs" style={{ color: "var(--ink-muted)" }}>
          <span>{dateStr || "Today"}</span>
          <span className="w-1 h-1 rounded-full" style={{ background: "var(--ink-muted)" }} />
          <span>Your {storyCount} essential stories</span>
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          {availableSources.length ? <FocusControl availableSources={availableSources} size="sm" /> : null}
        </div>
      </div>
    </header>
  );
}
