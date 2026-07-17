# RepoQA prompts and trace examples

This document records representative prompts, operation calls, generated outputs, and trace excerpts from the preserved RepoQA experiment. It provides a readable view of the execution protocol while keeping the complete machine-readable artifacts under `baseline-01/` authoritative.

The excerpts below are documentation only. They are not consumed by the analysis scripts and do not replace the raw baseline files.

## 1. Generation prompt

The generation models receive a repository-retrieval task and must reproduce the exact function described by a natural-language specification.

The system instruction in the preserved traces is equivalent to:

```text
Solve the benchmark task using only the provided context.

Produce an accurate, concise, context-grounded response.

- Do not use external knowledge.
- State when the context is insufficient.
- Follow the requested output format.
```

The RepoQA task template is:

```text
Based on the function description and code context, retrieve and repeat the
exact described function from the code context in a code block wrapped by
triple backticks.

Function description: {description}
```

The complete trial objects, including task text, description parameters, tags, model, strategy, format, validation threshold, and trace configuration, are stored in:

```text
baseline-01/trials.jsonl
```

## 2. Representative task

One preserved task describes a Python method that merges adjacent string groups while validating whether the transformation is allowed. The relevant trial identifiers include:

| Configuration | Strategy / format | Example trial |
|---|---|---|
| I-Code | `inline` / `code` | `50bd9ffac3` |
| I-JSON | `inline` / `json` | `fa98e779a0` is operation-mediated; use `trials.jsonl` to locate the matching inline-JSON trial |
| Func. | `local_function` / `json` | `fa98e779a0` |
| L-MCP | `local_mcp` / `json` | `68474de507` |

The exact paper subset is not currently recorded; these examples come from the complete committed baseline and are intended only to illustrate the protocol.

## 3. Inline execution example

For inline execution, the repository code context is serialized into the model input together with the function description. No repository operation call is expected.

Representative trace:

```text
baseline-01/traces/executions/50bd9ffac3.json
```

Its event sequence is:

```text
model.generate
strategy.inline.execute
engine.execute
```

The trace reports:

```json
{
  "modelCalls": 1,
  "toolCalls": 0,
  "inputTokens": 3503,
  "outputTokens": 414,
  "totalTokens": 3917,
  "totalDurationMs": 5331
}
```

The generated answer contains the retrieved target method in a fenced code block. The full output is retained in:

```text
baseline-01/responses.jsonl
baseline-01/traces/executions/50bd9ffac3.json
```

## 4. Local function-calling example

For local function calling, the model receives structured repository operations rather than the entire code context. It searches the workspace and then requests the target symbol.

Representative trace:

```text
baseline-01/traces/executions/fa98e779a0.json
```

A shortened call sequence from that trace is:

```json
[
  {
    "tool_name": "list_files",
    "arguments": {
      "workspace_id": "py_001_ctx4k"
    }
  },
  {
    "tool_name": "list_symbols",
    "arguments": {
      "workspace_id": "py_001_ctx4k",
      "path": "src/black/trans.py",
      "kind": ""
    }
  },
  {
    "tool_name": "get_symbol",
    "arguments": {
      "workspace_id": "py_001_ctx4k",
      "symbol_id": "src/black/trans.py#method:StringMerger._merge_string_group:586"
    }
  }
]
```

The corresponding event flow is:

```text
model.generate
mcp.tool_call: list_files
mcp.tool_result: one Python source file
model.generate
mcp.tool_call: list_symbols
mcp.tool_result: candidate class and methods
model.generate
mcp.tool_call: get_symbol
mcp.tool_result: target method source
model.generate
```

The trace's `runtime` field records `local_function`, even though the common event vocabulary uses `mcp.tool_call` and `mcp.tool_result` for structured operation events.

## 5. Local MCP example

Local MCP exposes the same repository operations through an MCP server running in the experiment environment. A representative trial is:

```text
trialId: 68474de507
strategy: local_mcp
workspace: py_001_ctx4k
```

Its trace can be inspected at:

```text
baseline-01/traces/executions/68474de507.json
```

The expected interaction follows the same semantic sequence as local function calling—workspace discovery, symbol discovery, and symbol retrieval—but the operation transport is MCP.

## 6. Deterministic evaluation

RepoQA does not use LLM-as-a-judge. Each response is evaluated by a deterministic dataset-specific scorer. The scorer compares the returned code with the target function and records fields such as:

```text
isBestMatch
passed
bestSimilarScore
threshold
language
repository
target
```

The authoritative evaluation artifacts are:

```text
baseline-01/evals.jsonl
baseline-01/evals-summary.json
```

A successful trial has `passed = true` when the extracted response satisfies the configured matching threshold. The analysis script joins responses and evaluations by `trialId`; expected paper values are never used as analysis input.

## 7. Security and redaction

Some historical trial records may contain connection parameters captured at execution time. Documentation and examples must never reproduce credentials. Use environment variables or placeholders when preparing new experiment specifications, for example:

```json
{
  "mcp_server": {
    "server_url": "${REPOQA_MCP_URL}",
    "auth_token": "${REPOQA_MCP_TOKEN}"
  }
}
```

Before publishing an immutable artifact release, scan the repository history and current files for provider keys, MCP tokens, and other secrets. Rotate any credential that was ever committed.

## 8. Inspecting the examples

Locate the representative trials:

```bash
rg '"trialId": "(50bd9ffac3|fa98e779a0|68474de507)"' \
  experiments/repoqa/baseline-01
```

Inspect a trace:

```bash
python -m json.tool \
  experiments/repoqa/baseline-01/traces/executions/fa98e779a0.json
```

Run the offline analysis over the committed baseline:

```bash
python experiments/repoqa/analyze_repoqa.py \
  experiments/repoqa/baseline-01
```

## 9. Artifact map

| Information | Authoritative artifact |
|---|---|
| Task templates, parameters, models, and strategies | `baseline-01/trials.jsonl` |
| Generated outputs and query metrics | `baseline-01/responses.jsonl` |
| Deterministic evaluation records | `baseline-01/evals.jsonl` |
| Aggregate scorer output | `baseline-01/evals-summary.json` |
| Execution events and operation results | `baseline-01/traces/executions/*.json` |

The raw artifacts remain authoritative. This document only highlights representative examples for reviewers and artifact evaluators.
