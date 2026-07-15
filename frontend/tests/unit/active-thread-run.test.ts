import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearThreadRun,
  getThreadRunSnapshot,
  startThreadRun,
  stopThreadRun,
  subscribeThreadRun,
} from "@/features/chat/active-thread-run";
import { cancelRun, streamRun } from "@/features/chat/api";

vi.mock("@/features/chat/api", () => ({
  cancelRun: vi.fn(),
  streamRun: vi.fn(),
}));

const streamRunMock = vi.mocked(streamRun);
const cancelRunMock = vi.mocked(cancelRun);

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("active thread run store", () => {
  beforeEach(() => {
    clearThreadRun("thread-1");
    vi.clearAllMocks();
    cancelRunMock.mockResolvedValue({ run_id: "run-stop", thread_id: "thread-1", status: "cancelled" });
  });

  it("keeps receiving stream output after the page unsubscribes", async () => {
    let onText: ((chunk: string) => void) | undefined;
    let finishStream: (() => void) | undefined;

    streamRunMock.mockImplementation(async (options) => {
      onText = options.onText;
      options.onRunId?.("run-1");
      await new Promise<void>((resolve) => {
        finishStream = resolve;
      });
    });

    const updates: string[] = [];
    const unsubscribe = subscribeThreadRun("thread-1", () => {
      updates.push(getThreadRunSnapshot("thread-1")?.messages.at(-1)?.content ?? "");
    });

    startThreadRun({
      threadId: "thread-1",
      content: "question",
      assistantId: "assistant-1",
      messages: [
        { id: "user-1", role: "user", content: "question" },
        { id: "assistant-1", role: "assistant", content: "" },
      ],
    });

    onText?.("partial ");
    unsubscribe();
    onText?.("after route change");

    expect(getThreadRunSnapshot("thread-1")?.messages.at(-1)?.content).toBe(
      "partial after route change",
    );
    expect(updates).toContain("partial ");

    finishStream?.();
    await flushPromises();
    expect(getThreadRunSnapshot("thread-1")?.status).toBe("success");
  });

  it("cancels the active backend run from the shared store", async () => {
    streamRunMock.mockImplementation(async (options) => {
      options.onRunId?.("run-stop");
      await new Promise<void>((_resolve, reject) => {
        options.signal?.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      });
    });

    startThreadRun({
      threadId: "thread-1",
      content: "question",
      assistantId: "assistant-1",
      messages: [
        { id: "user-1", role: "user", content: "question" },
        { id: "assistant-1", role: "assistant", content: "" },
      ],
    });

    await stopThreadRun("thread-1");

    expect(cancelRunMock).toHaveBeenCalledWith("thread-1", "run-stop");
    expect(getThreadRunSnapshot("thread-1")?.status).toBe("cancelled");
  });
});
