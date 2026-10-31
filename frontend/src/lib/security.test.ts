import { describe, expect, it } from "vitest";

// TN03 / master prompt §8: text from sources is always rendered as text, never as HTML.
const files = import.meta.glob<string>(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
});

describe("no raw HTML sinks", () => {
  it("never uses innerHTML, outerHTML, document.write or eval", () => {
    const sinks =
      /dangerouslySetInnerHTML|\.innerHTML|\.outerHTML|document\.write|\beval\(|new Function\(/;
    const entries = Object.entries(files);
    expect(entries.length).toBeGreaterThan(20);
    expect(entries.filter(([, body]) => sinks.test(body)).map(([path]) => path)).toEqual([]);
  });
});
