import { ScrollArea } from "@/components/ui/scroll-area";

const messages = [
  { id: 1, author: "System", content: "Thread bootstrapped from the current tab." },
  { id: 2, author: "You", content: "Summarize this page and tell me what to do next." },
  {
    id: 3,
    author: "Copilot",
    content: "The page outlines recent crawling activity. I can highlight anomalous jobs or open related sessions.",
  },
];

export function ChatMessageList() {
  return (
    <ScrollArea className="flex-1 rounded-xl border bg-background p-3">
      <div className="space-y-3 text-sm">
        {messages.map((message) => (
          <div key={message.id}>
            <p className="font-medium text-primary">{message.author}</p>
            <p className="text-muted-foreground">{message.content}</p>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
