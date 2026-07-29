---
name: deduplicate_results
track: core
kind: local_formatter
requires_env: []
inputs: [items, similarity_threshold]
outputs: [items, duplicates, original_count, unique_count, removed_count, similarity_threshold]
side_effect: false
---
# deduplicate_results

Removes exact and near-duplicate research items without changing the retained
items. URLs are normalized by removing fragments, common tracking parameters,
default ports, and cosmetic host/path differences. Remaining titles are
compared with a configurable similarity threshold from `0.0` to `1.0`.

The result includes both the unique items and evidence describing every removed
duplicate. This tool does not search, fetch, summarize, or format sources.
