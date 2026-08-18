# sentinel/config_loader.py
import json
import logging
import os
import re
from pathlib import Path

# Provide standard abstraction layer with environment variable interpolation and secret protection.
class ConfigLoader:
    def __init__(self, config_file: str = "config.json"):
        self.config_path = Path(__file__).parent / config_file
        self._config_cache = None

    def _resolve_env_var(self, value):
        """
        Expands environment variables formatted as ${VAR} or ${VAR:-default}.
        If the value is a direct string, checks if an uppercase env var exists as an override.
        """
        if isinstance(value, str):
            # Pattern for ${VAR} or ${VAR:-default}
            pattern = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")
            def replace_match(match):
                var_name = match.group(1)
                default_val = match.group(2) if match.group(2) is not None else ""
                return os.environ.get(var_name, default_val)
            
            return pattern.sub(replace_match, value)
        elif isinstance(value, dict):
            return {k: self._resolve_env_var(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_env_var(item) for item in value]
        return value

    def _load(self):
        if not self.config_path.exists():
            raise FileNotFoundError(f"Missing core configuration file: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            try:
                raw_config = json.load(f)
                self._config_cache = self._resolve_env_var(raw_config)
            except json.JSONDecodeError as e:
                logging.error(f"Config corruption detected within {self.config_path}: {e}")
                raise

    def get(self, section: str, key: str = None):
        """ Fetch config securely with fail-closed properties and env var override support. """
        if self._config_cache is None:
            self._load()
        
        # Check direct env var override for specific section.key (e.g., CLOUDFLARE_TUNNEL_TOKEN)
        if key is not None:
            env_key = f"{key.upper()}"
            if env_key in os.environ and os.environ[env_key]:
                return os.environ[env_key]
            
            compound_env_key = f"{section.upper()}_{key.upper()}"
            if compound_env_key in os.environ and os.environ[compound_env_key]:
                return os.environ[compound_env_key]

        sec_data = self._config_cache.get(section)
        if sec_data is None:
            raise KeyError(f"Configuration section missing: {section}")
        
        if key is not None:
            val = sec_data.get(key)
            if val is None:
                raise KeyError(f"Configuration key missing: {section}.{key}")
            return val
            
        return sec_data

    def reload(self):
        """ Force re-read of configuration and environment variables. """
        self._config_cache = None
        self._load()

# Global instantiation
config = ConfigLoader()
