import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";

/**
 * Error handling in the API client.
 *
 * These are the messages a user sees when something is wrong, which is
 * precisely when a vague message costs the most. Each case asserts the text
 * tells them what to do, not just that it failed.
 */

function mockFetch(impl: typeof fetch) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("request", () => {
  it("returns the parsed body on success", async () => {
    mockFetch(async () => jsonResponse({ connected: 2, total: 5, connectors: [], local_only: false }));
    await expect(api.connectors()).resolves.toMatchObject({ connected: 2 });
  });

  it("explains how to start the backend when it is unreachable", async () => {
    // fetch rejects only when the request never reached a server.
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(api.status()).rejects.toThrow(/Cannot reach the ORION backend/);
    await expect(api.status()).rejects.toThrow(/run-backend/);
  });

  it("keeps the original failure as the cause, so debugging is still possible", async () => {
    const underlying = new TypeError("Failed to fetch");
    mockFetch(async () => {
      throw underlying;
    });

    await expect(api.status()).rejects.toMatchObject({ cause: underlying });
  });

  it("names the auth setting on 401 rather than saying 'unauthorized'", async () => {
    mockFetch(async () => new Response("", { status: 401 }));
    await expect(api.status()).rejects.toThrow(/ORION_AUTH_TOKEN/);
  });

  it("treats 403 the same way", async () => {
    mockFetch(async () => new Response("", { status: 403 }));
    await expect(api.status()).rejects.toThrow(/AUTH_ENABLED/);
  });

  it("points at the logs on a server error", async () => {
    mockFetch(async () => new Response("<html>500</html>", { status: 500 }));
    await expect(api.status()).rejects.toThrow(/HTTP 500.*logs/s);
  });

  it("prefers the backend's own explanation when it gives one", async () => {
    mockFetch(async () => jsonResponse({ detail: "Database is locked" }, 503));
    await expect(api.status()).rejects.toThrow("Database is locked");
  });

  it("surfaces a 4xx detail verbatim, because it is usually actionable", async () => {
    mockFetch(async () => jsonResponse({ detail: "Path escapes the knowledge directory" }, 400));
    await expect(api.ingestPath("../../etc/passwd")).rejects.toThrow(
      "Path escapes the knowledge directory",
    );
  });

  it("falls back to the status text when a 4xx has no JSON body", async () => {
    mockFetch(async () => new Response("nope", { status: 404, statusText: "Not Found" }));
    await expect(api.status()).rejects.toThrow(/Not Found|nope/);
  });

  it("handles a 204 with no body", async () => {
    mockFetch(async () => new Response(null, { status: 204 }));
    await expect(api.deleteMemory("abc")).resolves.toBeUndefined();
  });

  it("sends JSON content-type for object bodies but not for uploads", async () => {
    const calls: RequestInit[] = [];
    mockFetch(async (_url, init) => {
      calls.push(init as RequestInit);
      return jsonResponse({});
    });

    await api.killSwitch(true, "test");
    expect((calls[0].headers as Record<string, string>)["Content-Type"]).toBe("application/json");

    const file = new File(["hi"], "a.txt", { type: "text/plain" });
    await api.inspectAttachment(file);
    // FormData must set its own boundary; forcing a content-type breaks it.
    expect((calls[1].headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });
});
