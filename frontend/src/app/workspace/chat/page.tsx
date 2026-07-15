import { Suspense } from "react";

import { ChatPage } from "@/features/chat/chat-page";

export default function Page() {
  return (
    <Suspense fallback={<div className="workspace-loading">正在打开对话...</div>}>
      <ChatPage />
    </Suspense>
  );
}
