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

interface RequestOptions {
  signal?: AbortSignal | undefined;
  method?: "GET" | "POST";
  body?: unknown;
  headers?: Record<string, string>;
}

async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!path.startsWith("/api/")) throw new Error("API putanja mora počinjati s /api/");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  options.signal?.addEventListener("abort", () => controller.abort());
  const method = options.method ?? "GET";
  try {
    const response = await fetch(path, {
      method,
      headers: {
        Accept: "application/json",
        ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
      credentials: "same-origin",
      signal: controller.signal,
      ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      // /status returns 503 with a normal body when the database is down.
      if (
        method === "GET" &&
        response.status === 503 &&
        body &&
        typeof body === "object" &&
        "status" in body &&
        !("code" in body)
      ) {
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

export function apiGet<T>(
  path: string,
  init?: { signal?: AbortSignal; headers?: Record<string, string> },
): Promise<T> {
  return apiRequest<T>(path, { ...init });
}

export function apiPost<T>(path: string, body: unknown, init?: { signal?: AbortSignal }) {
  return apiRequest<T>(path, { ...init, method: "POST", body });
}

function toProblem(status: number, body: unknown): Problem {
  if (body && typeof body === "object" && "code" in body && "detail" in body) {
    return { ...(body as Problem), status };
  }
  return { status, code: "HTTP_ERROR", detail: "Zahtjev nije uspio." };
}

/** Readable message for any error thrown by a query or mutation. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.problem.detail;
  return "Nešto je pošlo po zlu. Pokušajte ponovno.";
}
