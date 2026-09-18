import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Bot,
  Brain,
  ClipboardCheck,
  Command,
  Cpu,
  Database,
  FlaskConical,
  GraduationCap,
  Home,
  MessageSquarePlus,
  Plug,
  Power,
  Search,
  Settings2,
  Shield,
  TerminalSquare,
} from "lucide-react";
import { api } from "../lib/api";

/**
 * Command palette (Cmd/Ctrl+K).
 *
 * Keyboard-first navigation and actions. Anything not recognised as a command
 * falls through to "ask ORION", so the palette doubles as a way into chat and
 * an empty query is never a dead end.
 */

interface Action {
  id: string;
  label: string;
  hint?: string;
  icon: any;
  group: "Navigate" | "Actions";
  run: () => void | Promise<void>;
  keywords?: string;
}

/** Subsequence match, so "mcps" finds "MCP servers". */
function fuzzy(needle: string, haystack: string): boolean {
  const n = needle.toLowerCase();
  const h = haystack.toLowerCase();
  if (h.includes(n)) return true;
  let i = 0;
  for (const char of h) {
    if (char === n[i]) i += 1;
    if (i === n.length) return true;
  }
  return false;
}

export function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const actions = useMemo<Action[]>(() => {
    const go = (path: string, label: string, icon: any, keywords?: string): Action => ({
      id: `nav:${path}`,
      label,
      icon,
      group: "Navigate",
      keywords,
      run: () => navigate(path),
    });

    return [
      go("/", "Command Center", Home, "dashboard home overview"),
      go("/chat", "Conversations", Bot, "chat talk ask message"),
      go("/memory", "Memory", Brain, "remember facts"),
      go("/skills", "Skills", GraduationCap, "learned procedures"),
      go("/knowledge", "Knowledge", Database, "documents rag files"),
      go("/tools", "Tools", TerminalSquare, "registry capabilities"),
      go("/mcp", "MCP servers", Plug, "external tools protocol"),
      go("/automations", "Automations", Activity, "schedule cron jobs"),
      go("/security", "Security", Shield, "approvals audit policy"),
      go("/observability", "Observability", FlaskConical, "runs traces metrics logs"),
      go("/evaluation", "Evaluation", ClipboardCheck, "evals regression testing"),
      go("/models", "Models", Cpu, "ollama download provision"),
      go("/settings", "Settings", Settings2, "preferences config flags"),
      {
        id: "act:new-chat",
        label: "Start a new conversation",
        icon: MessageSquarePlus,
        group: "Actions",
        keywords: "new chat fresh clear",
        run: () => navigate("/chat?new=1"),
      },
      {
        id: "act:kill",
        label: "Engage the kill switch",
        hint: "Halts all tool use immediately",
        icon: Power,
        group: "Actions",
        keywords: "stop halt emergency panic disable",
        run: async () => {
          await api.killSwitch(true, "command palette");
          navigate("/security");
        },
      },
    ];
  }, [navigate]);

  const results = useMemo(() => {
    const q = query.trim();
    if (!q) return actions;
    return actions.filter((a) => fuzzy(q, `${a.label} ${a.keywords ?? ""}`));
  }, [query, actions]);

  // Global shortcut. Cmd+K on macOS, Ctrl+K elsewhere.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      // Wait a frame so the input exists before focusing it.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => setCursor(0), [query]);

  // Keep the highlighted row in view when navigating by keyboard.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${cursor}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  async function choose(action?: Action) {
    const target = action ?? results[cursor];
    setOpen(false);
    if (target) {
      await target.run();
    } else if (query.trim()) {
      // Nothing matched: treat the text as a question.
      navigate(`/chat?q=${encodeURIComponent(query.trim())}`);
    }
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((c) => (results.length ? (c + 1) % results.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((c) => (results.length ? (c - 1 + results.length) % results.length : 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      void choose();
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  let lastGroup = "";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="palette-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            className="palette"
            initial={{ opacity: 0, y: -18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 420, damping: 32 }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
          >
            <div className="palette-input">
              <Search size={17} />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Search pages, run an action, or ask a question…"
                aria-label="Command"
              />
              <kbd>ESC</kbd>
            </div>

            <div className="palette-list" ref={listRef}>
              {results.map((action, index) => {
                const header = action.group !== lastGroup ? action.group : null;
                lastGroup = action.group;
                const Icon = action.icon;
                return (
                  <div key={action.id}>
                    {header && <div className="palette-group">{header}</div>}
                    <button
                      data-index={index}
                      className={`palette-row ${index === cursor ? "active" : ""}`}
                      onMouseEnter={() => setCursor(index)}
                      onClick={() => void choose(action)}
                    >
                      <Icon size={15} />
                      <span className="palette-label">
                        {action.label}
                        {action.hint && <em>{action.hint}</em>}
                      </span>
                      <ArrowRight size={13} className="palette-go" />
                    </button>
                  </div>
                );
              })}

              {results.length === 0 && (
                <button className="palette-row active" onClick={() => void choose()}>
                  <Bot size={15} />
                  <span className="palette-label">
                    Ask ORION “{query}”
                    <em>No command matched — send this to chat instead</em>
                  </span>
                  <ArrowRight size={13} className="palette-go" />
                </button>
              )}
            </div>

            <div className="palette-foot">
              <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
              <span><kbd>⏎</kbd> select</span>
              <span><Command size={11} /> <kbd>K</kbd> toggle</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
