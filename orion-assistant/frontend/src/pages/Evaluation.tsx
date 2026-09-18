import { useEffect, useState } from "react";
import { Check, FlaskConical, Play, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { api, type EvalHistoryEntry, type EvalRun } from "../lib/api";
import { useAsync, useToast } from "../hooks/useApi";
import {
  Badge,
  Counter,
  EmptyBlock,
  Gauge,
  ErrorBlock,
  Loading,
  PageTitle,
  Panel,
  Toast,
  timeAgo,
} from "../components/ui";

function rateTone(rate: number) {
  if (rate >= 0.9) return "ok" as const;
  if (rate >= 0.6) return "warn" as const;
  return "err" as const;
}

/**
 * Evaluation: re-run a fixed set of cases and see whether behaviour drifted.
 *
 * Suites live in evals/*.yaml, so the interesting comparison is between runs
 * rather than any absolute score — a local model will never pass everything.
 */
export function Evaluation() {
  const { data, loading, error } = useAsync(() => api.evaluations(), []);
  const { toast, notify } = useToast();
  const [history, setHistory] = useState<EvalHistoryEntry[]>([]);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [openCase, setOpenCase] = useState<string | null>(null);

  const loadHistory = () =>
    api
      .evaluationHistory()
      .then((r) => setHistory(r.runs))
      .catch(() => setHistory([]));

  useEffect(() => {
    void loadHistory();
  }, []);

  async function start(name: string) {
    setRunning(name);
    setRun(null);
    try {
      const result = await api.runEvaluation(name);
      setRun(result);
      notify(`${result.passed}/${result.total} cases passed`, result.failed ? "err" : "ok");
      void loadHistory();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err), "err");
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="page">
      <PageTitle
        icon={FlaskConical}
        title="Evaluation"
        subtitle="REGRESSION"
        actions={
          data ? <Badge tone="info">model: {data.model}</Badge> : undefined
        }
      />

      {loading && <Loading />}
      {error && <ErrorBlock message={error} />}

      {data && data.suites.length === 0 && (
        <EmptyBlock
          icon={FlaskConical}
          title="No evaluation suites"
          hint={`Drop a YAML or JSON suite into ${data.directory} to start tracking whether ORION's behaviour drifts as you change models and prompts.`}
        />
      )}

      {data?.suites.map((suite) => (
        <Panel
          key={suite.name}
          subtitle="SUITE"
          title={suite.name}
          right={
            <div className="row-actions">
              <Badge tone="info">{suite.case_count} cases</Badge>
              <button disabled={running !== null || Boolean(suite.error)} onClick={() => start(suite.name)}>
                <Play size={13} /> {running === suite.name ? "Running…" : "Run"}
              </button>
            </div>
          }
        >
          {suite.error ? (
            <div className="notice err">
              <div>
                <strong>This suite could not be read.</strong>
                <br />
                <span className="mono small">{suite.error}</span>
              </div>
            </div>
          ) : (
            <p className="muted">{suite.description || "No description."}</p>
          )}
          {running === suite.name && (
            <p className="muted small">
              Running each case through the real agent loop, one at a time. On a local model this
              can take a few minutes.
            </p>
          )}
        </Panel>
      ))}

      {run && (
        <Panel
          subtitle="RESULT"
          title={`${run.suite} — ${run.passed}/${run.total} passed`}
          right={
            <div className="row-actions">
              <Badge tone={rateTone(run.pass_rate)}>{Math.round(run.pass_rate * 100)}%</Badge>
              {run.degraded && <Badge tone="warn">degraded</Badge>}
              <Badge tone="default">{(run.duration_ms / 1000).toFixed(1)}s</Badge>
            </div>
          }
        >
          <div className="eval-gauge">
            <Gauge
              value={run.pass_rate}
              tone={run.pass_rate >= 0.9 ? "var(--ok)" : run.pass_rate >= 0.6 ? "var(--warn)" : "var(--err)"}
            />
            <div className="eval-gauge-label">
              <strong><Counter value={Math.round(run.pass_rate * 100)} />%</strong>
              <span>{run.passed} of {run.total} cases passed in {(run.duration_ms / 1000).toFixed(1)}s</span>
            </div>
          </div>

          <ul className="eval-cases">
            {run.cases.map((c, i) => (
              <motion.li
                key={c.id}
                className={c.passed ? "ok" : "bad"}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(i, 12) * 0.04, duration: 0.3 }}
              >
                <button className="eval-case-head" onClick={() => setOpenCase(openCase === c.id ? null : c.id)}>
                  {c.passed ? <Check size={14} /> : <X size={14} />}
                  <span className="eval-case-id">{c.id}</span>
                  <span className="muted eval-case-task">{c.task}</span>
                  <span className="muted small">{c.duration_ms}ms</span>
                </button>

                <AnimatePresence initial={false}>
                {openCase === c.id && (
                  <motion.div
                    className="eval-case-body"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                    style={{ overflow: "hidden" }}
                  >
                    {c.error && <p className="mono small err-text">{c.error}</p>}

                    <div className="eval-checks">
                      {c.checks.map((check, i) => (
                        <div key={i} className={check.passed ? "ok" : "bad"}>
                          {check.passed ? <Check size={12} /> : <X size={12} />}
                          <code>
                            {check.kind}: {JSON.stringify(check.expected)}
                          </code>
                          {check.detail && <span className="muted">{check.detail}</span>}
                        </div>
                      ))}
                      {c.checks.length === 0 && <span className="muted small">No assertions.</span>}
                    </div>

                    {c.tools_used.length > 0 && (
                      <p className="muted small">Tools used: {c.tools_used.join(", ")}</p>
                    )}
                    <pre className="eval-answer">{c.answer || "(empty answer)"}</pre>
                  </motion.div>
                )}
                </AnimatePresence>
              </motion.li>
            ))}
          </ul>
        </Panel>
      )}

      {history.length > 0 && (
        <Panel subtitle="HISTORY" title="Previous runs">
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Suite</th>
                <th>Model</th>
                <th>Result</th>
                <th>Failures</th>
              </tr>
            </thead>
            <tbody>
              {history.map((entry, i) => (
                <tr key={i}>
                  <td>{timeAgo(entry.ran_at)}</td>
                  <td>{entry.suite}</td>
                  <td className="mono small">{entry.model || "—"}</td>
                  <td>
                    <Badge tone={rateTone(entry.pass_rate)}>
                      {entry.passed}/{entry.total}
                    </Badge>
                  </td>
                  <td className="muted small">{entry.failures?.join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      <Toast toast={toast} />
    </div>
  );
}
