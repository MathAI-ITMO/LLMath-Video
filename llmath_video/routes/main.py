from __future__ import annotations

import os

from flask import Blueprint, redirect, render_template, request, url_for

from ..storage import VideoStore


def register(app, video_store: VideoStore, config: dict):
    bp = Blueprint("main", __name__)

    @bp.route("/")
    def index():
        embedded = request.args.get("embedded", "").lower() == "true"
        return render_template(
            "index.html",
            subtitles_panel_enabled=False,
            embedded=embedded,
        )

    @bp.route("/<path:filename>")
    def open_single(filename):
        reserved = (
            "video/",
            "subtitles/",
            "frames/",
            "summary/",
            "suggestions/",
            "logs/",
            "api/",
            "static/",
            "favicon.ico",
        )
        for pref in reserved:
            if filename.startswith(pref):
                return redirect(url_for("main.index"))
        safe_name = os.path.basename(filename)
        if not video_store.allowed_file(safe_name):
            return redirect(url_for("main.index"))
        candidate = video_store.path_for(safe_name)
        if not os.path.isfile(candidate):
            return redirect(url_for("main.index"))
        subtitles_panel_enabled = bool(
            config.get("subtitles_panel_enabled", True)
        )
        return render_template(
            "index.html",
            subtitles_panel_enabled=subtitles_panel_enabled,
            single_name=safe_name,
        )

    app.register_blueprint(bp)

