/** Text helpers shared by search and filters. */

/** Lower case, no diacritics, house numbers without leading zeros ("0007" -> "7"). */
export function normalize(text: string): string {
  return text
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/\b0+(\d)/g, "$1")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

/**
 * Every query word must start one of the words of the text ("vla 8" finds "Vlaška 81",
 * not "Vlaška 96" of space 4008). Returns a score: higher is better, 0 means no match.
 */
export function matchScore(queryWords: string[], textWords: string[]): number {
  if (queryWords.length === 0) return 0;
  let score = 0;
  for (const q of queryWords) {
    let best = 0;
    for (const t of textWords) {
      if (t === q) best = 2;
      else if (best < 1 && t.startsWith(q)) best = 1;
    }
    if (best === 0) return 0;
    score += best;
  }
  return score;
}
