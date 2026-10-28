/**
 * Minimal API client. Same-origin only; errors follow RFC 9457 problem+json.
 */

export interface Problem {
  status: number;
  code: string;
  detail: string;
  request_id?: string;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly problem: Problem;
  constructor(problem: Problem) {
    super(problem.detail);
    this.name = "ApiError";
    this.problem = problem;
  }
}

const DEFAULT_TIMEOUT_MS = 10_000;

export async function apiGet<T>(path: string, init?: { signal?: AbortSignal }): Promise<T> {
  if (!path.startsWith("/api/")) throw new Error("API putanja mora počinjati s /api/");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  init?.signal?.addEventListener("abort", () => controller.abort());
  try {
    const response = await fetch(path, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      signal: controller.signal,
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      // /status returns 503 with a normal body when the database is down.
      if (response.status === 503 && body && typeof body === "object" && "status" in body) {
        return body as T;
      }
      throw new ApiError(toProblem(response.status, body));
    }
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      detail: "Poslužitelj nije dostupan. Provjerite vezu i pokušajte ponovno.",
    });
  } finally {
    clearTimeout(timeout);
  }
}

function toProblem(status: number, body: unknown): Problem {
  if (body && typeof body === "object" && "code" in body && "detail" in body) {
    return body as Problem;
  }
  return { status, code: "HTTP_ERROR", detail: "Zahtjev nije uspio." };
}
