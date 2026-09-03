import { applyTheme, initialTheme } from "./theme";

describe("theme", () => {
  beforeEach(() => localStorage.clear());

  it("persists and applies an explicit theme", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(initialTheme()).toBe("dark");
  });
});
