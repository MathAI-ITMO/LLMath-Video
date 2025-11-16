from __future__ import annotations

import json
import os
from datetime import datetime

from flask import Blueprint, jsonify

from ..llm import build_timecoded_transcript, generate_suggestions_with_llm
from ..storage import (
    LogStore,
    SubtitleStore,
    SuggestionStore,
    SummaryStore,
)


def register(
    app,
    summary_store: SummaryStore,
    suggestion_store: SuggestionStore,
    subtitle_store: SubtitleStore,
    log_store: LogStore,
    llm_config: dict,
    config: dict,
):
    bp = Blueprint("content", __name__)

    @bp.route("/summary/<path:filename>")
    def get_summary(filename):
        text = summary_store.read(filename)
        return jsonify({"text": text})

    @bp.route("/suggestions/<path:filename>")
    def get_suggestions(filename):
        try:
            existing = suggestion_store.read(filename) or {}
        except Exception as exc:
            return jsonify({"items": [], "error": str(exc)}), 200
        items = existing.get("items")
        if isinstance(items, list) and items:
            return jsonify({"items": items})
        try:
            segments = subtitle_store.read_segments(filename)
            if segments:
                timecoded = build_timecoded_transcript(segments)
                new_items = generate_suggestions_with_llm(
                    timecoded,
                    filename,
                    subs_count=len(segments),
                    llm_config=llm_config,
                    config=config,
                    logger=log_store.append,
                )
                if new_items:
                    suggestion_store.write_items(filename, new_items)
                    return jsonify({"items": new_items})
        except Exception as e:
            log_store.append(
                filename,
                {
                    "type": "error",
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "content": f"suggestions_on_demand_error: {str(e)}",
                },
            )
        return jsonify({"items": []})

    @bp.route("/logs/<path:filename>")
    def get_logs(filename):
        entries = log_store.read_entries(filename)
        return jsonify({"entries": entries})

    @bp.route("/logs/<path:filename>", methods=["DELETE"])
    def clear_logs(filename):
        try:
            log_store.clear(filename)
            return jsonify({"status": "cleared"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    app.register_blueprint(bp)

