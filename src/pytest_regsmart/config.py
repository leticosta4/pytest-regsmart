from __future__ import annotations
 
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
 
from _pytest.config import Config
 
from .ranking import rank_args
from .selection import selection_args
 
 
@dataclass
class PluginConfig:
    """Estado imutável derivado das options do pytest — separado da lógica dos hooks."""
 
    diff_level: Any  # DIFF_LEVEL
    diff_source: Any  # DIFF_SOURCE
    no_rank: bool
    weights: Any
    level: Any
    replay_file: Any
    hist_len: int
    seed: int
    graph_cache_dir: str | None = None
    branch: str | None = field(default=None, init=False)
 
    @classmethod
    def from_pytest_config(cls, config: Config) -> PluginConfig:
        cache_enabled = config.getini("graph_cache") and os.environ.get("REGSMART_GRAPH_CACHE") != "0"
        cache_dir = None
        if cache_enabled:
            explicit = os.environ.get("REGSMART_GRAPH_CACHE_DIR") or config.getini("graph_cache_dir")
            if explicit:
                path = Path(explicit)
                cache_dir = str((path if path.is_absolute() else Path(config.rootpath) / path).resolve())
            elif hasattr(config, "cache"):
                try:
                    cache_dir = str(config.cache.mkdir("pytest-regsmart"))
                except Exception:  # noqa: BLE001 - cache support must never break pytest
                    cache_dir = None
        return cls(
            diff_level=selection_args.parse_diff_level(config),
            diff_source=selection_args.parse_diff_source(config),
            no_rank=rank_args.parse_no_rank(config),
            weights=rank_args.parse_rtp_weights(config),
            level=rank_args.parse_rtp_level(config),
            replay_file=rank_args.parse_replay(config),
            hist_len=rank_args.parse_hist_len(config),
            seed=rank_args.parse_seed(config),
            graph_cache_dir=cache_dir,
        )
