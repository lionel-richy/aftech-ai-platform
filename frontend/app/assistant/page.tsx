import { Topbar } from "@/components/layout/Topbar";
import { ChatView } from "@/components/assistant/ChatView";

export default function AssistantPage() {
  return (
    <>
      <Topbar title="Assistant IA" description="Posez une question sur les documents indexés." />
      <main className="flex-1 overflow-hidden">
        <ChatView />
      </main>
    </>
  );
}
