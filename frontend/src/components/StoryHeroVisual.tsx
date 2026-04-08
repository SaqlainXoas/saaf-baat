import type { StoryCardData } from "@/data/types";
import { capitalise, formatCategory } from "@/utils/storyMeta";

const TONES: Record<string, { background: string; accent: string; chip: string }> = {
  politics: {
    background: "linear-gradient(140deg, #122021 0%, #1e3936 48%, #35695f 100%)",
    accent: "rgba(140, 231, 213, 0.28)",
    chip: "rgba(82, 183, 163, 0.16)",
  },
  security: {
    background: "linear-gradient(140deg, #10171b 0%, #18343a 45%, #21535d 100%)",
    accent: "rgba(96, 188, 209, 0.22)",
    chip: "rgba(82, 183, 163, 0.12)",
  },
  economy: {
    background: "linear-gradient(140deg, #181714 0%, #2e2b24 44%, #575141 100%)",
    accent: "rgba(240, 195, 122, 0.28)",
    chip: "rgba(240, 195, 122, 0.16)",
  },
  city: {
    background: "linear-gradient(140deg, #171719 0%, #29323a 42%, #4a5c65 100%)",
    accent: "rgba(170, 198, 212, 0.25)",
    chip: "rgba(82, 183, 163, 0.14)",
  },
  other: {
    background: "linear-gradient(140deg, #171916 0%, #27312a 44%, #3c5245 100%)",
    accent: "rgba(153, 206, 180, 0.2)",
    chip: "rgba(82, 183, 163, 0.12)",
  },
};

function getTone(category: string) {
  return TONES[category] || TONES.other;
}

export default function StoryHeroVisual({
  story,
  variant = "default",
}: {
  story: StoryCardData;
  variant?: "default" | "compact" | "brief" | "cue";
}) {
  const compact = variant !== "default";
  const isBrief = variant === "brief";
  const isCue = variant === "cue";
  const tone = getTone(story.category);
  const sourceLabel = story.sources.map((source) => capitalise(source.source)).join(" • ");
  const sourceTitle = story.sources.length <= 1 ? "Current reporting" : "Source support";
  const rawTags = story.metadata?.story_tags;
  const storyTags = Array.isArray(rawTags)
    ? rawTags.map((tag) => String(tag)).slice(0, isCue ? 1 : compact ? 1 : 2)
    : [];

  return (
    <div
      className={`relative overflow-hidden border ${
        isCue ? "rounded-[22px] min-h-[148px]" : compact ? "rounded-[24px] aspect-[5/4]" : "rounded-[28px] aspect-[16/9]"
      }`}
      style={{
        aspectRatio: isBrief ? "16 / 11" : isCue ? "5 / 4" : undefined,
        background: tone.background,
        borderColor: "rgba(255,255,255,0.08)",
        boxShadow: isCue ? "0 18px 42px -28px rgba(11, 18, 32, 0.4)" : "0 26px 70px -30px rgba(11, 18, 32, 0.45)",
      }}
    >
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 18% 20%, rgba(255,255,255,0.14), transparent 28%), radial-gradient(circle at 82% 28%, rgba(255,255,255,0.09), transparent 22%), linear-gradient(180deg, rgba(255,255,255,0.04), transparent 48%)",
        }}
      />
      <div
        className={`absolute ${
          isCue ? "inset-y-4 left-4 w-16" : isBrief ? "inset-y-4 left-4 w-20" : "inset-y-6 left-6 w-24"
        } rounded-[22px]`}
        style={{ background: tone.accent, filter: "blur(2px)" }}
      />
      <div
        className={`absolute ${
          isCue ? "right-3 top-3 max-w-[60%] px-3 py-2" : isBrief ? "bottom-4 right-4 px-3 py-2" : "bottom-6 right-6 px-4 py-3"
        } rounded-[20px] border backdrop-blur-sm`}
        style={{
          borderColor: "rgba(255,255,255,0.14)",
          background: "rgba(255,255,255,0.08)",
          color: "rgba(255,255,255,0.92)",
        }}
      >
        <p className="text-[10px] font-bold uppercase tracking-[0.22em] opacity-70">{sourceTitle}</p>
        <p className={`mt-1 ${isCue || isBrief ? "text-xs" : "text-sm"} font-semibold`}>{sourceLabel || "Live brief"}</p>
      </div>
      <div
        className={`absolute ${
          isCue ? "left-3 top-3 gap-1.5 max-w-[58%]" : isBrief ? "left-4 top-4 gap-1.5" : "left-6 top-6 gap-2"
        } flex flex-wrap items-center`}
      >
        <span
          className={`inline-flex items-center rounded-full ${isCue || isBrief ? "px-2.5 py-1" : "px-3 py-1"} text-[10px] font-bold uppercase tracking-[0.2em]`}
          style={{ background: tone.chip, color: "rgba(255,255,255,0.92)" }}
        >
          {formatCategory(story.category)}
        </span>
        {(story.impact_labels || []).slice(0, isCue ? 1 : compact ? 1 : 2).map((label) => (
          <span
            key={label}
            className="inline-flex items-center rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em]"
            style={{ background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.9)" }}
          >
            {label.replace(/^[^\s]+\s+/, "")}
          </span>
        ))}
      </div>
      {storyTags.length ? (
        <div
          className={`absolute ${
            isCue ? "left-3 bottom-3 max-w-[48%]" : isBrief ? "left-4 bottom-4 max-w-[55%]" : "left-6 bottom-6 max-w-[60%]"
          }`}
        >
          {storyTags.map((tag) => (
            <div
              key={tag}
              className={`mb-2 inline-flex rounded-full ${isCue || isBrief ? "px-2.5 py-1 text-[11px]" : "px-3 py-1 text-xs"} font-medium`}
              style={{
                background: "rgba(255,255,255,0.08)",
                color: "rgba(255,255,255,0.88)",
                border: "1px solid rgba(255,255,255,0.08)",
              }}
            >
              {tag}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
