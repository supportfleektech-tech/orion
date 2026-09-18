import { FormEvent, useCallback, useEffect, useState } from "react";
import { GraduationCap, Sparkles, Trash2 } from "lucide-react";
import { api, type FeedbackStats, type SkillItem } from "../lib/api";
import { Badge, EmptyBlock, ErrorBlock, Loading, PageTitle, Panel, Toast, timeAgo } from "../components/ui";
import { useToast } from "../hooks/useApi";

const BLANK = { name: "", description: "", instructions: "", trigger_keywords: "" };

export function Skills() {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [filter, setFilter] = useState("");
  const [probe, setProbe] = useState("");
  const [matches, setMatches] = useState<SkillItem[] | null>(null);
  const [draft, setDraft] = useState({ ...BLANK });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast, notify } = useToast();

  const load = useCallback(async () => {
    try {
      const [s, f] = await Promise.all([api.skills(filter || undefined), api.feedbackStats()]);
      setSkills(s.skills);
      setStats(f);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!draft.name.trim() || !draft.instructions.trim()) return;
    try {
      await api.createSkill({
        name: draft.name,
        description: draft.description || "User-defined skill.",
        instructions: draft.instructions,
        trigger_keywords: draft.trigger_keywords
          .split(",")
          .map((k) => k.trim().toLowerCase())
          .filter(Boolean),
      });
      setDraft({ ...BLANK });
      notify("Skill saved", "ok");
      void load();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    }
  }

  async function testMatch(e: FormEvent) {
    e.preventDefault();
    if (!probe.trim()) {
      setMatches(null);
      return;
    }
    setMatches((await api.relevantSkills(probe)).skills);
  }

  return (
    <div className="page">
      <PageTitle
        icon={GraduationCap}
        title="Skills"
        subtitle="SELF-IMPROVEMENT"
        actions={
          stats && (
            <Badge tone={stats.satisfaction === null ? "default" : stats.satisfaction > 0.6 ? "ok" : "warn"}>
              {stats.up}↑ {stats.down}↓
              {stats.satisfaction !== null && ` · ${Math.round(stats.satisfaction * 100)}%`}
            </Badge>
          )
        }
      />

      <Panel title="How this works" subtitle="LEARNING LOOP">
        <p className="muted">
          When ORION completes a multi-step task successfully, it distils what worked into a named
          procedure. On later requests, matching skills are injected into the prompt so the same
          approach is reused. Skills that keep failing lose confidence and are disabled
          automatically. Everything here is plain text you can read, edit, or delete.
        </p>
      </Panel>

      <div className="grid-two">
        <Panel title="Test matching" subtitle="DRY RUN">
          <form className="inline-form" onSubmit={testMatch}>
            <input
              value={probe}
              placeholder="e.g. deploy the backend to production"
              onChange={(e) => setProbe(e.target.value)}
            />
            <button className="ghost" type="submit">
              <Sparkles size={14} /> Match
            </button>
          </form>
          {matches !== null &&
            (matches.length === 0 ? (
              <p className="muted small">No learned skill matches this request yet.</p>
            ) : (
              <div className="list">
                {matches.map((m) => (
                  <div key={m.id} className="list-row">
                    <strong>{m.name}</strong>
                    <Badge tone="info">relevance {m.relevance?.toFixed(2)}</Badge>
                  </div>
                ))}
              </div>
            ))}
        </Panel>

        <Panel title="Teach a skill" subtitle="MANUAL">
          <form className="form" onSubmit={create}>
            <div className="field">
              <label>Name</label>
              <input
                placeholder="triage a failing deploy"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>When to use it</label>
              <input
                placeholder="CI goes red after a release"
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Trigger keywords (comma separated)</label>
              <input
                placeholder="deploy, ci, pipeline"
                value={draft.trigger_keywords}
                onChange={(e) => setDraft({ ...draft, trigger_keywords: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Steps</label>
              <textarea
                rows={5}
                placeholder={"1. read the failing job log\n2. rerun with verbose output"}
                value={draft.instructions}
                onChange={(e) => setDraft({ ...draft, instructions: e.target.value })}
              />
            </div>
            <button type="submit">Save skill</button>
          </form>
        </Panel>
      </div>

      <Panel
        title={`Skills (${skills.length})`}
        subtitle="LIBRARY"
        right={
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="candidate">Candidate</option>
            <option value="disabled">Disabled</option>
          </select>
        }
      >
        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorBlock message={error} />
        ) : skills.length === 0 ? (
          <EmptyBlock
            icon={GraduationCap}
            title="Nothing learned yet"
            hint="Complete a multi-step task in Chat and ORION will distil it into a reusable skill."
          />
        ) : (
          <div className="list">
            {skills.map((skill) => (
              <div key={skill.id} className="list-row skill-row">
                <div style={{ flex: 1 }}>
                  <div className="row-top">
                    <strong>{skill.name}</strong>
                    <Badge tone={skill.status === "active" ? "ok" : skill.status === "disabled" ? "err" : "info"}>
                      {skill.status}
                    </Badge>
                    <Badge>{skill.source}</Badge>
                    <span className="muted small">confidence {Math.round(skill.confidence * 100)}%</span>
                  </div>
                  <p className="muted small">{skill.description}</p>
                  <pre className="trace">{skill.instructions}</pre>
                  <span className="muted small">
                    used {skill.uses}× · {skill.successes} ok / {skill.failures} failed
                    {skill.last_used_at && ` · last ${timeAgo(skill.last_used_at)}`}
                    {skill.trigger_keywords.length > 0 && ` · ${skill.trigger_keywords.join(", ")}`}
                  </span>
                </div>
                <div className="row-actions">
                  <button
                    className="ghost"
                    onClick={() =>
                      void api
                        .setSkillStatus(skill.id, skill.status === "disabled" ? "active" : "disabled")
                        .then(load)
                    }
                  >
                    {skill.status === "disabled" ? "Enable" : "Disable"}
                  </button>
                  <button className="ghost" onClick={() => void api.deleteSkill(skill.id).then(load)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Toast toast={toast} />
    </div>
  );
}
