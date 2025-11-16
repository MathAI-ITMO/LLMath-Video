from __future__ import annotations

from datetime import datetime
import logging

from flask import Blueprint, jsonify, request, url_for

from config_manager import get_llm_setting, get_prompt_template

from ..llm import call_openai_text, get_openai_client
from ..storage import FrameStore, LogStore, SubtitleStore, SummaryStore


def register(
    app,
    frame_store: FrameStore,
    summary_store: SummaryStore,
    subtitle_store: SubtitleStore,
    log_store: LogStore,
    llm_config: dict,
    config: dict,
):
    bp = Blueprint("llm_api", __name__)
    logger = logging.getLogger("llmath_video.api")

    @bp.route("/api/explain_frame", methods=["POST"])
    def explain_frame():
        data = request.get_json(silent=True) or {}
        name = data.get("name") or ""
        image_data_url = data.get("image") or ""
        current_time = float(data.get("currentTime") or 0)
        api_key = llm_config.get("openai_api_key")
        if not api_key:
            return jsonify({"answer": "LLM не настроен"}), 200

        img_rel_path = frame_store.save_data_url(name, image_data_url)

        summary_text = summary_store.read(name)
        subs_text = _subtitles_before_time(
            subtitle_store.read_segments(name), current_time
        )

        system = get_prompt_template(config, "frame_system")
        tpl = get_prompt_template(config, "frame_user_template")
        user_prompt = tpl.format(lecture=name, summary=summary_text, context=subs_text)

        client = get_openai_client(llm_config)
        model = get_llm_setting(llm_config, "openai_model")

        img_url_for_log = (
            url_for("media.serve_frame", filename=img_rel_path)
            if img_rel_path
            else None
        )
        now_req = datetime.now().isoformat(timespec="seconds")
        log_store.append(
            name,
            {
                "type": "frame_request",
                "time": now_req,
                "model": model,
                "content": user_prompt,
                "image_url": img_url_for_log,
            },
        )

        answer = ""
        last_err = None
        for attempt in range(3):
            try:
                chat = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"{system}\n\n{user_prompt}"},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": image_data_url},
                                },
                            ],
                        }
                    ],
                )
                answer = (chat.choices[0].message.content or "").strip()
                break
            except Exception as e:
                last_err = e
                msg = str(e)
                # Log full stack for debugging unexpected failures
                logger.exception("explain_frame request failed: name=%s attempt=%s", name, attempt + 1)
                if "429" in msg or "rate" in msg.lower():
                    import time

                    time.sleep(1.5 * (attempt + 1))
                    continue
                break

        now = datetime.now().isoformat(timespec="seconds")
        if answer:
            log_store.append(
                name,
                {
                    "type": "frame_response",
                    "time": now,
                    "content": answer,
                    "image_url": img_url_for_log,
                },
            )
            return jsonify({"answer": answer, "image_url": img_url_for_log})
        err_text = str(last_err) if last_err else "Неизвестная ошибка LLM"
        logger.error("explain_frame error: name=%s err=%s", name, err_text)
        log_store.append(
            name,
            {"type": "error", "time": now, "content": err_text},
        )
        return jsonify({"answer": "Ошибка обращения к LLM"}), 200

    @bp.route("/api/chat", methods=["POST"])
    def api_chat():
        data = request.get_json(silent=True) or {}
        name = data.get("name") or ""
        current_time = float(data.get("currentTime") or 0)
        dialog = data.get("dialog") or []
        question = data.get("question") or ""
        api_key = llm_config.get("openai_api_key")
        if not api_key:
            return jsonify({"answer": "LLM не настроен"}), 200

        segments = subtitle_store.read_segments(name)
        subs_text = _subtitles_before_time(segments, current_time)[-3000:]
        summary_text = summary_store.read(name)

        dialog_items = list(dialog or [])
        if dialog_items and (
            dialog_items[-1].get("role") == "student"
            and dialog_items[-1].get("text", "").strip() == question.strip()
        ):
            dialog_items = dialog_items[:-1]
        dialog_items = [m for m in dialog_items if (m or {}).get("kind") != "frame"]
        prev_lines = []
        for m in dialog_items:
            role = m.get("role")
            txt = (m.get("text") or "").strip()
            if not txt:
                continue
            label = "Студент" if role == "student" else ("Лектор" if role == "lecturer" else "Система")
            prev_lines.append(f"{label}: {txt}")
        prev_text = "\n".join(prev_lines)
        if len(prev_text) > 8000:
            prev_text = prev_text[-8000:]

        tpl = get_prompt_template(config, "chat_user_template")
        user_prompt = tpl.format(
            lecture=name,
            summary=summary_text,
            context=subs_text,
            history=prev_text,
            question=question,
        )

        client = get_openai_client(llm_config)
        model = get_llm_setting(llm_config, "openai_model")
        system = get_prompt_template(config, "chat_system")
        prompt = f"{system}\n\n{user_prompt}"
        now_req = datetime.now().isoformat(timespec="seconds")
        log_store.append(
            name,
            {"type": "chat_request", "time": now_req, "model": model, "content": prompt},
        )
        try:
            answer = call_openai_text(client, model, prompt)
        except Exception as e:
            now = datetime.now().isoformat(timespec="seconds")
            log_store.append(name, {"type": "error", "time": now, "content": str(e)})
            logger.exception("chat request failed: name=%s", name)
            return jsonify({"answer": "Ошибка обращения к LLM"}), 200
        now = datetime.now().isoformat(timespec="seconds")
        if answer:
            log_store.append(
                name,
                {"type": "chat_response", "time": now, "content": answer},
            )
            return jsonify({"answer": answer})
        log_store.append(
            name,
            {"type": "error", "time": now, "content": "Не удалось получить ответ"},
        )
        logger.error("chat error: name=%s err=%s", name, "Не удалось получить ответ")
        return jsonify({"answer": "Ошибка обращения к LLM"}), 200

    app.register_blueprint(bp)


def _subtitles_before_time(segments, current_time: float) -> str:
    parts: list[str] = []
    for item in segments or []:
        try:
            if float(item.get("start", 0)) < current_time:
                parts.append(item.get("text", ""))
        except Exception:
            continue
    return " ".join(parts)

