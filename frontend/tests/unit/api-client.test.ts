import { describe, expect, it, vi } from "vitest";

import { apiFetch, apiUrl } from "@/shared/api/client";

describe("api client", () => {
  it("uses relative gateway paths by default", () => {
    expect(apiUrl("/api/models")).toBe("/api/models");
  });

  it("adds credentials to every request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/models");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/models",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});
