import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("api request handling", () => {
  const originalFetch = globalThis.fetch;
  const originalReload = window.location.reload;

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload: vi.fn() },
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload: originalReload },
    });
    vi.restoreAllMocks();
  });

  it("returns parsed JSON on a normal successful response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      jsonResponse({ displayName: "Reviewer", localMock: false }),
    );
    const identity = await api.me();
    expect(identity.displayName).toBe("Reviewer");
  });

  it("reloads the page and throws when the session redirects to sign-in", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      type: "opaqueredirect",
      status: 0,
      ok: false,
      headers: new Headers(),
    } as unknown as Response);

    await expect(api.list()).rejects.toThrow(/session has expired/i);
    expect(window.location.reload).toHaveBeenCalledOnce();
  });

  it("surfaces a clear error when the server returns non-JSON (e.g. an HTML login page)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("<html>sign in</html>", {
        status: 200,
        headers: { "content-type": "text/html" },
      }),
    );
    await expect(api.list()).rejects.toThrow(/unexpected response/i);
  });

  it("explains a 403 from the auth layer instead of failing silently", async () => {
    // Easy Auth rejects with an empty, non-JSON body and no statusText over HTTP/2.
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response("", { status: 403, statusText: "" }),
    );
    await expect(api.list()).rejects.toThrow(/403/);
  });

  it("never throws an empty message when the error body has no detail", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      jsonResponse({ detail: "" }, { status: 500, statusText: "" }),
    );
    await expect(api.list()).rejects.toThrow(/request failed \(500\)/i);
  });

  it("surfaces the server-provided detail message on a JSON error response", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      jsonResponse({ detail: "File must be between 1 byte and 10 bytes." }, { status: 413 }),
    );
    await expect(api.list()).rejects.toThrow("File must be between 1 byte and 10 bytes.");
  });

  it("surfaces a network error when fetch itself rejects", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(api.list()).rejects.toThrow(/network error/i);
  });
});
