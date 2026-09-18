# Evaluation

A local assistant drifts. You swap the model, tune the reranker, edit the
system prompt — and the only honest way to know whether it got better or worse
is to re-run a fixed set of cases and compare.

Open **Evaluation** in the sidebar, pick a suite, press **Run**. Each case goes
through the real agent loop — real tools, real retrieval, real model — and is
graded against what the suite says a good answer looks like.

---

## Writing a suite

Suites are plain YAML (or JSON) in `evals/`. No code:

```yaml
name: core
description: Baseline behaviour that must not regress.

cases:
  - id: arithmetic-uses-calculator
    task: what is 47 * 19?
    expect:
      contains: "893"
      tools_used: calculate
```

### Assertions

| Key | Passes when |
|---|---|
| `contains` | The substring appears in the answer (case-insensitive) |
| `not_contains` | It does not appear |
| `regex` | The pattern matches (case-insensitive, `.` spans newlines) |
| `tools_used` | That tool was called during the run |
| `tools_not_used` | It was not called |
| `max_duration_ms` | The run finished within the budget |

Every key also accepts a list, which becomes one check per entry:

```yaml
    expect:
      contains:
        - "893"
        - "47"
      tools_not_used: [shell, browse_page]
```

A case passes only if **every** check passes. A case with no assertions is
treated as a mistake by the test suite, not a free pass.

> **YAML gotcha:** bare `yes`, `no`, `on`, `off` and `true` become booleans, and
> bare digits become numbers. They are compared as text anyway, but quote them
> (`contains: "yes"`) to say what you mean.

---

## Why no LLM judge

A model grading another model is nondeterministic, needs a second model
available, and cannot run offline on a laptop — it reintroduces exactly the
uncertainty an evaluation exists to remove. The checks here are cheap, exact,
and repeatable.

The trade-off is real: this measures behaviour you can state precisely, not
answer quality in general. That is the right scope for a **regression** suite.
Use the cases to pin down things that should never break — the calculator gets
used, the shell does not get called, nothing claims to have sent an email.

---

## Reading results

Expand any case to see each assertion, what was expected, why it failed, which
tools ran, and the full answer.

Absolute pass rates are not very meaningful on their own: a 4B local model will
fail cases that a frontier model passes. **The comparison between runs is the
signal.** Every run is recorded in the history table with the model it used, so
"was this change an improvement?" is answerable.

The two shipped suites are deliberately different in character:

* **`core`** — capability. Expect these to move as you change models.
* **`safety`** — guardrails. These should pass regardless of model quality; a
  failure here is a policy bug, not a capability gap.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/evaluations` | Available suites and the active model |
| `GET` | `/v1/evaluations/history` | Past runs, newest first |
| `POST` | `/v1/evaluations/{name}/run` | Run a suite and return full results |

Runs execute cases **sequentially** — a local model serves one request at a
time, so concurrency would make the latency numbers meaningless. Expect a suite
to take a few minutes against a local model.

Evaluations run with approvals auto-granted; otherwise a suite touching a
gated tool would block forever waiting for a human. They still respect the kill
switch and every other policy flag.
