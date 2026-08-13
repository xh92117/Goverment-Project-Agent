"use client";

import { useEffect, useState } from "react";

const KEY = "govdecl-theme";

export function useThemeMode() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const initial =
      document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    setTheme(initial);
  }, []);

  function update(next: "light" | "dark") {
    document.documentElement.dataset.theme = next;
    document.documentElement.classList.toggle("dark", next === "dark");
    localStorage.setItem(KEY, next);
    setTheme(next);
  }

  return { theme, setTheme: update, toggleTheme: () => update(theme === "dark" ? "light" : "dark") };
}
