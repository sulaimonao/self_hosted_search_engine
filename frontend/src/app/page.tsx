import { WebPreview } from "@/components/web-preview";
import { ChatPanel } from "@/components/chat-panel";

export default function Home() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 h-screen bg-background">
      <div className="col-span-1">
        <WebPreview />
      </div>
      <div className="col-span-1 flex flex-col">
        <ChatPanel />
      </div>
    </div>
  );
}