import type { Identity, Referral } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, init);
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
      headers: { "X-Data-Classification": "synthetic" },
      body,
    });
  },
  review: (id: string, approved: boolean, note: string) => {
    const query = new URLSearchParams({ approved: String(approved), note });
    return request<Referral>(`/api/referrals/${id}/review?${query}`, { method: "POST" });
  },
};
