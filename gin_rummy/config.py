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
    ai_level: str = "WARNING"  # Separate level for AI decision logging (WARNING hides decisions)
    log_file: str | None = None  # Optional file path for detailed logs


@dataclass
class GameRulesConfig:
    """Game rules configuration."""

    knock_threshold: int = 10
    gin_bonus: int = 25
    undercut_bonus: int = 25
    min_deck_cards: int = 2  # Round ends in draw when deck reaches this
    target_score: int = 100  # Score needed to win the game


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
class ContextAwareAIConfig:
    """Configuration for ContextAwareAI behavior."""

    # Base threshold before modifiers
    base_draw_threshold: int = 1

    # Outs calculation weights
    meld_completing_weight: float = 10.0
    run_extending_weight: float = 5.0
    set_building_weight: float = 4.0
    partial_meld_early_bonus: float = 2.0

    # Game phase boundaries (fraction of deck remaining)
    early_game_threshold: float = 0.7  # >70% deck = early game
    late_game_threshold: float = 0.3  # <30% deck = late game

    # Dynamic threshold modifiers
    max_deck_modifier: float = 2.0  # Max reduction from deck position
    max_outs_modifier: float = 2.0  # Max increase from having many outs
    trailing_aggressive_threshold: int = 50  # Points behind to get aggressive
    leading_conservative_threshold: int = 30  # Points ahead to get conservative

    # Bonus adjustments
    key_out_bonus: int = 3  # Bonus for meld-completing outs
    denial_bonus: int = 2  # Bonus for denying opponent
    safe_rank_discard_bonus: int = 1  # Bonus for discarding safe ranks
    dangerous_rank_penalty: int = 2  # Penalty for discarding ranks opponent picked up
    dangerous_suit_penalty: int = 1  # Penalty for discarding suits opponent picked up
    danger_card_penalty: int = 3  # Penalty for cards that complete opponent's inferred melds
    denial_probability_threshold: float = 0.7  # Opponent want probability to trigger

    # Opponent modeling
    track_opponent_patterns: bool = True


