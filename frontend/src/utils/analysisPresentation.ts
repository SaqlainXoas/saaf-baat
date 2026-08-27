/**
 * Presentation helpers for the detail page's analysis block.
 *
 * The detail page used to render `story.analysis || story.snippet` under a
 * fixed "Analysis" heading, so a card whose analysis was rejected showed one
 * publisher's unattributed wire lede, cut mid-sentence, labelled as the
 * multi-source analysis. Nothing told the reader the analysis was missing.
 */

/** Publisher slugs the analysis attributes something to. */
const PUBLISHER_ALIASES: Record<string, string[]> = {
  app: ["APP", "Associated Press of Pakistan"],
  ary: ["ARY"],
  brecorder: ["Brecorder", "Business Recorder"],
  dawn: ["Dawn"],
  geo: ["Geo"],
  nation: ["Nation"],
  thenews: ["The News"],
  tribune: ["Tribune", "Express Tribune"],
};

const REPORTING_CUE =
  "(?:reports?|reported|reporting|says?|said|writes?|wrote|notes?|noted|carry|carries|carried|adds?|added|quotes?|quoted|describes?|described|confirms?|confirmed)";

/**
 * Which publishers the analysis names, matched the same way the backend
 * validator matches them: the published casing next to a reporting verb, or
 * behind "according to". A bare lowercase word is prose, not an attribution.
 */
export function publishersNamedInAnalysis(analysis: string | null | undefined): string[] {
  const text = analysis || "";
  if (!text) return [];
  const named = new Set<string>();
  for (const [slug, aliases] of Object.entries(PUBLISHER_ALIASES)) {
    for (const alias of aliases) {
      const escaped = alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const cued = new RegExp(`\\b${escaped}\\b\\W+(?:\\w+\\W+){0,2}${REPORTING_CUE}\\b`);
      const attributed = new RegExp(`\\baccording to\\s+(?:the\\s+)?${escaped}\\b`, "i");
      if (cued.test(text) || attributed.test(text)) {
        named.add(slug);
        break;
      }
    }
  }
  return [...named];
}

/**
 * A period is not always a full stop. This corpus is full of "Sept. 16",
 * "Dr. Uzma Khan" and "Rs. 30m"; splitting naively on `[.!?]` put a paragraph
 * break between "Dr." and the name after it. Mirrors `src/utils/text.py`.
 */
const ABBREVIATIONS = new Set([
  "approx", "apr", "aug", "capt", "co", "col", "dec", "dept", "dr", "eng",
  "etc", "feb", "fig", "gen", "gov", "hon", "inc", "jan", "jr", "jul", "jun",
  "lt", "ltd", "maj", "mar", "mr", "mrs", "ms", "no", "nov", "oct", "prof",
  "pvt", "rev", "rs", "sept", "sep", "sgt", "sr", "st", "vs",
]);

export function splitSentences(text: string): string[] {
  const clean = (text || "").trim();
  if (!clean) return [];

  const sentences: string[] = [];
  const boundary = /([.!?]+)(\s+)/g;
  let start = 0;
  let match: RegExpExecArray | null;

  while ((match = boundary.exec(clean)) !== null) {
    const periodEnd = match.index + match[1].length;
    const following = clean[match.index + match[0].length] || "";
    if (following && (following.toLowerCase() === following && /[a-z0-9]/.test(following))) {
      continue;
    }
    const beforePeriod = clean.slice(start, match.index);
    const trailing = /([A-Za-z]+)$/.exec(beforePeriod);
    if (trailing && (ABBREVIATIONS.has(trailing[1].toLowerCase()) || trailing[1].length === 1)) {
      continue;
    }
    const piece = clean.slice(start, periodEnd).trim();
    if (piece) sentences.push(piece);
    start = match.index + match[0].length;
  }

  const tail = clean.slice(start).trim();
  if (tail) sentences.push(tail);
  return sentences;
}

/**
 * Split the analysis into readable paragraphs. A 900-character block exceeds a
 * full 390px viewport in one unbroken run; the prompt does not ask for
 * paragraph breaks, so they are made here from sentence groups.
 *
 * Balanced by construction rather than by fixed groups of three: grouping in
 * threes left a one-sentence tail, and the guard against that merged it back
 * so that a four-sentence analysis rendered as one paragraph again.
 */
export function toAnalysisParagraphs(text: string): string[] {
  const clean = (text || "").trim().replace(/\s+/g, " ");
  if (!clean) return [];

  const sentences = splitSentences(clean);
  if (sentences.length <= 3) return [clean];

  const groups = sentences.length >= 7 ? 3 : 2;
  const perGroup = Math.ceil(sentences.length / groups);
  const paragraphs: string[] = [];
  for (let index = 0; index < sentences.length; index += perGroup) {
    const chunk = sentences.slice(index, index + perGroup).join(" ").trim();
    if (chunk) paragraphs.push(chunk);
  }
  return paragraphs;
}
