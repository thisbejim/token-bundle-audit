# Opportunity research

Research date: 2026-09-20 (Australia/Melbourne)

## Candidates considered

| Candidate | Pain | Evidence | Gap | Decision |
| --- | ---: | ---: | --- | --- |
| Provider-aware JSON-Schema linter | 9 | 9 | Strong, but `schemafit` already targets this exact gap across five providers | Reject |
| MCP contract/conformance tester | 9 | 9 | Official MCP conformance plus `mcpward`/`mcpdiff`/Inspector already cover the workflow | Reject |
| SafeTensors/model-header inspector | 8 | 8 | `stprobe`, `weightlint`, and newer model-checker tools make this crowded | Reject |
| Tokenizer/chat-bundle release gate | 9 | 8 | Existing tools validate weights or tokenizer internals, but not the assembled metadata/template contract | Build |

## Strongest public signals

1. Hugging Face's [chat template guide](https://huggingface.co/docs/transformers/main/en/chat_templating_writing)
   calls the template part of the model's trained input format, warns that
   extra whitespace can harm performance, and documents that Python methods and
   Python values are not portable to non-Python Jinja implementations.
2. The [Hugging Face chat-template blog](https://huggingface.co/blog/chat-templates)
   describes the wrong format as a silent performance failure and recommends
   explicitly shipping a template with every chat model.
3. vLLM [#15125](https://github.com/vllm-project/vllm/issues/15125) shows a
   multimodal checkpoint carrying competing template sources and using the
   wrong one for image/text ordering.
4. vLLM [#14884](https://github.com/vllm-project/vllm/issues/14884) reports a
   disk-loaded template becoming invalid after an escape transformation.
5. vLLM [#39614](https://github.com/vllm-project/vllm/issues/39614) demonstrates
   a tool-result/template mismatch through `/tokenize` and `/detokenize`; the
   prompt looked valid at the API boundary while content disappeared before
   inference.
6. Transformers [#28670](https://github.com/huggingface/transformers/issues/28670)
   shows a saved model directory failing at tokenizer loading, after users had
   already assembled the checkpoint files.
7. The [Apertus tokenizer repository](https://github.com/swiss-ai/apertus-omni-tokenizer)
   publishes a model-specific checksum validator for tokenizer/config files.
   That repeated one-off pattern is evidence for a reusable, architecture-
   neutral preflight.

## Alternatives investigated

- The Transformers and vLLM loaders are authoritative but are late checks and
  require the runtime stack.
- `weightlint` (the sibling project in this workspace) checks shards,
  SafeTensors headers, and broad metadata presence; it intentionally does not
  reason about template precedence or Jinja portability.
- `ztok` provides tokenizer-vocabulary validation and round-trip checks; it does
  not audit a complete Hugging Face model directory's config and chat metadata.
- Model-specific shell validators can compare known checksums, but they do not
  generalize to new model families or conversions.

## Quality-gate scoring (0–10)

| Dimension | Score | Reason |
| --- | ---: | --- |
| Developer pain | 9 | Failures are late, expensive, and often silent. |
| Frequency | 8 | Every checkpoint conversion/release reconciles these files. |
| Public demand | 8 | Multiple runtime issues plus one-off validators show repeated friction. |
| Frontier-AI relevance | 9 | Directly affects open-weight model training, serving, and API-compatible inference. |
| Improvement | 8 | Millisecond CPU-only gate with stable paths/codes before a GPU load. |
| Standalone usefulness | 9 | Works on a directory with no model, account, or network. |
| Local-first advantage | 10 | Metadata never leaves the machine. |
| Discoverability | 8 | Matches “tokenizer mismatch”, “chat template broken”, and “model bundle check”. |
| Feasibility | 9 | Standard-library JSON/text checks with fixture-first tests. |
| Testability | 9 | Synthetic bundles cover each rule deterministically. |
| Maintainability | 8 | Targets stable file conventions, not provider-specific private APIs. |
| Overall open-source value | 8 | A sharp complement to runtime and weight validators, with honest limits. |

## Pre-build challenge

An inference engineer would clone this when a model conversion or release needs
to be checked on a CPU-only CI runner before a multi-gigabyte worker starts.
The repository is not a shallow AI demo because its core is deterministic
metadata reconciliation, its findings have stable codes and paths, and its
test suite never calls a model or executes a template.
