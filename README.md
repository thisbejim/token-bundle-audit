# token-bundle-audit

Offline release gates for Hugging Face-style tokenizer and chat-template bundles.

A model can have valid-looking weights and JSON while its tokenizer bundle is
quietly wrong: `config.vocab_size` can disagree with the tokenizer, a special
token can point outside the vocabulary, two files can contain competing chat
templates, or a Python-only Jinja expression can fail in a Rust/C++ server.
Those failures are often discovered only after a worker has opened a large
checkpoint—or worse, as degraded model behavior.

`token-bundle-audit` is a small local CLI and Python library that checks the
metadata and templates before a model reaches inference or training. It never
loads weights, imports `transformers`, executes Jinja, contacts the Hugging Face
Hub, or sends bundle contents anywhere.

## Quick start

```console
$ python -m pip install "git+https://github.com/thisbejim/token-bundle-audit.git"
$ token-bundle-audit check ./Qwen-model
token-bundle-audit: ./Qwen-model
ERROR   TB110 [config.json#/vocab_size] tokenizer base vocabulary (151936) exceeds config.vocab_size (151872)
WARNING TB124 [tokenizer_config.json] standalone chat_template.jinja differs from embedded default; Transformers gives the standalone file precedence
Summary: 1 error(s), 1 warning(s), 0 info(s)
```

Use it in CI:

```console
$ token-bundle-audit check ./model --strict --format json > token-bundle-report.json
```

`--strict` makes warnings fail the command. The default exit status fails only
for errors, so advisory findings can be introduced without breaking a local
inspection workflow. `--format sarif` is available for code-scanning uploads.

## What it checks

- `config.json` vocabulary size versus the discovered `tokenizer.json` or
  `vocab.json` vocabulary.
- Added-token IDs, duplicate IDs, special-token references, and generation
  token IDs against the configured vocabulary range.
- Precedence conflicts between `chat_template.jinja`, embedded
  `tokenizer_config.json` templates, legacy `chat_template.json`, and named
  templates in `additional_chat_templates/`.
- Basic Jinja delimiter balance, required `messages` and
  `add_generation_prompt` signals, external includes/imports, and portability
  hazards documented by Hugging Face (Python methods, Python boolean/null
  spellings, and `loop.previtem`/`loop.nextitem`).
- Malformed metadata with stable finding codes, paths, and remediation-oriented
  messages.

It deliberately does not claim to prove model quality, render a template
exactly like every Jinja engine, or validate tensor contents. Pair it with a
weight-file gate and a runtime smoke test when you need those guarantees.

## Supported bundle shapes

The audit is useful with a local directory containing any of the following
standard files:

```text
config.json
tokenizer.json             # preferred, when available
vocab.json                 # supported fallback
tokenizer_config.json
special_tokens_map.json
generation_config.json
chat_template.jinja
chat_template.json          # legacy compatibility
additional_chat_templates/*.jinja
```

Missing optional files produce advisory findings. The tool is intentionally
stdlib-only at runtime and does not need a tokenizer implementation or a GPU.

## Library API

```python
from token_bundle_audit import audit_bundle

report = audit_bundle("./model")
for finding in report.findings:
    print(finding.code, finding.severity, finding.message)

if not report.ok(strict=True):
    raise SystemExit(1)
```

## Why this exists

Hugging Face describes chat templates as the format the model was trained on
and warns that the wrong format can cause severe, silent degradation. Its
documentation also calls out Python-only Jinja methods and values that do not
port to non-Python runtimes. vLLM issues show the operational form of that
problem: a template/content mismatch can change the actual prompt and token
count while the request still looks valid. Model-specific projects often ship
one-off checksum scripts, but those do not generalize to a release gate for a
bundle assembled from multiple files.

The useful boundary is therefore before loading: inspect the small metadata
files, report the exact path and reason, and leave execution to the user's
chosen Transformers, vLLM, llama.cpp, MLX, or other runtime.

## Privacy and safety

All processing is local. There is no telemetry, account, network request,
model download, or API key. The audit reads JSON and Jinja text as untrusted
data and never executes templates, imports Python from a model repository, or
follows paths referenced by JSON.

## Development

```console
$ python3 -m venv .venv
$ .venv/bin/python -m pip install -e .
$ .venv/bin/python -m unittest discover -s tests -v
$ .venv/bin/python -m compileall -q src tests
```

The test suite is fixture-first and offline. It covers a clean bundle, broken
vocabulary metadata, duplicate IDs, template precedence, portability findings,
invalid JSON, missing paths, machine-readable output, and strict CI behavior.

## License

MIT. See [LICENSE](LICENSE).
