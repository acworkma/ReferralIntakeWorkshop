import type { Identity, Referral } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

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

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await response.text().catch(() => "");
    console.error(`Unexpected non-JSON response from ${path}`, response.status, text.slice(0, 500));
    throw new Error(
      response.ok
        ? "Unexpected response from the server. Try refreshing the page."
        : `Request failed (${response.status} ${response.statusText}).`,
    );
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? "Request failed.");
  }
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<Identity>("/api/me"),
  list: () => request<Referral[]>("/api/referrals"),
  upload: (file: File) => {
    const body = new FormData();
    body.append("document", file);
    return request<Referral>("/api/referrals", {
      method: "POST",
      body,
    });
  },
  review: (id: string, approved: boolean, note: string) => {
    const query = new URLSearchParams({ approved: String(approved), note });
    return request<Referral>(`/api/referrals/${id}/review?${query}`, { method: "POST" });
  },
};
