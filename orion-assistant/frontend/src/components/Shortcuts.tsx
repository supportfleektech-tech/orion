import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Keyboard, X } from "lucide-react";

/**
 * Keyboard shortcut reference, opened with "?".
 *
 * Every shortcut the app binds is listed here and nowhere else, so the help
 * cannot drift from reality without someone noticing.
 */

const GROUPS: { title: string; items: [string[], string][] }[] = [
  {
    title: "Global",
    items: [
      [["Ctrl", "K"], "Open the command palette"],
      [["Ctrl", "Shift", "V"], "Start or stop voice input"],
      [["?"], "Show this help"],
      [["Esc"], "Close any overlay"],
    ],
  },
  {
    title: "Chat",
    items: [
      [["Enter"], "Send the message"],
      [["Shift", "Enter"], "New line"],
    ],
  },
  {
    title: "Palette",
    items: [
      [["↑", "↓"], "Move between results"],
      [["Enter"], "Run the highlighted command"],
    ],
  },
];

export function Shortcuts() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") return setOpen(false);
      if (event.key !== "?") return;

      // Never steal "?" from someone typing a question.
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      if (typing) return;

      event.preventDefault();
      setOpen((v) => !v);
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            className="modal shortcuts"
            style={{ width: "min(540px, 100%)" }}
            initial={{ opacity: 0, scale: 0.94, y: 14 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ type: "spring", stiffness: 420, damping: 32 }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
          >
            <div className="shortcuts-head">
              <h3><Keyboard size={17} /> Keyboard shortcuts</h3>
              <button className="icon" onClick={() => setOpen(false)} aria-label="Close">
                <X size={14} />
              </button>
            </div>

            {GROUPS.map((group, g) => (
              <motion.div
                key={group.title}
                className="shortcut-group"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 + g * 0.05 }}
              >
                <div className="eyebrow">{group.title}</div>
                {group.items.map(([keys, label]) => (
                  <div className="shortcut-row" key={label}>
                    <span>{label}</span>
                    <span className="shortcut-keys">
                      {keys.map((k) => (
                        <kbd key={k}>{k}</kbd>
                      ))}
                    </span>
                  </div>
                ))}
              </motion.div>
            ))}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
