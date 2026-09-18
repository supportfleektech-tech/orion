# Evaluation and Self-Improvement

## Golden task suite

Create a versioned set of representative tasks:

```text
01_chat.yaml
02_memory.yaml
03_rag.yaml
04_tool_choice.yaml
05_planning.yaml
06_web_research.yaml
07_code_edit.yaml
08_document_generation.yaml
09_safety.yaml
10_regression.yaml
```

Each task contains:

- input;
- expected capabilities;
- forbidden actions;
- acceptance criteria;
- scoring rubric;
- optional reference answer.

## Improvement loop

```text
telemetry
   ↓
failure clustering
   ↓
hypothesis
   ↓
candidate change (prompt/router/tool)
   ↓
golden suite
   ↓
safety suite
   ↓
review
   ↓
canary
   ↓
release
```

## Score dimensions

Do not reduce assistant quality to a single number. Track separate measures:

- correctness;
- groundedness;
- tool precision;
- tool recall;
- task completion;
- latency;
- privacy compliance;
- approval compliance.

## Optional fine-tuning

Collect high-quality examples only after consent and privacy filtering. Keep training data export separate from production memory. Fine-tuning is not necessary for the first releases.
