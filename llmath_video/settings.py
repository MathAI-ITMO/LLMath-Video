from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict

from config_manager import (
    build_llm_config,
    ensure_data_directories,
    load_config,
)


@dataclass(frozen=True)
class DataDirectories:
    video: str
    audio: str
    subtitles: str
    frames: str
    summaries: str
    logs: str
    suggestions: str


@dataclass(frozen=True)
class AppSettings:
    base_dir: str
    config: Dict
    llm_config: Dict
    dirs: DataDirectories
    allowed_extensions: frozenset[str]

    def as_dict(self) -> Dict:
        return {
            "base_dir": self.base_dir,
            "config": self.config,
            "llm_config": self.llm_config,
            "dirs": self.dirs,
            "allowed_extensions": self.allowed_extensions,
        }


def load_settings(base_dir: str) -> AppSettings:
    config = load_config(base_dir)
    dirs = ensure_data_directories(base_dir)
    data_dirs = DataDirectories(
        video=dirs["video"],
        audio=dirs["audio"],
        subtitles=dirs["subtitles"],
        frames=dirs["frames"],
        summaries=dirs["summaries"],
        logs=dirs["logs"],
        suggestions=dirs["suggestions"],
    )
    llm_config = build_llm_config(config)
    allowed_extensions = frozenset({".mp4", ".webm", ".ogg", ".mkv", ".mov"})
    return AppSettings(
        base_dir=os.path.abspath(base_dir),
        config=config,
        llm_config=llm_config,
        dirs=data_dirs,
        allowed_extensions=allowed_extensions,
    )

