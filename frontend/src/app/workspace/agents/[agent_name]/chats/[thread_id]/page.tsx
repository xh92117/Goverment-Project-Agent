import { redirect } from "next/navigation";

export default async function LegacyChatPage({
  params,
}: Readonly<{ params: Promise<{ thread_id: string }> }>) {
  const { thread_id: threadId } = await params;
  const query = threadId && threadId !== "new" ? `?thread=${encodeURIComponent(threadId)}` : "";
  redirect(`/workspace/chat${query}`);
}
