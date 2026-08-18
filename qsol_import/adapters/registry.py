from __future__ import annotations

from typing import Any

from qsol_import.adapter_contract import Adapter, AdapterError
from qsol_import.adapters.claude import ClaudeAdapter
from qsol_import.adapters.gemini import GeminiAdapter
from qsol_import.adapters.generic import GenericAdapter
from qsol_import.adapters.github import GitHubAdapter
from qsol_import.adapters.grok import GrokAdapter
from qsol_import.adapters.openai_contract import OpenAIContractAdapter


_ADAPTERS: dict[str, Adapter] = {
    "grok": GrokAdapter(),
    "claude": ClaudeAdapter(),
    "gemini": GeminiAdapter(),
    "github": GitHubAdapter(),
    "generic": GenericAdapter(),
    "openai-common": OpenAIContractAdapter(),
}


def adapter_names() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def get_adapter(name: str) -> Adapter:
    try:
        return _ADAPTERS[name]
    except KeyError as exc:
        raise AdapterError("unknown_adapter", f"unknown adapter: {name!r}") from exc


def adapter_registry() -> list[dict[str, Any]]:
    return [get_adapter(name).descriptor() for name in adapter_names()]
