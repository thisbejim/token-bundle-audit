# Product specification

## Target developer

Inference and research engineers packaging a Hugging Face-style checkpoint for
vLLM, Transformers, llama.cpp, MLX, TGI, or an OpenAI-compatible server; and
model authors publishing a tokenizer/chat-template change alongside weights.

## Problem

When a model bundle is copied, converted, quantized, or released, small
tokenizer metadata files become a distributed contract. A vocabulary-size
mismatch, out-of-range special token, stale embedded template, or
Python-specific Jinja expression can fail late or silently alter prompts. The
current workaround is to start the server, discover the problem from a loader
exception or bad behavior, and then inspect JSON by hand.

## Evidence

- Hugging Face's chat-template documentation says the template must match the
  format used during training and that a wrong format is a silent performance
  failure. It also documents portability hazards in non-Python Jinja engines.
- vLLM issue [#15125](https://github.com/vllm-project/vllm/issues/15125) shows a
  real multimodal model selecting the wrong template source and producing the
  wrong prompt ordering.
- vLLM issue [#14884](https://github.com/vllm-project/vllm/issues/14884) shows a
  template loaded from disk being transformed into invalid Jinja by a runtime
  escape path.
- vLLM issue [#39614](https://github.com/vllm-project/vllm/issues/39614) uses
  `/tokenize` and `/detokenize` to diagnose a tool-result/template mismatch that
  silently removed content from the prompt.
- Transformers issue [#28670](https://github.com/huggingface/transformers/issues/28670)
  shows a saved fine-tune directory failing at tokenizer loading after the
  model files were already present.
- A model-specific release repository ships a checksum validator for its
  tokenizer files ([Apertus omni tokenizer](https://github.com/swiss-ai/apertus-omni-tokenizer)),
  evidence that authors repeatedly need a preflight gate but usually have to
  write one-off scripts.

## Existing workflow and alternatives

- `transformers` and vLLM remain the source of truth, but their checks occur
  while loading or serving and may require a large environment or GPU.
- `weightlint`-style weight checks catch shard and SafeTensors problems, not
  the deeper tokenizer/chat-template contract.
- `ztok` validates tokenizer internals and round trips, but does not reconcile a
  model directory's config, special-token metadata, and competing template
  sources.
- Model-specific checksum scripts protect one known release and cannot be
  reused for a different architecture or conversion.

## Gap and product thesis

For inference engineers shipping a local model directory, `token-bundle-audit`
is the fast, dependency-free preflight that catches tokenizer/config/template
contract failures before a loader or GPU worker starts, because it audits the
portable files already on disk and emits stable CI diagnostics without loading
weights or executing templates.

## Core workflow

```text
Hugging Face-style model directory
        ↓
token-bundle-audit check [--strict] [--format json|sarif]
        ↓
stable findings with file paths, codes, and exit status
```

## Non-goals

- No weight loading, tensor arithmetic, tokenizer encoding, or model quality
  evaluation.
- No attempt to implement a Jinja interpreter or certify every runtime.
- No downloads, Hub API, hosted dashboard, or provider-specific network call.
- No automatic mutation or repair of user files.

## Interface

A CLI plus a tiny Python library. The CLI is composable in CI and shell
pipelines; JSON and SARIF reports are stable enough for automation.

## Offline and integration story

Everything works offline against an ordinary directory. The output can gate a
Transformers/vLLM/llama.cpp/MLX deployment step, accompany a model release, or
be run beside an existing weight validator. No provider API is required.
