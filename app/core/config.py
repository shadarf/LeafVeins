"""Configuration management for LeafVeins."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Manages application configuration."""
    
    DEFAULT_CONFIG = {
        "editor": {
            "font_family": "Consolas",
            "font_size": 11,
            "tab_width": 4,
            "use_spaces": True,
            "line_numbers": True,
            "word_wrap": False,
            "auto_save": True,
            "auto_save_interval": 30,
            "highlight_current_line": True,
            "bracket_matching": True,
            "edit_mode": False,
        },
        "preview": {
            "auto_refresh": True,
            "zoom_level": 100,
            "show_margins": True,
            "sync_scroll": False,
        },
        "compiler": {
            "default_compiler": "pdflatex",
            "timeout": 60,
            "max_passes": 5,
            "bibtex_enabled": True,
            "makeindex_enabled": True,
            "shell_escape": False,
            "synctex": True,
            "stop_on_first_error": False,
            "compile_size_limit": "7mb",
            "texlive_openout_any": "",
            "texlive_max_print_line": "",
            "compiler_paths": {
                "pdflatex": "",
                "xelatex": "",
                "lualatex": "",
                "bibtex": "",
                "biber": "",
                "makeindex": "",
            },
        },
        "latexmk": {
            "use_latexmk": True,
            "flags": [],
            "force_continue_on_error": True,  # -f flag (opposite of stop_on_first_error)
            "sync_method": "latexmk",  # latexmk handles SyncTeX
        },
        "project": {
            "expire_after_idle_hours": 24,
            "check_interval_minutes": 10,
            "max_fdb_size_mb": 1,
        },
        "ui": {
            "theme": "dark",
            "show_file_tree": True,
            "show_preview": True,
            "show_console": True,
            "file_tree_width": 250,
            "preview_width": 500,
            "console_height": 200,
            "recent_projects": [],
            "maximized": False,
            "window_geometry": None,
        },
        "project": {
            "default_main_file": "main.tex",
            "backup_on_compile": True,
            "max_backups": 10,
        },
    }
    
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            # Use AppData on Windows
            if os.name == 'nt':
                config_dir = Path(os.environ.get('APPDATA', Path.home())) / 'LeafVeins'
            else:
                config_dir = Path.home() / '.config' / 'leafveins'
        
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / 'config.json'
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                # Merge with defaults to ensure all keys exist
                return self._merge_configs(self.DEFAULT_CONFIG, user_config)
            except (json.JSONDecodeError, IOError):
                pass
        return self.DEFAULT_CONFIG.copy()
    
    def _merge_configs(self, default: Dict, user: Dict) -> Dict:
        """Recursively merge user config with defaults."""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    def save(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
        except IOError as e:
            print(f"Failed to save config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key (e.g., 'editor.font_size')."""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value by dot-notation key."""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save()
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire configuration section."""
        return self._config.get(section, {}).copy()
    
    def update_section(self, section: str, values: Dict[str, Any]) -> None:
        """Update entire configuration section."""
        if section not in self._config:
            self._config[section] = {}
        self._config[section].update(values)
        self.save()
    
    def detect_compilers(self) -> Dict[str, str]:
        """Auto-detect LaTeX compiler paths on Windows."""
        import shutil
        
        paths = {}
        compilers = ['pdflatex', 'xelatex', 'lualatex', 'bibtex', 'biber', 'makeindex']
        
        # Check PATH first
        for compiler in compilers:
            path = shutil.which(compiler)
            if path:
                paths[compiler] = path
        
        # Check common Windows locations
        common_paths = [
            r"C:\Program Files\MiKTeX\miktex\bin\x64",
            r"C:\Program Files\MiKTeX\miktex\bin",
            r"C:\texlive\2024\bin\win32",
            r"C:\texlive\2023\bin\win32",
            r"C:\texlive\2022\bin\win32",
            r"C:\texlive\2021\bin\win32",
        ]
        
        for base_path in common_paths:
            base = Path(base_path)
            if base.exists():
                for compiler in compilers:
                    if compiler not in paths:
                        exe = base / f"{compiler}.exe"
                        if exe.exists():
                            paths[compiler] = str(exe)
        
        return paths
    
    def auto_configure_compilers(self) -> None:
        """Auto-detect and configure compiler paths."""
        detected = self.detect_compilers()
        current = self.get('compiler.compiler_paths', {})
        current.update(detected)
        self.set('compiler.compiler_paths', current)


# Global config instance
_config: Optional[Config] = None


def get_config(config_dir: Optional[Path] = None) -> Config:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = Config(config_dir)
    return _config