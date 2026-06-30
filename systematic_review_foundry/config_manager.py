"""
Configuration manager for the Systematic Review Foundry.
Handles user preferences, API keys, custom prompts, and model parameters.
"""
import json
import os
import copy
from pathlib import Path
from typing import Optional, Dict, Any

from default_prompts import DEFAULT_PROMPTS, DEFAULT_MODEL_PARAMS


def get_config_dir() -> Path:
    """Return the platform-appropriate config directory."""
    if os.name == 'nt':
        base = Path(os.environ.get('APPDATA', Path.home()))
    elif os.name == 'posix' and 'darwin' in os.uname().sysname.lower():
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    config_dir = base / 'SystematicReviewFoundry'
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_default_session_dir() -> Path:
    """Return the default directory for saving sessions."""
    d = Path.home() / 'Documents' / 'SystematicReviewFoundry'
    d.mkdir(parents=True, exist_ok=True)
    return d


class ConfigManager:
    """Manages application configuration, custom prompts, and API settings."""

    def __init__(self):
        self.config_path = get_config_dir() / 'config.json'
        self._config: Dict[str, Any] = {}
        self._load()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "active_session_path": str(get_default_session_dir() / "untitled.json"),
            "active_api": "claude",
            "claude_api_key": "",
            "claude_models": [],
            "claude_model": "claude-sonnet-4-6",
            "ncbi_api_key": "",
            "ollama_models": [],
            "ollama_url": "http://localhost:11434",
            "active_ollama_model": "",
            "custom_prompts": {},
            "custom_params": {},
            "master_params": {},
            "window_geometry": None,
            "recent_sessions": [],
            "auto_save_interval_seconds": 120,
            "institutional_credentials": {
                "username": "",
                "password": ""
            }
        }

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                # Merge with defaults so new keys are always present
                self._config = self._default_config()
                self._config.update(saved)
            except (json.JSONDecodeError, IOError):
                self._config = self._default_config()
        else:
            self._config = self._default_config()

    def save(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    # --- Getters / Setters ---

    @property
    def active_session_path(self) -> str:
        return self._config.get("active_session_path",
                                str(get_default_session_dir() / "untitled.json"))

    @active_session_path.setter
    def active_session_path(self, value: str):
        self._config["active_session_path"] = value
        # Track recent sessions
        recents = self._config.get("recent_sessions", [])
        if value in recents:
            recents.remove(value)
        recents.insert(0, value)
        self._config["recent_sessions"] = recents[:10]
        self.save()

    @property
    def active_api(self) -> str:
        return self._config.get("active_api", "claude")

    @active_api.setter
    def active_api(self, value: str):
        self._config["active_api"] = value
        self.save()

    @property
    def claude_api_key(self) -> str:
        return self._config.get("claude_api_key", "")

    @claude_api_key.setter
    def claude_api_key(self, value: str):
        self._config["claude_api_key"] = value
        self.save()

    @property
    def claude_model(self) -> str:
        return self._config.get("claude_model", "claude-sonnet-4-6")

    @claude_model.setter
    def claude_model(self, value: str):
        self._config["claude_model"] = value
        self.save()

    @property
    def claude_models(self) -> list:
        return self._config.get("claude_models", [])

    @claude_models.setter
    def claude_models(self, value: list):
        self._config["claude_models"] = value
        self.save()

    def fetch_claude_models(self) -> list:
        """Fetch available models from the Anthropic API and cache them.

        Returns the list of model ID strings, sorted with the most recent
        first.  Falls back to the cached list (or a sensible default) on
        any network / auth error.
        """
        import urllib.request
        import urllib.error

        api_key = self.claude_api_key
        if not api_key:
            return self.claude_models or ["claude-sonnet-4-6"]

        url = "https://api.anthropic.com/v1/models?limit=100"
        req = urllib.request.Request(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            model_ids = sorted(
                [m["id"] for m in data.get("data", [])],
                reverse=True,
            )
            if model_ids:
                self.claude_models = model_ids
                # If the active model is no longer available, reset to first
                if self.claude_model not in model_ids:
                    self._config["claude_model"] = model_ids[0]
                    self.save()
            return model_ids
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, OSError):
            return self.claude_models or ["claude-sonnet-4-6"]

    @property
    def ncbi_api_key(self) -> str:
        return self._config.get("ncbi_api_key", "")

    @ncbi_api_key.setter
    def ncbi_api_key(self, value: str):
        self._config["ncbi_api_key"] = value
        self.save()

    @property
    def ollama_url(self) -> str:
        return self._config.get("ollama_url", "http://localhost:11434")

    @ollama_url.setter
    def ollama_url(self, value: str):
        self._config["ollama_url"] = value
        self.save()

    @property
    def ollama_models(self) -> list:
        return self._config.get("ollama_models", [])

    @ollama_models.setter
    def ollama_models(self, value: list):
        self._config["ollama_models"] = value
        self.save()

    @property
    def active_ollama_model(self) -> str:
        return self._config.get("active_ollama_model", "")

    @active_ollama_model.setter
    def active_ollama_model(self, value: str):
        self._config["active_ollama_model"] = value
        self.save()

    @property
    def auto_save_interval(self) -> int:
        return self._config.get("auto_save_interval_seconds", 120)

    # --- Prompt Management ---

    def get_prompt(self, prompt_key: str) -> str:
        """Get the active prompt: custom if set, else default."""
        custom = self._config.get("custom_prompts", {}).get(prompt_key)
        if custom:
            return custom
        return DEFAULT_PROMPTS.get(prompt_key, "")

    def set_custom_prompt(self, prompt_key: str, prompt_text: str):
        if "custom_prompts" not in self._config:
            self._config["custom_prompts"] = {}
        self._config["custom_prompts"][prompt_key] = prompt_text
        self.save()

    def reset_prompt(self, prompt_key: str):
        customs = self._config.get("custom_prompts", {})
        if prompt_key in customs:
            del customs[prompt_key]
            self.save()

    def is_prompt_customized(self, prompt_key: str) -> bool:
        return prompt_key in self._config.get("custom_prompts", {})

    def get_all_prompt_keys(self) -> list:
        return list(DEFAULT_PROMPTS.keys())

    # --- Model Parameters ---

    def get_params_for_prompt(self, prompt_key: str) -> Dict[str, Any]:
        """Get parameters for a specific prompt. Falls back to master, then defaults."""
        custom = self._config.get("custom_params", {}).get(prompt_key)
        if custom:
            return custom
        master = self._config.get("master_params", {})
        if master:
            return master
        return copy.deepcopy(DEFAULT_MODEL_PARAMS)

    def set_params_for_prompt(self, prompt_key: str, params: Dict[str, Any]):
        if "custom_params" not in self._config:
            self._config["custom_params"] = {}
        self._config["custom_params"][prompt_key] = params
        self.save()

    def reset_params_for_prompt(self, prompt_key: str):
        customs = self._config.get("custom_params", {})
        if prompt_key in customs:
            del customs[prompt_key]
            self.save()

    def get_master_params(self) -> Dict[str, Any]:
        master = self._config.get("master_params", {})
        if master:
            return master
        return copy.deepcopy(DEFAULT_MODEL_PARAMS)

    def set_master_params(self, params: Dict[str, Any]):
        self._config["master_params"] = params
        self.save()

    def reset_master_params(self):
        self._config["master_params"] = {}
        self.save()

    @property
    def institutional_credentials(self) -> Dict[str, str]:
        return self._config.get("institutional_credentials", {"username": "", "password": ""})

    @institutional_credentials.setter
    def institutional_credentials(self, value: Dict[str, str]):
        self._config["institutional_credentials"] = value
        self.save()
