export type Theme = "light" | "dark" | "system";

export function applyTheme(theme: Theme) {
  const resolved =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;
  document.documentElement.dataset.theme = resolved;
  localStorage.setItem("referral-theme", theme);
}

export function initialTheme(): Theme {
  const stored = localStorage.getItem("referral-theme");
  return stored === "light" || stored === "dark" || stored === "system" ? stored : "system";
}
