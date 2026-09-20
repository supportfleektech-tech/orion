# Running a real local model

ORION ships with `scripts/demo_model.py`, a rule-based stand-in that proves the
full agent pipeline works without any download. It is **not** an LLM. This guide
replaces it with a real model that runs entirely on your machine.

## Quick start

```bash
cd orion-assistant
./scripts/setup-local-model.sh
```

The script detects your RAM and free disk, installs Ollama if it is missing,
picks the best model your machine can actually run, pulls it plus the embedding
model, and writes the result into `.env`. Then restart ORION:

```bash
./scripts/dev.sh
```

Open **Models** in the UI to confirm: it shows your hardware, whether Ollama is
reachable, which models are installed, and whether the active model supports
vision.

To force a specific model:

```bash
./scripts/setup-local-model.sh qwen3.5:4b
```

## Which model you get

The ladder is defined in `backend/app/services/model_manager.py` and surfaced at
`GET /v1/models/catalog`.

| Tier | Model | Download | Needs | Vision | Tools | Context |
|---|---|---|---|---|---|---|
| workstation | `qwen3.5:9b` | 6.6 GB | 14 GB RAM | yes | yes | 256K |
| vision-focus | `qwen3-vl:8b` | 5.8 GB | 12 GB RAM | yes | yes | 128K |
| **recommended** | **`qwen3.5:4b`** | **3.4 GB** | **7 GB RAM** | **yes** | **yes** | **256K** |
| compact | `gemma3:4b` | 3.3 GB | 5 GB RAM | yes | **no** | 128K |
| minimal | `qwen3:1.7b` | 1.4 GB | 3 GB RAM | no | yes | 32K |

`qwen3.5:4b` is the default recommendation for an 8 GB machine: it is
multimodal, has a 256K context, supports thinking mode and native tool calling,
and is Apache 2.0 licensed.

**Auto-selection only picks models with tool calling.** ORION is an agent — a
model that cannot call tools silently degrades into plain chat. `gemma3:4b` is
vision-capable but has no native tool calling in Ollama, so it is never chosen
automatically. You can still select it by hand from the Models page or by
passing it to the setup script; the catalog labels the trade-off.

Rule of thumb: a smaller model at Q4 beats a larger model at Q2.

## Learning and self-improvement

Real improvement here does not mean fine-tuning weights on your laptop — that is
not realistic on 8 GB. Instead ORION improves through mechanisms you can
inspect and edit:

1. **Memory** — facts and interaction summaries, retrieved by embedding
   similarity (`/v1/memory`).
2. **Knowledge** — documents you ingest, chunked and searchable (`/v1/knowledge`).
3. **Skills** — successful multi-step runs are distilled by the model into named,
   reusable procedures, then injected into later prompts when they match. Skills
   gain confidence when they work and are auto-disabled after repeated failures.
   See the **Skills** page and `/v1/skills`.
4. **Feedback** — thumbs up/down on answers feeds back into skill confidence
   (`/v1/feedback`).

Turn skill distillation off with `SKILL_LEARNING_ENABLED=false` if you do not
want the extra model call per learnable run.

## Input formats

`POST /v1/chat/upload` accepts files alongside your message. Check what your
current deployment supports at `GET /v1/attachments/capabilities`.

| Format | Handling |
|---|---|
| `.txt .md .json .csv .py .ts .sql .yaml` and other text/code | read directly |
| `.pdf .docx .pptx .xlsx .xls` | text extracted (no OCR for scanned pages) |
| `.png .jpg .webp .gif .bmp .tiff` | resized and sent to the vision model |
| `.mp3 .wav .m4a .ogg .flac .opus` | transcribed locally with faster-whisper |
| `.mp4 .mov .webm .mkv` | accepted, but not analysed frame-by-frame |

Images require a vision-capable model. If your active model is text-only, the
image is **not** silently dropped — the model is told an image was attached and
that it cannot see it, and the UI says the same. Audio transcription needs the
optional extra:

```bash
pip install -r backend/requirements-optional.txt
```

## If your network blocks the model registry

Some sandboxes and corporate networks block `ollama.com`, `registry.ollama.ai`
and `huggingface.co`. The setup script will tell you rather than hanging. Two
options:

**Copy the blobs from another machine.** Pull on a machine with access, then
copy the store across:

```bash
# on the machine with network access
ollama pull qwen3.5:4b
tar -czf models.tgz -C ~/.ollama models
# then on the target machine
tar -xzf models.tgz -C ~/.ollama
```

**Use a GGUF file directly.** Drop a `.gguf` next to a Modelfile and import it:

```bash
printf 'FROM ./qwen3.5-4b-q4_k_m.gguf\n' > Modelfile
ollama create qwen3.5:4b -f Modelfile
```

## Cloud burst

Local stays the default. To allow escalation to a hosted model for hard tasks,
set `OPENROUTER_API_KEY` in `.env`. Set `LOCAL_ONLY=true` to guarantee nothing
ever leaves the machine.

## Degraded mode

If no model is reachable, ORION does not fabricate answers. It returns a
retrieval-only response assembled from memory and ingested knowledge, labels the
sources, marks the response `degraded: true`, and tells you how to start Ollama
or configure a cloud key.


## Proving it actually works

Everything in CI runs against a mock LLM, because CI has no GPU and often no
network. That leaves exactly one surface untested: whether a *real* model
drives the tool loop, streams tokens, and grounds answers in retrieval.

Once a model is installed, prove it in one command:

```bash
./scripts/run-backend.sh          # one terminal
./scripts/verify-real-model.sh    # another
```

It checks six things against the live stack: a plain answer, a tool call with
the right arithmetic, incremental token streaming, retrieval grounding on a
fact that exists nowhere else, memory recall across conversations, and both
shipped evaluation suites.

The script refuses to run against the bundled demo model or a degraded
runtime, rather than reporting a pass that means nothing.

Read the results as two different signals:

* **`core` failures are capability.** A 4B model will miss cases a frontier
  model gets. That is information about the model, not a bug in ORION.
* **`safety` failures are policy.** Those should pass on any model, so a
  failure there is a real defect worth chasing.
