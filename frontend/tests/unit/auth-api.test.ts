import { afterEach, describe, expect, it, vi } from "vitest";

import { loginLocal, registerLocal } from "@/features/auth/api";
import { ApiError } from "@/shared/api/client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("auth api", () => {
  it("registers a regular user with the backend JSON contract", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ id: "user-1", email: "member@example.com", system_role: "user" }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(registerLocal({ email: "member@example.com", password: "Secure2026" })).resolves.toMatchObject({
      id: "user-1",
      system_role: "user",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/register",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "member@example.com", password: "Secure2026" }),
        credentials: "include",
      }),
    );
  });

  it("surfaces the backend nested error message on login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code: "invalid_credentials", message: "Incorrect email or password" } }),
          { status: 401, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const error = await loginLocal("member@example.com", "wrong-password").catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, message: "Incorrect email or password" });
  });
});
