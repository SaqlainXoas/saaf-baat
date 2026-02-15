export const IMPACT_LABELS = [
  "WALLET",
  "COMMUTE",
  "SAFETY",
  "WORK",
  "UTILITIES",
  "GOVERNANCE",
] as const;

export type ImpactLabel = (typeof IMPACT_LABELS)[number];

const LABEL_SET = new Set<string>(IMPACT_LABELS);

/** Strip emoji/prefixes and normalise to a known label; returns "UPDATE" as fallback. */
export function normaliseImpact(raw: string): ImpactLabel | "UPDATE" {
  if (!raw) return "UPDATE";
  for (const label of IMPACT_LABELS) {
    if (raw.includes(label)) return label;
  }
  const upper = raw.trim().toUpperCase();
  if (LABEL_SET.has(upper)) return upper as ImpactLabel;
  return "UPDATE";
}

