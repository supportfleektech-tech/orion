import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar } from "./components/Sidebar";
import { VoiceProvider } from "./components/VoiceControl";
import { CommandPalette } from "./components/CommandPalette";
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
import { Mcp } from "./pages/Mcp";
import { Evaluation } from "./pages/Evaluation";
import { pageVariants } from "./lib/motion";

/**
 * Routes, wrapped so each page crossfades instead of snapping.
 *
 * `mode="wait"` lets the outgoing page finish leaving before the next enters;
 * with both on screen at once the layout jumps. Keyed on pathname so only a
 * real navigation triggers it, not a query-string change.
 */
function AnimatedRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname}
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        <Routes location={location}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/memory" element={<Memory />} />
          <Route path="/knowledge" element={<Knowledge />} />
          <Route path="/tools" element={<Tools />} />
          <Route path="/mcp" element={<Mcp />} />
          <Route path="/automations" element={<Automations />} />
          <Route path="/security" element={<Security />} />
          <Route path="/observability" element={<Observability />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/models" element={<Models />} />
          <Route path="/skills" element={<Skills />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <VoiceProvider>
        <div className="app-shell">
          <Sidebar />
          <main className="main">
            <Topbar />
            <AnimatedRoutes />
          </main>
        </div>
        <CommandPalette />
      </VoiceProvider>
    </BrowserRouter>
  );
}
