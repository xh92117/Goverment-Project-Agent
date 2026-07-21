import { describe, expect, it, vi } from "vitest";

import { apiFetch, apiJson, apiUrl, ApiError } from "@/shared/api/client";

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

  it("extracts structured backend error messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code: "email_already_exists", message: "Email already registered" } }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const error = await apiJson("/api/v1/auth/register").catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 400, message: "Email already registered" });
  });
});
