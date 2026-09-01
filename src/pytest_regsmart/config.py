from __future__ import annotations
 
from dataclasses import dataclass, field
from typing import Any
 
from _pytest.config import Config
 
from .ranking import rank_args
from .selection import selection_args
 
 
@dataclass
class PluginConfig:
    """Estado imutável derivado das options do pytest — separado da lógica dos hooks."""
 
    diff_level: Any  # DIFF_LEVEL — ajuste o tipo se quiser importar de .const
    no_rank: bool
    weights: Any
    level: Any
    replay_file: Any
    hist_len: int
    seed: int
    branch: str | None = field(default=None, init=False)
 
    @classmethod
    def from_pytest_config(cls, config: Config) -> "PluginConfig":
        return cls(
            diff_level=selection_args.parse_diff_level(config),
            no_rank=rank_args.parse_no_rank(config),
            weights=rank_args.parse_rtp_weights(config),
            level=rank_args.parse_rtp_level(config),
            replay_file=rank_args.parse_replay(config),
            hist_len=rank_args.parse_hist_len(config),
            seed=rank_args.parse_seed(config),
        )