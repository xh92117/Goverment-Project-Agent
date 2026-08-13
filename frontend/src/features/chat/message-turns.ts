import type { StreamAction } from "@/features/chat/api";
import type { LocalMessage } from "@/features/chat/message-utils";

export interface ChatTurn {
  id: string;
  user?: LocalMessage;
  assistantIds: string[];
  assistant?: LocalMessage;
}

function mergeActions(actions: StreamAction[]) {
  const map = new Map<string, StreamAction>();
  for (const action of actions) {
    map.set(action.id, { ...(map.get(action.id) ?? action), ...action });
  }
  return Array.from(map.values());
}

function combineAssistant(messages: LocalMessage[]): LocalMessage | undefined {
  if (messages.length === 0) return undefined;
  return {
    id: messages.map((message) => message.id).join(":"),
    role: "assistant",
    content: messages
      .map((message) => message.content)
      .filter((content) => content.trim())
      .join("\n\n"),
    actions: mergeActions(messages.flatMap((message) => message.actions ?? [])),
  };
}

export function buildTurns(messages: LocalMessage[]): ChatTurn[] {
  const turns: Array<ChatTurn & { assistantMessages: LocalMessage[] }> = [];

  for (const message of messages) {
    if (message.role === "user") {
      const previousTurn = turns.at(-1);
      if (
        previousTurn?.user?.content.trim() === message.content.trim() &&
        previousTurn.assistantMessages.length > 0
      ) {
        previousTurn.assistantIds = [];
        previousTurn.assistantMessages = [];
        continue;
      }
      turns.push({
        id: message.id,
        user: message,
        assistantIds: [],
        assistantMessages: [],
      });
      continue;
    }

    let turn = turns.at(-1);
    if (!turn || (!turn.user && turn.assistantMessages.length > 0)) {
      turn = {
        id: `assistant-${message.id}`,
        assistantIds: [],
        assistantMessages: [],
      };
      turns.push(turn);
    }
    turn.assistantIds.push(message.id);
    turn.assistantMessages.push(message);
  }

  return turns.map(({ assistantMessages, ...turn }) => ({
    ...turn,
    assistant: combineAssistant(assistantMessages),
  }));
}