@dataclass
class Config:
    """Main configuration container."""

    logging: LoggingConfig = field(default_factory=LoggingConfig)
    game_rules: GameRulesConfig = field(default_factory=GameRulesConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    assist: AssistConfig = field(default_factory=AssistConfig)
    context_aware_ai: ContextAwareAIConfig = field(default_factory=ContextAwareAIConfig)

    @classmethod
    def load(cls, path: Path | str | None = None) -> Self:
        """Load configuration from TOML file(s).

        Supports two modes:
        1. Split config: config/ directory with separate .toml files by concern
        2. Single config: config.toml with all settings (backwards compatible)

        Args:
            path: Path to config file or directory. If None, looks for config/
                  directory first, then config.toml in standard locations.

        Returns:
            Config instance with values from file(s) (or defaults if not found).
        """
        if path is not None:
            config_path = Path(path)
            if config_path.is_dir():
                return cls._from_config_dir(config_path)
            elif config_path.exists():
                return cls._from_toml(config_path)
            else:
                logging.warning(f"Config path not found: {path}, using defaults")
                return cls()

        # Look for config/ directory first (split config)
        config_dir_paths = [
            Path.cwd() / "config",
            Path(__file__).parent.parent / "config",
            Path.home() / ".config" / "gin_rummy" / "config",
        ]

        for config_dir in config_dir_paths:
            if config_dir.is_dir() and any(config_dir.glob("*.toml")):
                return cls._from_config_dir(config_dir)

        # Fall back to single config.toml (backwards compatible)
        config_file_paths = [
            Path.cwd() / "config.toml",
            Path(__file__).parent.parent / "config.toml",
            Path.home() / ".config" / "gin_rummy" / "config.toml",
        ]

        for config_path in config_file_paths:
            if config_path.exists():
                return cls._from_toml(config_path)

        # No config found, use defaults
        return cls()

    @classmethod
    def _from_config_dir(cls, config_dir: Path) -> Self:
        """Load and merge config from a directory of TOML files."""
        merged_data: dict = {}

        # Load all .toml files in the directory
        for toml_file in sorted(config_dir.glob("*.toml")):
            with open(toml_file, "rb") as f:
                file_data = tomllib.load(f)
                # Merge into combined data
                for key, value in file_data.items():
                    if key in merged_data and isinstance(merged_data[key], dict):
                        merged_data[key].update(value)
                    else:
                        merged_data[key] = value

        return cls._from_data(merged_data)

    @classmethod
    def _from_toml(cls, path: Path) -> Self:
        """Parse config from a TOML file."""
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls._from_data(data)

    @classmethod
    def _from_data(cls, data: dict) -> Self:
        """Create Config from a dictionary of parsed TOML data."""
        logging_data = data.get("logging", {})
        game_rules_data = data.get("game_rules", {})
        ai_data = data.get("ai", {})
        display_data = data.get("display", {})
        database_data = data.get("database", {})
        assist_data = data.get("assist", {})
        context_aware_ai_data = data.get("context_aware_ai", {})

        return cls(
            logging=LoggingConfig(**logging_data),
            game_rules=GameRulesConfig(**game_rules_data),
            ai=AIConfig(**ai_data),
            display=DisplayConfig(**display_data),
            database=DatabaseConfig(**database_data),
            assist=AssistConfig(**assist_data),
            context_aware_ai=ContextAwareAIConfig(**context_aware_ai_data),
        )

    def setup_logging(self) -> None:
        """Configure logging based on settings."""
        # Set up root logger
        logging.basicConfig(
            level=getattr(logging, self.logging.level.upper(), logging.INFO),
            format=self.logging.format,
        )

        # Set AI logger level - use show_ai_thinking to override
        ai_logger = logging.getLogger("gin_rummy.ai")
        if self.display.show_ai_thinking:
            ai_logger.setLevel(logging.INFO)
        else:
            ai_logger.setLevel(
                getattr(logging, self.logging.ai_level.upper(), logging.WARNING)
            )

        # Optional file logging for detailed analysis
        if self.logging.log_file:
            file_handler = logging.FileHandler(self.logging.log_file)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(self.logging.format))
            logging.getLogger().addHandler(file_handler)
            # AI logger always logs to file at DEBUG level
            ai_logger.addHandler(file_handler)

    @classmethod
    def with_overrides(cls, override_path: Path | str) -> Self:
        """Create config with values overridden from another file.

        Loads the default config, then applies overrides from the
        specified file. Only values present in the override file
        are changed.

        Args:
            override_path: Path to TOML file with override values.

        Returns:
            Config with overrides applied.
        """
        from dataclasses import fields, replace

        # Load base config
        base = cls.load()

        # Load overrides
        override_path = Path(override_path)
        if not override_path.exists():
            raise FileNotFoundError(f"Override config not found: {override_path}")

        with open(override_path, "rb") as f:
            overrides = tomllib.load(f)

        # Helper to merge dataclass with dict updates
        def merge_dataclass(obj, updates):
            if not updates:
                return obj
            valid_updates = {}
            for f in fields(obj):
                if f.name in updates:
                    valid_updates[f.name] = updates[f.name]
            return replace(obj, **valid_updates) if valid_updates else obj

        # Apply overrides to each section
        return cls(
            logging=merge_dataclass(base.logging, overrides.get("logging", {})),
            game_rules=merge_dataclass(base.game_rules, overrides.get("game_rules", {})),
            ai=merge_dataclass(base.ai, overrides.get("ai", {})),
            display=merge_dataclass(base.display, overrides.get("display", {})),
            database=merge_dataclass(base.database, overrides.get("database", {})),
            assist=merge_dataclass(base.assist, overrides.get("assist", {})),
            context_aware_ai=merge_dataclass(
                base.context_aware_ai, overrides.get("context_aware_ai", {})
            ),
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
