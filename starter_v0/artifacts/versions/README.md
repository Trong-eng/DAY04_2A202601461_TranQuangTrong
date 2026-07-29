# Versioned artifacts

This directory preserves the prompt and tool declarations used by each eval
version so that the UI and CLI can rerun an older version exactly.

## Workflow

1. `v0/` contains the untouched baseline artifacts.
2. Copy the preceding version into the next version directory.
3. Change one hypothesis in that new version's `system_prompt.md` or
   `tools.yaml`.
4. Run the eval with explicit artifact paths.
5. Record the resulting hashes, metric, and run JSON in
   `../version_log.csv`.

Example for `v1`:

```bash
python run_eval.py \
  --provider openrouter \
  --version v1 \
  --suite base \
  --eval-cases data/eval_base.json \
  --system-prompt artifacts/versions/v1/system_prompt.md \
  --tools artifacts/versions/v1/tools.yaml
```

Do not label identical artifacts as different optimization versions. Each of
`v1`, `v2`, and `v3` must represent a genuine iteration.
