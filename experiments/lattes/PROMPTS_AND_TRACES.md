# Lattes prompts and trace examples

This document records representative prompts, model inputs, operation calls, and trace excerpts from the preserved `baseline_001` experiment. It complements the raw artifacts under `baseline_001/` and makes the execution protocol easier to inspect without requiring readers to search through all 1,200 runs.

The excerpts below are descriptive views of committed artifacts. They are not additional experimental results and are not used by the analysis scripts.

## 1. Generation prompt

The answer-generation models were instructed to answer questions about a researcher using the supplied Lattes curriculum as context. The instruction used in the preserved traces is equivalent to:

```text
You are an assistant that answers questions about a researcher using the
researcher's Lattes curriculum as context.

Produce accurate, concise, context-grounded answers.

- Use only the provided data.
- State when the available context is insufficient.
- Do not make assumptions or rely on external knowledge.
```

The benchmark then adds the question and provides context according to the selected strategy.

### Example question

```text
Where and how long ago did the researcher complete their PhD?
```

The complete question records, including templates, parameters, tags, selected context blocks, model configuration, and strategy, are stored in:

```text
baseline_001/queries.jsonl
```

Representative records for the same question across all five configurations have run identifiers such as:

| Configuration | Strategy / format | Example run |
|---|---|---|
| I-HTML | `inline` / `html` | `b33c1e3458` |
| I-JSON | `inline` / `json` | `8a0831e117` |
| Func. | `local_function` / `json` | `64a9f29f8d` |
| L-MCP | `local_mcp` / `json` | `a3efd1b16d` |
| R-MCP | `mcp` / `json` | `77134889b0` |

These identifiers can be located directly in `queries.jsonl`, `answers.jsonl`, and the corresponding trace directories.

## 2. Context-provisioning behavior

The task question is held constant while the mechanism used to provide curriculum data changes.

### Inline HTML and inline JSON

For inline configurations, the selected curriculum blocks are serialized and inserted into the model input together with the question. No operation call is expected.

A representative inline trace is:

```text
baseline_001/traces/queries/b33c1e3458.json
```

Its recorded execution contains one model-generation step, no tool calls, and the provider-reported token and latency metrics. The full serialized curriculum is intentionally retained only in the raw trace rather than duplicated here.

### Local function calling

For operation-mediated configurations, the model receives operation descriptions and chooses which structured curriculum operation to invoke.

Representative call from run `6a0689d3ca`:

```json
{
  "tool_name": "get_supervisions",
  "arguments": {
    "lattes_id": "5521922960404236",
    "start_year": 2019
  }
}
```

The trace records the call, the structured result, the runtime used to execute it, and the subsequent model-generation step. The full trace is available at:

```text
baseline_001/traces/queries/6a0689d3ca.json
```

A shortened event sequence is:

```text
model.generate
mcp.tool_call: get_supervisions(lattes_id=..., start_year=2019)
mcp.tool_result: success, runtime=local_function
model.generate
...
```

Although the event names use the benchmark's common MCP-oriented tracing vocabulary, the `runtime` field identifies this execution as `local_function`.

### Local MCP

Local MCP exposes the same domain operations through an MCP server running in the experiment environment. A representative query can be found by selecting a `local_mcp` record in `queries.jsonl` and opening the path referenced by its `traceRef` field.

The expected trace pattern is:

```text
model.generate
mcp.tool_call: <operation>(<structured arguments>)
mcp.tool_result: success, runtime=local_mcp
model.generate
```

### Remote MCP

Remote MCP delegates the same operation to the configured remote MCP endpoint. Provider-native MCP evidence may be recorded under `trace.nativeMcp`, provider response objects, or AI-trace event metadata. The repository's `extract_observed_calls.py` normalizes these representations when calculating observed operation counts.

No credential is reproduced in this document. The experiment specification uses an environment-variable placeholder for the authentication token.

## 3. Example generated result

For the inline-HTML run `b33c1e3458`, the model answered the PhD question with the institution, year, and an elapsed-time calculation grounded in the supplied curriculum. The full answer and usage metrics are stored in:

```text
baseline_001/answers.jsonl
baseline_001/traces/queries/b33c1e3458.json
```

The corresponding trace reports, among other fields:

```json
{
  "modelCalls": 1,
  "toolCalls": 0,
  "totalTokens": 108279,
  "totalDurationMs": 7205
}
```

These values are examples for a single run, not aggregate paper results.

## 4. Evaluation prompt and judge traces

Each generated answer is independently evaluated by three judges. The evaluation asks each judge to assess two criteria:

- **correctness**: whether the answer is supported by the supplied curriculum context;
- **completeness**: whether the answer sufficiently addresses the question.

Each criterion receives one of the labels `meets`, `partial`, or `misses`, together with a justification. The aggregate majority and unanimous metrics are computed from the individual votes in:

```text
baseline_001/judge_votes.jsonl
```

A representative evaluation trace is:

```text
baseline_001/traces/evals/cb91c83c43.json
```

It records separate model executions and usage metrics for the GPT, Gemini, and Claude judges. The complete vote objects are retained in `judge_votes.jsonl`; the analysis scripts derive majority and unanimity from those records rather than from static values.

## 5. Reproducing the examples

Locate a query by run identifier:

```bash
rg '"runId": "6a0689d3ca"' experiments/lattes/baseline_001
```

Inspect its trace:

```bash
python -m json.tool \
  experiments/lattes/baseline_001/traces/queries/6a0689d3ca.json
```

Extract normalized operation-call evidence for the complete baseline:

```bash
python experiments/lattes/extract_observed_calls.py \
  experiments/lattes/baseline_001 \
  --output-dir experiments/lattes/baseline_001/derived/calls
```

Run the baseline-derived analysis:

```bash
python experiments/lattes/analyze_lattes.py \
  experiments/lattes/baseline_001
```

## 6. Artifact map

| Information | Authoritative artifact |
|---|---|
| Question templates and parameters | `baseline_001/queries.jsonl` |
| Generated answers and query metrics | `baseline_001/answers.jsonl` |
| Individual judge decisions | `baseline_001/judge_votes.jsonl` |
| Query execution details | `baseline_001/traces/queries/*.json` |
| Judge execution details | `baseline_001/traces/evals/*.json` |
| Normalized observed calls | generated by `extract_observed_calls.py` |

The raw artifacts remain authoritative. This document only provides readable entry points into them.
