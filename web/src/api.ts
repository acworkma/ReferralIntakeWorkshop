import type { Delivery, Health, Identity, Referral } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

function describeStatus(response: Response): string {
  // statusText is always empty over HTTP/2, so never rely on it alone.
  return response.statusText
    ? `${response.status} ${response.statusText}`
    : String(response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      redirect: "manual",
      credentials: "same-origin",
    });
  } catch (reason) {
    console.error(`Network error calling ${path}`, reason);
    throw new Error("Network error: the request could not be sent. Check your connection and try again.");
  }

  if (response.type === "opaqueredirect" || response.status === 0) {
    console.warn(`Request to ${path} was redirected (likely an expired sign-in session). Reloading.`);
    window.location.reload();
    throw new Error("Your session has expired. Reloading to sign in again.");
  }

  // 204 responses carry no body and no content-type, so settle them first.
  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await response.text().catch(() => "");
    console.error(`Unexpected non-JSON response from ${path}`, response.status, text.slice(0, 500));
    if (response.status === 403) {
      throw new Error(
        "Request rejected (403). Your sign-in session may be stale - refresh the page and try again.",
      );
    }
    throw new Error(
      response.ok
        ? "Unexpected response from the server. Try refreshing the page."
        : `Request failed (${describeStatus(response)}).`,
    );
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail.trim() : "";
    throw new Error(detail || `Request failed (${describeStatus(response)}).`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  me: () => request<Identity>("/api/me"),
  list: () => request<Referral[]>("/api/referrals"),
  /**
   * Stands in for an upstream system delivering a document. This only writes to
   * the landing zone; the workflow that picks it up is triggered by the write.
   */
  deliver: (file: File) => {
    const body = new FormData();
    body.append("document", file);
    return request<Delivery>("/api/referrals", {
      method: "POST",
      body,
    });
  },
  review: (id: string, approved: boolean, note: string) => {
    const query = new URLSearchParams({ approved: String(approved), note });
    return request<Referral>(`/api/referrals/${id}/review?${query}`, { method: "POST" });
  },
  remove: (id: string) => request<void>(`/api/referrals/${id}`, { method: "DELETE" }),
};
