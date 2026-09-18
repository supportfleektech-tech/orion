import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { VoiceProvider } from "./components/VoiceControl";
import { Topbar } from "./components/Topbar";
import { Dashboard } from "./pages/Dashboard";
import { Chat } from "./pages/Chat";
import { Memory } from "./pages/Memory";
import { Knowledge } from "./pages/Knowledge";
import { Tools } from "./pages/Tools";
import { Automations } from "./pages/Automations";
import { Security } from "./pages/Security";
import { Observability } from "./pages/Observability";
import { Settings } from "./pages/Settings";
import { Models } from "./pages/Models";
import { Skills } from "./pages/Skills";

export default function App() {
  return (
    <BrowserRouter>
      <VoiceProvider>
      <div className="app-shell">
        <Sidebar />
        <main className="main">
          <Topbar />
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/memory" element={<Memory />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/automations" element={<Automations />} />
            <Route path="/security" element={<Security />} />
            <Route path="/observability" element={<Observability />} />
            <Route path="/models" element={<Models />} />
            <Route path="/skills" element={<Skills />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      </VoiceProvider>
    </BrowserRouter>
  );
}
