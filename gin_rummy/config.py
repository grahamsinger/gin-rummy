"""Configuration management for Gin Rummy."""

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(name)s - %(levelname)s - %(message)s"
    ai_level: str = "INFO"  # Separate level for AI decision logging


@dataclass
class GameRulesConfig:
    """Game rules configuration."""

    knock_threshold: int = 10
    gin_bonus: int = 25
    undercut_bonus: int = 25
    min_deck_cards: int = 2  # Round ends in draw when deck reaches this


@dataclass
class AIConfig:
    """AI behavior configuration."""

    # Knock strategy: "always" = knock whenever possible, "conservative" = only with low deadwood
    knock_strategy: str = "always"
    conservative_knock_threshold: int = 5  # Only knock if deadwood <= this (when conservative)

    # Draw strategy: how much deadwood reduction is needed to take from discard
    min_deadwood_improvement: int = 1  # Take from discard if it reduces deadwood by at least this


@dataclass
class DisplayConfig:
    """Display and UI configuration."""

    clear_screen: bool = True
    ai_turn_delay: float = 0.5  # Seconds to pause during AI turns
    show_ai_thinking: bool = False  # Show what AI is considering


@dataclass
class DatabaseConfig:
    """Database configuration for game history tracking."""

    enabled: bool = True  # Whether to track game history
    path: str = "game_history.db"  # Path to SQLite database file
    track_ai_decisions: bool = True  # Track detailed AI decision reasoning


@dataclass
class AssistConfig:
    """Training assist mode configuration."""

    enabled: bool = True  # Show assist information during play
    show_values: bool = False  # Show actual card values (vs just counts)


@dataclass
class Config:
    """Main configuration container."""

    logging: LoggingConfig = field(default_factory=LoggingConfig)
    game_rules: GameRulesConfig = field(default_factory=GameRulesConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    assist: AssistConfig = field(default_factory=AssistConfig)

    @classmethod
    def load(cls, path: Path | str | None = None) -> Self:
        """Load configuration from a TOML file.

        Args:
            path: Path to config file. If None, looks for config.toml in
                  current directory, then in package directory.

        Returns:
            Config instance with values from file (or defaults if not found).
        """
        if path is not None:
            config_path = Path(path)
            if config_path.exists():
                return cls._from_toml(config_path)
            else:
                logging.warning(f"Config file not found: {path}, using defaults")
                return cls()

        # Look for config.toml in standard locations
        search_paths = [
            Path.cwd() / "config.toml",
            Path(__file__).parent.parent / "config.toml",
            Path.home() / ".config" / "gin_rummy" / "config.toml",
        ]

        for config_path in search_paths:
            if config_path.exists():
                return cls._from_toml(config_path)

        # No config file found, use defaults
        return cls()

    @classmethod
    def _from_toml(cls, path: Path) -> Self:
        """Parse config from a TOML file."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        logging_data = data.get("logging", {})
        game_rules_data = data.get("game_rules", {})
        ai_data = data.get("ai", {})
        display_data = data.get("display", {})
        database_data = data.get("database", {})
        assist_data = data.get("assist", {})

        return cls(
            logging=LoggingConfig(**logging_data),
            game_rules=GameRulesConfig(**game_rules_data),
            ai=AIConfig(**ai_data),
            display=DisplayConfig(**display_data),
            database=DatabaseConfig(**database_data),
            assist=AssistConfig(**assist_data),
        )

    def setup_logging(self) -> None:
        """Configure logging based on settings."""
        # Set up root logger
        logging.basicConfig(
            level=getattr(logging, self.logging.level.upper(), logging.INFO),
            format=self.logging.format,
        )

        # Set AI logger level separately
        ai_logger = logging.getLogger("gin_rummy.ai")
        ai_logger.setLevel(
            getattr(logging, self.logging.ai_level.upper(), logging.INFO)
        )


# Global config instance - loaded lazily
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance, loading it if necessary."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def load_config(path: Path | str | None = None) -> Config:
    """Load config from a specific path and set as global."""
    global _config
    _config = Config.load(path)
    return _config
