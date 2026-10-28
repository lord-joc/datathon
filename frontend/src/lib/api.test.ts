import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet } from "./api";

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

describe("apiGet", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("rejects paths outside /api/", async () => {
    await expect(apiGet("https://evil.example/x")).rejects.toThrow();
  });

  it("returns the body on success", async () => {
    mockFetch(200, { status: "ok" });
    await expect(apiGet("/api/v1/health")).resolves.toEqual({ status: "ok" });
  });

  it("turns problem+json into ApiError", async () => {
    mockFetch(404, { status: 404, code: "NOT_FOUND", detail: "Nema." });
    const error = await apiGet("/api/v1/nope").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).problem.code).toBe("NOT_FOUND");
  });

  it("maps network failures to a readable message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("fail"))),
    );
    const error = await apiGet("/api/v1/status").catch((e: unknown) => e);
    expect((error as ApiError).problem.code).toBe("NETWORK_ERROR");
  });
});
