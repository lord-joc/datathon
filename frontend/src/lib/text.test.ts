import { describe, expect, it } from "vitest";

import { matchScore, normalize } from "./text";

describe("normalize", () => {
  it("ignores case, diacritics and leading zeros in house numbers", () => {
    expect(normalize("TRG ANTE STARČEVIĆA 0007")).toBe("trg ante starcevica 7");
    expect(normalize("Đorđićeva 0003/B")).toBe("dordiceva 3 b");
  });
  it("keeps numbers that are not house numbers", () => {
    expect(normalize("ID 4763")).toBe("id 4763");
  });
});

describe("matchScore", () => {
  const words = (t: string) => normalize(t).split(" ");
  it("matches word prefixes, not text inside numbers", () => {
    expect(matchScore(words("vlaška 8"), words("VLAŠKA 0089 Gornji grad 3991"))).toBeGreaterThan(0);
    expect(matchScore(words("vlaška 8"), words("VLAŠKA 0096 Donji grad 4008"))).toBe(0);
  });
  it("ranks an exact word above a prefix", () => {
    const exact = matchScore(words("ilica 34"), words("ILICA 0034"));
    const prefix = matchScore(words("ilica 3"), words("ILICA 0034"));
    expect(exact).toBeGreaterThan(prefix);
  });
});
