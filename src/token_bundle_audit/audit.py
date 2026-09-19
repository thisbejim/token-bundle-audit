"""Deterministic checks for local Hugging Face-style model bundles.

This module intentionally does not import transformers, tokenizers, Jinja, or
any model runtime. It audits the files that a loader would reconcile before a
large checkpoint is opened.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .model import AuditReport, Finding

_SPECIAL_ROLES = ("bos_token", "eos_token", "unk_token", "pad_token", "sep_token", "cls_token")
_PORTABILITY_PATTERNS = (
    (re.compile(r"\.(?:items|keys|values)\s*\("), "Python dict method calls such as .items() are not portable to all Jinja runtimes"),
    (re.compile(r"\.(?:lower|upper|strip|replace)\s*\("), "Python string methods are not portable to all Jinja runtimes; prefer Jinja filters"),
    (re.compile(r"\b(?:True|False|None)\b"), "Python boolean/null spelling is not portable; use true, false, or none"),
    (re.compile(r"\bloop\.(?:previtem|nextitem)\b"), "loop.previtem/loop.nextitem are not implemented by several non-Python Jinja runtimes"),
)


def _add(report: AuditReport, code: str, severity: str, message: str, path: str = "") -> None:
    report.findings.append(Finding(code, severity, message, path))


def _load_json(root: Path, name: str, report: AuditReport) -> Any | None:
    path = root / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        _add(report, "TB002", "error", f"cannot read {name}: {exc}", name)
    except json.JSONDecodeError as exc:
        _add(report, "TB003", "error", f"invalid JSON in {name}: {exc.msg} at line {exc.lineno}", name)
    return None


def _object(value: Any | None, report: AuditReport, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        _add(report, "TB004", "error", f"{name} must contain a JSON object", name)
        return {}
    return value


def _template_map(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        return {"default": value}
    if isinstance(value, dict):
        if isinstance(value.get("template"), str):
            return {str(value.get("name", "default")): value["template"]}
        return {str(key): text for key, text in value.items() if isinstance(text, str)}
    if isinstance(value, list):
        result: dict[str, str] = {}
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("template"), str):
                result[str(item.get("name", "default"))] = item["template"]
        return result
    return {}


def _token_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        content = value.get("content")
        return {content} if isinstance(content, str) else set()
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result.update(_token_strings(item))
        return result
    return set()


def _token_ids(value: Any) -> set[int]:
    if isinstance(value, dict):
        token_id = value.get("id")
        return {token_id} if isinstance(token_id, int) and not isinstance(token_id, bool) else set()
    if isinstance(value, list):
        result: set[int] = set()
        for item in value:
            result.update(_token_ids(item))
        return result
    return set()


def _check_templates(
    root: Path,
    report: AuditReport,
    tokenizer_config: dict[str, Any],
) -> None:
    embedded = _template_map(tokenizer_config.get("chat_template"))
    legacy = _load_json(root, "chat_template.json", report)
    legacy_templates = _template_map(legacy.get("chat_template")) if isinstance(legacy, dict) else {}

    files: dict[str, str] = {}
    default_path = root / "chat_template.jinja"
    if default_path.exists():
        try:
            files["default"] = default_path.read_text(encoding="utf-8")
        except OSError as exc:
            _add(report, "TB002", "error", f"cannot read chat_template.jinja: {exc}", "chat_template.jinja")
    extra_dir = root / "additional_chat_templates"
    if extra_dir.is_dir():
        for path in sorted(extra_dir.glob("*.jinja")):
            try:
                files[path.stem] = path.read_text(encoding="utf-8")
            except OSError as exc:
                _add(report, "TB002", "error", f"cannot read {path.name}: {exc}", str(path.relative_to(root)))

    sources = [embedded, legacy_templates, files]
    available = {name: text for source in sources for name, text in source.items()}
    if not available:
        _add(
            report,
            "TB120",
            "warning",
            "no chat template found; chat-model serving may fall back to a fragile runtime default",
        )
        return

    for source_name, source in (("tokenizer_config.json", embedded), ("chat_template.json", legacy_templates)):
        if "default" in files and "default" in source and files["default"] != source["default"]:
            _add(
                report,
                "TB124",
                "warning",
                "standalone chat_template.jinja differs from embedded default; Transformers gives the standalone file precedence",
                source_name,
            )

    if "default" not in available and len(available) > 1:
        _add(report, "TB121", "warning", "multiple named chat templates exist but no default template is defined")

    for name, template in sorted(available.items()):
        path = "chat_template.jinja" if name == "default" and name in files else "tokenizer_config.json"
        if template.count("{{") != template.count("}}"):
            _add(report, "TB125", "error", f"unbalanced expression delimiters in {name} chat template", path)
        if template.count("{%") != template.count("%}"):
            _add(report, "TB125", "error", f"unbalanced statement delimiters in {name} chat template", path)
        if template.count("{#") != template.count("#}"):
            _add(report, "TB125", "error", f"unbalanced comment delimiters in {name} chat template", path)
        if "messages" not in template:
            _add(report, "TB126", "warning", f"{name} chat template never references messages", path)
        if "add_generation_prompt" not in template:
            _add(report, "TB127", "warning", f"{name} chat template has no add_generation_prompt branch", path)
        for pattern, message in _PORTABILITY_PATTERNS:
            if pattern.search(template):
                _add(report, "TB128", "warning", f"{name} template: {message}", path)
        if "{% include" in template or "{% import" in template:
            _add(report, "TB129", "warning", f"{name} template depends on an external include/import", path)


def audit_bundle(bundle: str | Path) -> AuditReport:
    """Audit a local model/tokenizer bundle and return a stable report."""

    root = Path(bundle)
    report = AuditReport(str(root))
    if not root.exists():
        _add(report, "TB001", "error", "bundle path does not exist")
        return report
    if not root.is_dir():
        _add(report, "TB001", "error", "bundle path is not a directory")
        return report

    config = _object(_load_json(root, "config.json", report), report, "config.json")
    tokenizer_config = _object(_load_json(root, "tokenizer_config.json", report), report, "tokenizer_config.json")
    special_map = _object(_load_json(root, "special_tokens_map.json", report), report, "special_tokens_map.json")
    tokenizer = _object(_load_json(root, "tokenizer.json", report), report, "tokenizer.json")
    vocab_file = _object(_load_json(root, "vocab.json", report), report, "vocab.json")
    generation = _object(_load_json(root, "generation_config.json", report), report, "generation_config.json")

    known_tokens: set[str] = set()
    base_vocab_size: int | None = None
    model_section = tokenizer.get("model")
    if isinstance(model_section, dict):
        vocab = model_section.get("vocab")
        if isinstance(vocab, dict):
            known_tokens.update(str(key) for key in vocab)
            base_vocab_size = len(vocab)
        elif isinstance(vocab, list):
            known_tokens.update(str(item) for item in vocab if isinstance(item, str))
            base_vocab_size = len(vocab)
    if base_vocab_size is None and vocab_file:
        known_tokens.update(str(key) for key in vocab_file)
        base_vocab_size = len(vocab_file)

    added_tokens = tokenizer.get("added_tokens") if isinstance(tokenizer, dict) else []
    added_ids: list[int] = []
    if isinstance(added_tokens, list):
        for item in added_tokens:
            if not isinstance(item, dict):
                _add(report, "TB005", "error", "tokenizer.json added_tokens entries must be objects", "tokenizer.json")
                continue
            content = item.get("content")
            if isinstance(content, str):
                known_tokens.add(content)
            token_id = item.get("id")
            if isinstance(token_id, int) and not isinstance(token_id, bool):
                added_ids.append(token_id)

    config_vocab = config.get("vocab_size")
    if isinstance(config_vocab, bool) or (config_vocab is not None and not isinstance(config_vocab, int)):
        _add(report, "TB006", "error", "config.vocab_size must be an integer", "config.json#/vocab_size")
        config_vocab = None
    if base_vocab_size is None:
        _add(report, "TB100", "warning", "could not determine tokenizer vocabulary size; tokenizer.json or vocab.json is missing/incomplete")
    elif isinstance(config_vocab, int):
        if base_vocab_size > config_vocab:
            _add(report, "TB110", "error", f"tokenizer base vocabulary ({base_vocab_size}) exceeds config.vocab_size ({config_vocab})", "config.json#/vocab_size")
        elif base_vocab_size != config_vocab:
            _add(report, "TB111", "info", f"config.vocab_size ({config_vocab}) differs from tokenizer base vocabulary ({base_vocab_size}); padded vocabularies can be intentional", "config.json#/vocab_size")

    if added_ids and isinstance(config_vocab, int):
        for token_id in sorted(set(added_ids)):
            if token_id < 0 or token_id >= config_vocab:
                _add(report, "TB112", "error", f"added token id {token_id} is outside config.vocab_size {config_vocab}", "tokenizer.json#/added_tokens")
    if len(added_ids) != len(set(added_ids)):
        _add(report, "TB113", "error", "tokenizer.json contains duplicate added-token ids", "tokenizer.json#/added_tokens")

    all_special: dict[str, set[str]] = {}
    all_special_ids: dict[str, set[int]] = {}
    for role in _SPECIAL_ROLES:
        values = []
        if role in special_map:
            values.append(special_map[role])
        if role in tokenizer_config:
            values.append(tokenizer_config[role])
        if values:
            tokens = set().union(*(_token_strings(value) for value in values))
            ids = set().union(*(_token_ids(value) for value in values))
            all_special[role] = tokens
            all_special_ids[role] = ids
            for token in sorted(tokens):
                if token not in known_tokens:
                    _add(report, "TB104", "warning", f"{role} references token {token!r}, but it is not present in the discovered vocabulary", "special_tokens_map.json")

    for role, ids in all_special_ids.items():
        for token_id in sorted(ids):
            if isinstance(config_vocab, int) and (token_id < 0 or token_id >= config_vocab):
                _add(report, "TB105", "error", f"{role} id {token_id} is outside config.vocab_size {config_vocab}", "special_tokens_map.json")

    id_roles: dict[int, list[str]] = {}
    for role, ids in all_special_ids.items():
        for token_id in ids:
            id_roles.setdefault(token_id, []).append(role)
    for token_id, roles in sorted(id_roles.items()):
        if len(set(roles)) > 1:
            _add(report, "TB106", "info", f"special-token id {token_id} is shared by {', '.join(sorted(set(roles)))}", "special_tokens_map.json")

    for key in ("eos_token_id", "bos_token_id", "pad_token_id"):
        value = generation.get(key)
        ids = value if isinstance(value, list) else [value]
        for token_id in ids:
            if isinstance(token_id, int) and isinstance(config_vocab, int) and not 0 <= token_id < config_vocab:
                _add(report, "TB107", "error", f"generation_config.{key} contains out-of-range id {token_id}", f"generation_config.json#/{key}")

    _check_templates(root, report, tokenizer_config)
    report.findings.sort(key=lambda item: (item.severity != "error", item.severity != "warning", item.code, item.path, item.message))
    return report
