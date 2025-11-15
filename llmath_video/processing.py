from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from datetime import datetime
from typing import Dict, Iterable, Optional

from .llm import (
    build_timecoded_transcript,
    generate_suggestions_with_llm,
    summarize_with_llm,
    transcribe_audio,
)
from .storage import LogStore, SummaryStore


class ProcessingService:
    def __init__(
        self,
        llm_config: Dict,
        config: Dict,
        dirs: Dict[str, str],
        log_store: LogStore,
        summary_store: SummaryStore,
    ):
        self.llm_config = llm_config
        self.config = config
        self.dirs = dirs
        self.log_store = log_store
        self.summary_store = summary_store
        self.processing_flags = set()
        self._lock = threading.Lock()

    def append_log(self, filename: str, entry: dict):
        self.log_store.append(filename, entry)

    def queue(self, video_path: str, force: bool = False):
        key = os.path.abspath(video_path)
        if not force:
            if not self._needs_work(video_path):
                return
        with self._lock:
            if key in self.processing_flags:
                return
            self.processing_flags.add(key)
        thread = threading.Thread(
            target=self._worker,
            args=(video_path,),
            name=f"process:{os.path.basename(video_path)}",
            daemon=True,
        )
        thread.start()

    def _needs_work(self, video_path: str) -> bool:
        name = os.path.basename(video_path)
        base, _ = os.path.splitext(name)
        mp3_path = os.path.join(self.dirs["audio"], f"{base}.mp3")
        subs_json_path = os.path.join(self.dirs["subtitles"], f"{name}.json")
        summary_path = os.path.join(self.dirs["summaries"], f"{name}.txt")
        sugg_path = os.path.join(self.dirs["suggestions"], f"{name}.json")
        for path in (mp3_path, subs_json_path, summary_path, sugg_path):
            if not os.path.isfile(path):
                return True
        return False

    def _worker(self, save_path: str):
        name = os.path.basename(save_path)
        base, _ = os.path.splitext(name)
        mp3_path = os.path.join(self.dirs["audio"], f"{base}.mp3")
        subs_json_path = os.path.join(self.dirs["subtitles"], f"{name}.json")
        summary_path = os.path.join(self.dirs["summaries"], f"{name}.txt")
        sugg_path = os.path.join(self.dirs["suggestions"], f"{name}.json")

        try:
            try:
                if not os.path.isfile(mp3_path):
                    self.append_log(
                        name,
                        {
                            "type": "info",
                            "time": datetime.now().isoformat(timespec="seconds"),
                            "content": "extract_audio",
                        },
                    )
                    extract_audio_to_mp3(
                        save_path, self.dirs["audio"], self.dirs["base"]
                    )
            except Exception as e:
                self.append_log(
                    name,
                    {
                        "type": "error",
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "content": f"extract_audio_error: {e}",
                    },
                )

            segments = []
            try:
                if os.path.isfile(mp3_path) and not os.path.isfile(subs_json_path):
                    self.append_log(
                        name,
                        {
                            "type": "info",
                            "time": datetime.now().isoformat(timespec="seconds"),
                            "content": "transcribe",
                        },
                    )
                    segments = transcribe_audio(
                        mp3_path, self.llm_config, self.dirs["base"]
                    )
                    if segments:
                        os.makedirs(self.dirs["subtitles"], exist_ok=True)
                        with open(subs_json_path, "w", encoding="utf-8") as f:
                            json.dump({"segments": segments}, f, ensure_ascii=False)
            except Exception as e:
                self.append_log(
                    name,
                    {
                        "type": "error",
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "content": f"transcribe_error: {e}",
                    },
                )

            if not segments and os.path.isfile(subs_json_path):
                try:
                    with open(subs_json_path, "r", encoding="utf-8") as f:
                        segments = (json.load(f).get("segments") or [])
                except Exception:
                    segments = []
            full_text = " ".join(
                [(s or {}).get("text", "") for s in (segments or [])]
            ).strip()

            try:
                if full_text and not os.path.isfile(summary_path):
                    summary_text = summarize_with_llm(
                        full_text, name, self.llm_config, self.config, self.append_log
                    )
                    if summary_text:
                        os.makedirs(self.dirs["summaries"], exist_ok=True)
                        self.summary_store.write(name, summary_text)
            except Exception as e:
                self.append_log(
                    name,
                    {
                        "type": "error",
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "content": f"summary_error: {e}",
                    },
                )

            try:
                if segments and not os.path.isfile(sugg_path):
                    timecoded = build_timecoded_transcript(segments)
                    items = generate_suggestions_with_llm(
                        timecoded,
                        name,
                        subs_count=len(segments),
                        llm_config=self.llm_config,
                        config=self.config,
                        logger=self.append_log,
                    )
                    if isinstance(items, list) and items:
                        os.makedirs(self.dirs["suggestions"], exist_ok=True)
                        with open(sugg_path, "w", encoding="utf-8") as f:
                            json.dump({"items": items}, f, ensure_ascii=False)
            except Exception as e:
                self.append_log(
                    name,
                    {
                        "type": "error",
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "content": f"suggestions_error: {e}",
                    },
                )
        finally:
            with self._lock:
                self.processing_flags.discard(os.path.abspath(save_path))


def extract_audio_to_mp3(video_path: str, out_dir: str, base_dir: str) -> str:
    base = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join(out_dir, f"{base}.mp3")
    os.makedirs(out_dir, exist_ok=True)
    ffmpeg_bin = shutil.which("ffmpeg") or os.path.join(base_dir, "tools", "ffmpeg.exe")
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "48k",
        out_path,
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed: {result.stderr[:200].decode('utf-8', 'ignore')}"
        )
    return out_path

