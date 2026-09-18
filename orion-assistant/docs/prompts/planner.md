# Planner Prompt

Transform a user goal into a minimal executable plan.

Output:

```json
{
  "goal":"...",
  "assumptions":[],
  "acceptance_criteria":[],
  "steps":[
    {"id":"s1","description":"...","tool":"optional","depends_on":[]}
  ],
  "risk":"low|medium|high|destructive",
  "approval_points":[]
}
```

Do not add steps merely to appear sophisticated. Prefer deterministic, reversible operations.
