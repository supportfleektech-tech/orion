import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Bell, Search, Shield, Zap } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../hooks/useApi";

export function Topbar() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const { data } = useAsync(() => api.status(), [], 15000);
  const pending = data?.counts.pending_approvals ?? 0;
  const [mac, setMac] = useState(false);

  useEffect(() => {
    setMac(/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent));
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    navigate(`/chat?q=${encodeURIComponent(q)}`);
    setQ("");
  }

  return (
    <header className="topbar">
      <form className="search" onSubmit={submit}>
        <Search size={16} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask ORION anything…" />
        <kbd className="kbd-hint">{mac ? "⌘" : "Ctrl"} K</kbd>
      </form>

      <div className="top-actions">
        <motion.div
          className="mode-pill"
          key={data?.flags.local_only ? "local" : "auto"}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        >
          <Zap size={13} /> {data?.flags.local_only ? "LOCAL ONLY" : "AUTO / LOCAL-FIRST"}
        </motion.div>

        <AnimatePresence>
          {data?.kill_switch.enabled && (
            <motion.button
              className="alarm"
              title="Kill switch engaged"
              onClick={() => navigate("/security")}
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.7 }}
              transition={{ type: "spring", stiffness: 500, damping: 26 }}
            >
              {/* A slow pulse: the kill switch being on is a state the user
                  should keep noticing, not something that fades away. */}
              <motion.span
                animate={{ opacity: [1, 0.45, 1] }}
                transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                style={{ display: "grid", placeItems: "center" }}
              >
                <Shield size={16} />
              </motion.span>
            </motion.button>
          )}
        </AnimatePresence>

        <button
          className={pending ? "alarm" : ""}
          title={`${pending} pending approvals`}
          onClick={() => navigate("/security")}
        >
          <motion.span
            animate={pending ? { rotate: [0, -12, 12, -8, 8, 0] } : { rotate: 0 }}
            transition={{ duration: 0.7, repeat: pending ? Infinity : 0, repeatDelay: 4 }}
            style={{ display: "grid", placeItems: "center" }}
          >
            <Bell size={17} />
          </motion.span>
          <AnimatePresence>
            {pending > 0 && (
              <motion.em
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0, opacity: 0 }}
                transition={{ type: "spring", stiffness: 600, damping: 22 }}
              >
                {pending}
              </motion.em>
            )}
          </AnimatePresence>
        </button>

        <div className="avatar">O</div>
      </div>
    </header>
  );
}
