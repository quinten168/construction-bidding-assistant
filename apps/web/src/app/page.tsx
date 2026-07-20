import { ChatApp } from "@/components/chat/chat-app";

// The entire product is the chat. ChatApp owns the single top bar (brand + title +
// usage), so the canvas gets a clean, Claude-style full-height reading surface.
export default function Page() {
  return (
    <div className="relative flex h-screen flex-col">
      <div className="ambient-mesh" />
      <ChatApp />
    </div>
  );
}
