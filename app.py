import os
from flask import Flask, render_template, request, send_from_directory, jsonify, redirect, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
import shutil
import subprocess
import json
import base64
from datetime import datetime


def create_app():
    """
    Factory function to create and configure the Flask application.

    The application serves a simple video player interface. Users can upload
    video files via dragвЂ‘andвЂ‘drop or by selecting from previously uploaded
    files. Uploaded videos are stored on the server and made available for
    playback through the same web interface.
    """
    app = Flask(
        __name__,
        static_url_path='/static',
        static_folder='static',
        template_folder='templates'
    )
    # Ensure JSON responses keep Unicode (Cyrillic) intact
    app.config['JSON_AS_ASCII'] = False
    
    # Enable CORS for frontend integration
    CORS(app, resources={r"/*": {"origins": ["http://localhost:8080", "http://127.0.0.1:8080"]}})

    # Directories
    base_dir = os.path.abspath(os.path.dirname(__file__))
    video_dir = os.path.join(base_dir, 'data', 'video')
    audio_dir = os.path.join(base_dir, 'data', 'audio')
    subs_dir = os.path.join(base_dir, 'data', 'subtitles')
    frames_dir = os.path.join(base_dir, 'data', 'frames')
    summary_dir = os.path.join(base_dir, 'data', 'summaries')
    logs_dir = os.path.join(base_dir, 'data', 'logs')
    suggestions_dir = os.path.join(base_dir, 'data', 'suggestions')
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(subs_dir, exist_ok=True)
    os.makedirs(summary_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(suggestions_dir, exist_ok=True)

    # Load config
    config_path = os.path.join(base_dir, 'config.json')
    default_config = {
        "subtitles_panel_enabled": True,
        "openai_api_key": "",
        "openai_api_base": "https://api.openai.com/v1",
        "openai_model": "gpt-5-nano",
        "transcription_mode": "openai",
        "openai_stt_model": "gpt-4o-transcribe",
        "whisper_model": "tiny",
        "whisper_language": "ru"
    }
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Allowed video extensions for upload
    ALLOWED_EXTENSIONS = {'.mp4', '.webm', '.ogg', '.mkv', '.mov'}

    def allowed_file(filename: str) -> bool:
        """Return True if the file has an allowed video extension."""
        _, ext = os.path.splitext(filename.lower())
        return ext in ALLOWED_EXTENSIONS

    @app.route('/')
    def index():
        """
        Render the main page which contains the video player, sidebar, and
        upload/list panel.
        """
        # Check if embedded mode is requested
        embedded = request.args.get('embedded', '').lower() == 'true'
        # Disable subtitles panel on main page (only show on single video pages)
        return render_template('index.html', 
                             subtitles_panel_enabled=False,
                             embedded=embedded)

    @app.route('/videos', methods=['GET'])
    def list_videos():
        """
        Return a JSON array of available videos. The list is sorted by
        modification time (most recent first). Each entry contains the
        filename and a URL to access the video.
        """
        videos = []
        for name in os.listdir(video_dir):
            file_path = os.path.join(video_dir, name)
            if os.path.isfile(file_path) and allowed_file(name):
                videos.append({
                    'name': name,
                    'mtime': os.path.getmtime(file_path),
                    'url': url_for('serve_video', filename=name)
                })
        # Sort by modification time descending
        videos.sort(key=lambda x: x['mtime'], reverse=True)
        # Strip mtime from response
        for v in videos:
            v.pop('mtime', None)
        return jsonify(videos)

    # Background processing control to avoid long blocking uploads
    processing_flags = set()

    def start_background_processing(save_path: str, force: bool = False):
        name = os.path.basename(save_path)
        base, _ = os.path.splitext(name)
        mp3_path = os.path.join(audio_dir, f"{base}.mp3")
        subs_json_path = os.path.join(subs_dir, f"{name}.json")
        summary_path = os.path.join(summary_dir, f"{name}.txt")
        sugg_path = os.path.join(suggestions_dir, f"{name}.json")

        def needs_work() -> bool:
            if not os.path.isfile(mp3_path):
                return True
            if not os.path.isfile(subs_json_path):
                return True
            if not os.path.isfile(summary_path):
                return True
            if not os.path.isfile(sugg_path):
                return True
            return False

        if not force and not needs_work():
            return
        key = os.path.abspath(save_path)
        if key in processing_flags:
            return
        processing_flags.add(key)

        def worker():
            try:
                # Extract audio
                try:
                    if not os.path.isfile(mp3_path):
                        append_log(name, {"type": "info", "time": datetime.now().isoformat(timespec='seconds'), "content": "extract_audio"})
                        extract_audio_to_mp3(save_path, audio_dir)
                except Exception as e:
                    append_log(name, {"type": "error", "time": datetime.now().isoformat(timespec='seconds'), "content": f"extract_audio_error: {e}"})

                # Transcribe
                segments = []
                try:
                    if os.path.isfile(mp3_path) and not os.path.isfile(subs_json_path):
                        append_log(name, {"type": "info", "time": datetime.now().isoformat(timespec='seconds'), "content": "transcribe"})
                        segments = transcribe_audio(mp3_path)
                        if segments:
                            os.makedirs(subs_dir, exist_ok=True)
                            with open(subs_json_path, 'w', encoding='utf-8') as f:
                                json.dump({"segments": segments}, f, ensure_ascii=False)
                except Exception as e:
                    append_log(name, {"type": "error", "time": datetime.now().isoformat(timespec='seconds'), "content": f"transcribe_error: {e}"})

                # Load segments if not present
                if not segments and os.path.isfile(subs_json_path):
                    try:
                        with open(subs_json_path, 'r', encoding='utf-8') as f:
                            segments = (json.load(f).get('segments') or [])
                    except Exception:
                        segments = []
                full_text = " ".join([(s or {}).get('text', '') for s in (segments or [])]).strip()

                # Summary
                try:
                    if full_text and not os.path.isfile(summary_path):
                        append_log(name, {"type": "summary_request", "time": datetime.now().isoformat(timespec='seconds'), "model": config.get('openai_model'), "content": (config.get('prompts', {}) or {}).get('summary') or ''})
                        summary_text = summarize_with_llm(full_text, name)
                        if summary_text:
                            os.makedirs(summary_dir, exist_ok=True)
                            with open(summary_path, 'w', encoding='utf-8') as sf:
                                sf.write(summary_text)
                            append_log(name, {"type": "summary_response", "time": datetime.now().isoformat(timespec='seconds'), "content": summary_text})
                except Exception as e:
                    append_log(name, {"type": "error", "time": datetime.now().isoformat(timespec='seconds'), "content": f"summary_error: {e}"})

                # Suggestions
                try:
                    if segments and not os.path.isfile(sugg_path):
                        timecoded = build_timecoded_transcript(segments)
                        items = generate_suggestions_with_llm(timecoded, name, subs_count=len(segments))
                        if isinstance(items, list) and items:
                            os.makedirs(suggestions_dir, exist_ok=True)
                            with open(sugg_path, 'w', encoding='utf-8') as f:
                                json.dump({"items": items}, f, ensure_ascii=False)
                except Exception as e:
                    append_log(name, {"type": "error", "time": datetime.now().isoformat(timespec='seconds'), "content": f"suggestions_error: {e}"})
            finally:
                processing_flags.discard(key)

        import threading as _th
        _th.Thread(target=worker, name=f"process:{name}", daemon=True).start()

    @app.route('/video/<path:filename>')
    def serve_video(filename):
        """
        Serve a video file from the configured video directory.

        Flask will handle range requests automatically when using
        ``send_from_directory`` and the appropriate headers. This enables
        streaming of large video files in the browser.
        """
        return send_from_directory(video_dir, filename, as_attachment=False)

    @app.route('/video/<path:filename>', methods=['DELETE'])
    def delete_video(filename):
        """Delete video and related audio/subtitle files."""
        # Sanitize and resolve paths
        filename = os.path.basename(filename)
        video_path = os.path.join(video_dir, filename)
        base, _ = os.path.splitext(filename)
        audio_path = os.path.join(audio_dir, f"{base}.mp3")
        subs_path = os.path.join(subs_dir, f"{filename}.json")
        sugg_path = os.path.join(suggestions_dir, f"{filename}.json")

        errors = []
        deleted = []
        for path in (video_path, audio_path, subs_path, sugg_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    deleted.append(os.path.basename(path))
            except Exception as e:
                errors.append(str(e))
        status = 200 if not errors else 207  # 207 Multi-Status like
        return jsonify({"deleted": deleted, "errors": errors}), status

    @app.route('/upload', methods=['POST'])
    def upload_video():
        """
        Handle video uploads. Accepts a single file from the ``file`` field of
        the request. Stores the file in the video directory if it has a
        permitted extension.
        Returns a JSON response indicating success or failure along with
        information about the uploaded file.
        """
        if 'file' not in request.files:
            return jsonify({'error': 'No file part in the request'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        # Preserve Unicode (Cyrillic) names while avoiding directory traversal
        # Use basename and strip dangerous characters, but keep letters/numbers/space/._-()
        original_name = file.filename or ''
        filename = os.path.basename(original_name)
        if not filename:
            return jsonify({'error': 'РќРµРєРѕСЂСЂРµРєС‚РЅРѕРµ РёРјСЏ С„Р°Р№Р»Р°'}), 400
        # Split extension and validate
        base, ext = os.path.splitext(filename)
        if not allowed_file(filename):
            return jsonify({'error': 'РќРµРїРѕРґРґРµСЂР¶РёРІР°РµРјС‹Р№ С‚РёРї С„Р°Р№Р»Р°'}), 400
        # Filter out characters not suitable for filenames on common OS
        allowed_chars = " ._()-"
        safe_base = ''.join(ch for ch in base if ch.isalnum() or ch in allowed_chars)
        safe_base = safe_base.strip()
        if not safe_base:
            safe_base = 'video'
        filename = f"{safe_base}{ext}"
        save_path = os.path.join(video_dir, filename)
        # If a file with the same name already exists, modify the name
        # to avoid overwriting. Append a numeric suffix.
        base = safe_base
        counter = 1
        while os.path.exists(save_path):
            new_name = f"{base}_{counter}{ext}"
            save_path = os.path.join(video_dir, new_name)
            counter += 1
        file.save(save_path)

        # Queue background processing and return quickly to avoid timeouts
        start_background_processing(save_path)

        # Return the video entry as it would appear in /videos
        rel_name = os.path.basename(save_path)
        return jsonify({
            'name': rel_name,
            'url': url_for('serve_video', filename=rel_name)
        }), 201

    @app.route('/api/ensure_processed', methods=['POST'])
    def api_ensure_processed():
        data = request.get_json(silent=True) or {}
        name = request.args.get('name') or (data.get('name') if isinstance(data, dict) else None) or request.form.get('name') or ''
        name = os.path.basename(name)
        if not name:
            return jsonify({"status": "error", "error": "missing name"}), 400
        video_path = os.path.join(video_dir, name)
        if not os.path.isfile(video_path):
            return jsonify({"status": "error", "error": "not found"}), 404
        start_background_processing(video_path)
        return jsonify({"status": "queued"})

    @app.route('/subtitles/<path:filename>.json')
    def serve_subtitles(filename):
        path = os.path.join(subs_dir, f"{filename}.json")
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        return jsonify({"segments": []}), 200

    @app.route('/frames/<path:filename>')
    def serve_frame(filename):
        # Securely serve saved frame images
        safe_path = os.path.abspath(os.path.join(frames_dir, filename))
        if not safe_path.startswith(os.path.abspath(frames_dir)):
            return jsonify({'error': 'invalid path'}), 400
        if not os.path.isfile(safe_path):
            return jsonify({'error': 'not found'}), 404
        return send_from_directory(os.path.dirname(safe_path), os.path.basename(safe_path), as_attachment=False)

    @app.route('/favicon.ico')
    def favicon():
        # Return no-content to silence 404s in console
        return ('', 204)

    def extract_audio_to_mp3(video_path: str, out_dir: str) -> str:
        """Extract audio track to MP3 using ffmpeg (system or bundled).

        On Linux/macOS, uses system ffmpeg if available. On Windows, falls back
        to tools/ffmpeg.exe if found. Produces mono/16kHz audio at ~48 kbps to
        keep payloads small for remote STT.
        """
        base = os.path.splitext(os.path.basename(video_path))[0]
        out_path = os.path.join(out_dir, f"{base}.mp3")
        os.makedirs(out_dir, exist_ok=True)
        ffmpeg_bin = shutil.which('ffmpeg') or os.path.join(base_dir, 'tools', 'ffmpeg.exe')
        cmd = [
            ffmpeg_bin, '-y', '-i', video_path,
            '-vn', '-ac', '1', '-ar', '16000', '-codec:a', 'libmp3lame', '-b:a', '48k',
            out_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[:200].decode('utf-8', 'ignore')}")
        return out_path

    def transcribe_with_whisper(audio_path: str):
        """Transcribe audio to segments using OpenAI Whisper."""
        import whisper
        w_model = str(config.get('whisper_model', 'tiny'))
        language = str(config.get('whisper_language', 'ru'))
        model = whisper.load_model(w_model)
        result = model.transcribe(audio_path, language=language, fp16=False, verbose=False)
        segments = []
        for seg in result.get('segments', []):
            segments.append({
                'start': float(seg.get('start', 0.0)),
                'end': float(seg.get('end', 0.0)),
                'text': seg.get('text', '').strip()
            })
        return segments

    def transcribe_with_openai(audio_path: str):
        """Transcribe audio using OpenAI API and return a list of segments.

        Strategy:
        - Try verbose_json with segment timestamps (works with whisper-1).
        - If only plain text is returned, split into sentence-like chunks
          and distribute over the full audio duration (approximation).
        """
        api_key = config.get('openai_api_key')
        if not api_key:
            return []
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=config.get('openai_api_base', 'https://api.openai.com/v1'))
        stt_model = str(config.get('openai_stt_model', 'whisper-1'))

        # Helper: audio duration via ffmpeg
        def probe_duration() -> float:
            try:
                ff = shutil.which('ffmpeg') or os.path.join(base_dir, 'tools', 'ffmpeg.exe')
                p = subprocess.run([ff, '-i', audio_path], stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                import re
                m = re.search(rb"Duration: (\d+):(\d+):(\d+\.\d+)", p.stderr)
                if m:
                    h = int(m.group(1)); mi = int(m.group(2)); se = float(m.group(3))
                    return float(h*3600 + mi*60 + se)
            except Exception:
                pass
            return 0.0

        # Helper: fallback segmenter from plain text
        def fallback_segments(full_text: str) -> list:
            full_text = (full_text or '').strip()
            if not full_text:
                return []
            import re
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", full_text) if s.strip()]
            if not sentences:
                sentences = [full_text]
            dur = probe_duration() or 0.0
            n = len(sentences)
            segs = []
            if dur <= 0.0:
                # No duration available: just zero-based increasing indices
                t = 0.0
                for s in sentences:
                    segs.append({'start': t, 'end': t, 'text': s})
                return segs
            step = dur / max(1, n)
            t = 0.0
            for i, s in enumerate(sentences):
                start = t
                end = min(dur, start + step)
                segs.append({'start': float(start), 'end': float(end), 'text': s})
                t = end
            return segs

        try:
            with open(audio_path, 'rb') as f:
                # First attempt: verbose_json with segments (works with whisper-1)
                try:
                    resp = client.audio.transcriptions.create(
                        model=stt_model,
                        file=f,
                        response_format='verbose_json',
                        language=str(config.get('whisper_language', 'ru')),
                        timestamp_granularities=['segment']
                    )
                    segments = []
                    # Try to access resp.segments or dict-like
                    raw_segments = getattr(resp, 'segments', None)
                    if raw_segments is None:
                        # try common fallbacks
                        try:
                            raw_segments = resp.get('segments')  # type: ignore[attr-defined]
                        except Exception:
                            raw_segments = None
                    for seg in (raw_segments or []):
                        # seg may be dict or object with attrs
                        try:
                            start = float(seg.get('start'))
                            end = float(seg.get('end'))
                            text = (seg.get('text') or '').strip()
                        except Exception:
                            start = float(getattr(seg, 'start', 0.0))
                            end = float(getattr(seg, 'end', 0.0))
                            text = (getattr(seg, 'text', '') or '').strip()
                        if text:
                            segments.append({'start': start, 'end': end, 'text': text})
                    if segments:
                        return segments
                    # if no segments in verbose_json, fall back to text below
                    full_text = (getattr(resp, 'text', '') or '').strip()
                    if not full_text:
                        try:
                            full_text = (resp.get('text') or '').strip()  # type: ignore[attr-defined]
                        except Exception:
                            full_text = ''
                except Exception:
                    # Some models may not support verbose_json/timestamps
                    full_text = ''

                if not full_text:
                    # Plain call without verbose_json
                    f.seek(0)
                    resp2 = client.audio.transcriptions.create(model=stt_model, file=f)
                    full_text = (getattr(resp2, 'text', '') or '').strip()
                if not full_text:
                    return []
                return fallback_segments(full_text)
        except Exception:
            return []

    def transcribe_audio(audio_path: str):
        mode = str(config.get('transcription_mode', 'openai')).lower()
        if mode == 'local':
            return transcribe_with_whisper(audio_path)
        return transcribe_with_openai(audio_path)

    # --- OpenAI helpers with fallback between Responses API and Chat Completions ---
    def get_openai_client():
        from openai import OpenAI
        return OpenAI(api_key=config.get('openai_api_key'), base_url=config.get('openai_api_base', 'https://api.openai.com/v1'))

    def call_openai_text(client, model: str, input_text: str) -> str:
        """Try Responses API, fallback to Chat Completions for text-only prompts."""
        last_err = None
        for attempt in range(3):
            try:
                if hasattr(client, 'responses'):
                    resp = client.responses.create(model=model, input=input_text)
                    return getattr(resp, 'output_text', None) or resp.output[0].content[0].text
                # Fallback to chat completions
                chat = client.chat.completions.create(model=model, messages=[{"role": "user", "content": input_text}])
                return (chat.choices[0].message.content or '').strip()
            except Exception as e:
                last_err = e
                msg = str(e)
                if '429' in msg or 'rate' in msg.lower():
                    import time
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
        if last_err:
            raise last_err
        return ''

    @app.route('/api/explain_frame', methods=['POST'])
    def explain_frame():
        data = request.get_json(silent=True) or {}
        name = data.get('name') or ''
        image_data_url = data.get('image') or ''
        current_time = float(data.get('currentTime') or 0)
        api_key = config.get('openai_api_key')
        if not api_key:
            return jsonify({'answer': 'LLM РЅРµ РЅР°СЃС‚СЂРѕРµРЅ'}), 200

        # Save image to frames_dir for logs/preview
        img_rel_path = None
        try:
            header, b64 = image_data_url.split(',', 1)
            img_bytes = base64.b64decode(b64)
            ts = datetime.now().strftime('%Y%m%d-%H%M%S')
            safe_name = os.path.splitext(os.path.basename(name))[0]
            subdir = os.path.join(frames_dir, safe_name)
            os.makedirs(subdir, exist_ok=True)
            img_filename = f"frame-{ts}.png"
            file_path = os.path.join(subdir, img_filename)
            with open(file_path, 'wb') as f:
                f.write(img_bytes)
            img_rel_path = os.path.relpath(file_path, frames_dir).replace('\\', '/')
        except Exception:
            pass

        # Build textual context (summary + subs up to current time)
        summary_text = read_summary(name)
        subs_text = ''
        try:
            subs_json_path = os.path.join(subs_dir, f"{name}.json")
            if os.path.isfile(subs_json_path):
                with open(subs_json_path, 'r', encoding='utf-8') as f:
                    segs = (json.load(f).get('segments') or [])
                parts = []
                for s in segs:
                    if float(s.get('start', 0)) < current_time:
                        parts.append(s.get('text', ''))
                subs_text = (" ".join(parts))
        except Exception:
            subs_text = ''

        # Prompts
        prompts = config.get('prompts', {}) or {}
        system = prompts.get('frame_system') or 'РўС‹ РІС‹СЃС‚СѓРїР°РµС€СЊ РІ СЂРѕР»Рё Р»РµРєС‚РѕСЂР°. Р•СЃР»Рё Рє С‚РµРѕСЂРёРё РїРѕРґС…РѕРґСЏС‚ С„РѕСЂРјСѓР»С‹, РјРѕР¶РµС€СЊ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ LaTeX.'
        tpl = prompts.get('frame_user_template') or (
            'Р›РµРєС†РёСЏ: {lecture}\nРљСЂР°С‚РєРѕРµ СЃРѕРґРµСЂР¶Р°РЅРёРµ: {summary}\n\nРњС‹ РЅР°С…РѕРґРёРјСЃСЏ РІ СЂР°Р·РґРµР»Рµ:\n{context}\n\nРќР° РёР·РѕР±СЂР°Р¶РµРЅРёРё РІС‹РґРµР»РµРЅ РєСЂР°СЃРЅС‹Рј РїРѕР»СѓРїСЂРѕР·СЂР°С‡РЅС‹Рј РєСЂСѓРіРѕРј РёРЅС‚РµСЂРµСЃСѓСЋС‰РёР№ С„СЂР°РіРјРµРЅС‚. Р”Р°Р№ РїРѕСЏСЃРЅРµРЅРёРµ РїРѕ СЌС‚РѕРјСѓ С„СЂР°РіРјРµРЅС‚Сѓ.'
        )
        user_prompt = tpl.format(lecture=name, summary=summary_text, context=subs_text)

        # Call Responses API with multimodal input (text + image data URL)
        client = get_openai_client()
        model = config.get('openai_model', 'gpt-4o-mini')

        # Log request
        now_req = datetime.now().isoformat(timespec='seconds')
        img_url_for_log = None
        if img_rel_path:
            img_url_for_log = url_for('serve_frame', filename=img_rel_path)
        append_log(name, {"type": "frame_request", "time": now_req, "model": model, "content": user_prompt, "image_url": img_url_for_log})

        # Call Responses API if available; otherwise use Chat Completions with image_url
        answer = ''
        last_err = None
        for attempt in range(3):
            try:
                if hasattr(client, 'responses'):
                    resp = client.responses.create(
                        model=model,
                        input=[{
                            'role': 'user',
                            'content': [
                                {'type': 'input_text', 'text': f"{system}\n\n{user_prompt}"},
                                {'type': 'input_image', 'image_url': image_data_url}
                            ]
                        }]
                    )
                    answer = getattr(resp, 'output_text', None) or resp.output[0].content[0].text
                    break
                else:
                    chat = client.chat.completions.create(
                        model=model,
                        messages=[{
                            'role': 'user',
                            'content': [
                                {'type': 'text', 'text': f"{system}\n\n{user_prompt}"},
                                {'type': 'image_url', 'image_url': {'url': image_data_url}}
                            ]
                        }]
                    )
                    answer = (chat.choices[0].message.content or '').strip()
                    break
            except Exception as e:
                last_err = e
                msg = str(e)
                if '429' in msg or 'rate' in msg.lower():
                    import time
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break

        now = datetime.now().isoformat(timespec='seconds')
        if answer:
            append_log(name, {"type": "frame_response", "time": now, "content": answer, "image_url": img_url_for_log})
            return jsonify({'answer': answer, 'image_url': img_url_for_log})
        else:
            err_text = str(last_err) if last_err else 'РќРµРёР·РІРµСЃС‚РЅР°СЏ РѕС€РёР±РєР° LLM'
            append_log(name, {"type": "error", "time": now, "content": err_text})
            return jsonify({'answer': 'РћС€РёР±РєР° РѕР±СЂР°С‰РµРЅРёСЏ Рє LLM'}), 200

    def read_summary(filename: str) -> str:
        path = os.path.join(summary_dir, f"{filename}.txt")
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    @app.route('/summary/<path:filename>')
    def get_summary(filename):
        text = read_summary(filename)
        return jsonify({"text": text})

    @app.route('/suggestions/<path:filename>')
    def get_suggestions(filename):
        path = os.path.join(suggestions_dir, f"{filename}.json")
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get('items'), list):
                    return jsonify({"items": data.get('items')})
            except Exception as e:
                return jsonify({"items": [], "error": str(e)}), 200
        # If suggestions are missing, try to generate on demand from subtitles
        try:
            subs_json_path = os.path.join(subs_dir, f"{filename}.json")
            if os.path.isfile(subs_json_path):
                with open(subs_json_path, 'r', encoding='utf-8') as f:
                    segs = (json.load(f).get('segments') or [])
                timecoded = build_timecoded_transcript(segs)
                items = generate_suggestions_with_llm(timecoded, filename, subs_count=len(segs))
                if isinstance(items, list) and items:
                    os.makedirs(suggestions_dir, exist_ok=True)
                    with open(path, 'w', encoding='utf-8') as out:
                        json.dump({"items": items}, out, ensure_ascii=False)
                    return jsonify({"items": items})
        except Exception as e:
            append_log(filename, {"type": "error", "time": datetime.now().isoformat(timespec='seconds'), "content": f"suggestions_on_demand_error: {str(e)}"})
        return jsonify({"items": []}), 200

    @app.route('/logs/<path:filename>')
    def get_logs(filename):
        log_path = os.path.join(logs_dir, f"{filename}.log")
        entries = []
        if os.path.isfile(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            pass
            except Exception:
                pass
        return jsonify({"entries": entries})

    @app.route('/logs/<path:filename>', methods=['DELETE'])
    def clear_logs(filename):
        log_path = os.path.join(logs_dir, f"{filename}.log")
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
            return jsonify({"status": "cleared"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    def append_log(filename: str, entry: dict):
        log_path = os.path.join(logs_dir, f"{filename}.log")
        entry = dict(entry)
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def summarize_with_llm(text: str, filename: str) -> str:
        api_key = config.get('openai_api_key')
        if not api_key:
            return ""
        try:
            client = get_openai_client()
            model = config.get('openai_model', 'gpt-5-nano')
            prompt_tpl = (config.get('prompts', {}) or {}).get('summary') or (
                "РўС‹ РѕРїС‹С‚РЅС‹Р№ Р»РµРєС‚РѕСЂ. РЎС„РѕСЂРјРёСЂСѓР№ РєСЂР°С‚РєРѕРµ РѕРїРёСЃР°РЅРёРµ Р»РµРєС†РёРё Рё РїРµСЂРµС‡РёСЃР»Рё РѕСЃРЅРѕРІРЅС‹Рµ РІРѕРїСЂРѕСЃС‹, РєРѕС‚РѕСЂС‹Рµ Р±С‹Р»Рё СЂР°Р·РѕР±СЂР°РЅС‹. РћС‚РІРµС‚ РЅР° СЂСѓСЃСЃРєРѕРј СЏР·С‹РєРµ. РўРµРєСЃС‚ Р»РµРєС†РёРё РЅРёР¶Рµ:\n\n{transcript}"
            )
            input_text = prompt_tpl.replace('{transcript}', text)
            # РќРµРєРѕС‚РѕСЂС‹Рµ РјРѕРґРµР»Рё РЅРµ РїРѕРґРґРµСЂР¶РёРІР°СЋС‚ temperature вЂ” РЅРµ РїРµСЂРµРґР°РµРј РµРіРѕ
            # Р”РѕР±Р°РІРёРј РїСЂРѕСЃС‚СѓСЋ СЃС‚СЂР°С‚РµРіРёСЋ РїРѕРІС‚РѕСЂРѕРІ РїСЂРё 429
            return call_openai_text(client, model, input_text)
        except Exception:
            return ""

    def build_timecoded_transcript(segments: list) -> str:
        """Build a transcript with [HH:mm:ss] time marks from Whisper segments."""
        def hhmmss(sec: float) -> str:
            s = int(sec)
            h = s // 3600
            m = (s % 3600) // 60
            ss = s % 60
            return f"{h:02d}:{m:02d}:{ss:02d}"
        lines = []
        for seg in segments or []:
            start = float(seg.get('start', 0))
            text = (seg.get('text') or '').strip()
            if text:
                lines.append(f"[{hhmmss(start)}] {text}")
        return "\n".join(lines)

    def generate_suggestions_with_llm(timecoded_transcript: str, filename: str, subs_count: int = 0):
        """Ask LLM to produce short time-ranged questions; returns list of items."""
        api_key = config.get('openai_api_key')
        if not api_key:
            return []
        try:
            prompts = config.get('prompts', {}) or {}
            tpl = prompts.get('suggestions') or (
                "РўС‹ РїРѕРјРѕС‰РЅРёРє СЃС‚СѓРґРµРЅС‚Р°, РєРѕС‚РѕСЂС‹Р№ СЃРјРѕС‚СЂРёС‚ РІРёРґРµРѕ-Р»РµРєС†РёСЋ. РўРµР±Рµ РґР°РЅ РїРѕР»РЅС‹Р№ С‚СЂР°РЅСЃРєСЂРёРїС‚"
                " СЃ РїРѕРјРµС‚РєР°РјРё РІСЂРµРјРµРЅРё РЅР°С‡Р°Р»Р° СЂРµРїР»РёРє РІ С„РѕСЂРјР°С‚Рµ [HH:mm:ss]. РќР° РѕСЃРЅРѕРІРµ СЌС‚РѕРіРѕ С‚РµРєСЃС‚Р°"
                " СЃРѕСЃС‚Р°РІСЊ РњРќРћР“Рћ РєРѕСЂРѕС‚РєРёС…, РєРѕРЅРєСЂРµС‚РЅС‹С… Рё СѓРјРµСЃС‚РЅС‹С… РІРѕРїСЂРѕСЃРѕРІ, РєРѕС‚РѕСЂС‹Рµ СЃС‚СѓРґРµРЅС‚ РјРѕР¶РµС‚"
                " Р·Р°РґР°С‚СЊ РїСЂРµРїРѕРґР°РІР°С‚РµР»СЋ, РєРѕРіРґР° СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ РѕР±СЃСѓР¶РґР°РµРјРѕР№ С‚РµРјРµ.\n\n"
                "РџСЂР°РІРёР»Р° СЃРѕСЃС‚Р°РІР»РµРЅРёСЏ РІРѕРїСЂРѕСЃРѕРІ:\n"
                "- РљР°Р¶РґС‹Р№ РІРѕРїСЂРѕСЃ РјР°РєСЃРёРјР°Р»СЊРЅРѕ РєРѕСЂРѕС‚РєРёР№ (Р¶РµР»Р°С‚РµР»СЊРЅРѕ РґРѕ 8-12 СЃР»РѕРІ).\n"
                "- Р’РѕРїСЂРѕСЃС‹ С„РѕСЂРјСѓР»РёСЂСѓР№ С‚Р°Рє, С‡С‚РѕР±С‹ РѕРЅРё РїРµСЂРµРєСЂС‹РІР°Р»Рё РІСЃСЋ РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ РІРёРґРµРѕ.\n"
                "- РЈ РєР°Р¶РґРѕРіРѕ РІРѕРїСЂРѕСЃР° РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РёРЅС‚РµСЂРІР°Р» Р°РєС‚СѓР°Р»СЊРЅРѕСЃС‚Рё (start/end РІ HH:mm:ss),"
                "  РІ С‚РµС‡РµРЅРёРµ РєРѕС‚РѕСЂРѕРіРѕ СЌС‚РѕС‚ РІРѕРїСЂРѕСЃ СѓРјРµСЃС‚РµРЅ. РРЅС‚РµСЂРІР°Р»С‹ Р”РћР›Р–РќР« РїРµСЂРµРєСЂС‹РІР°С‚СЊСЃСЏ,"
                "  С‡С‚РѕР±С‹ РІ Р»СЋР±РѕР№ РјРѕРјРµРЅС‚ РІСЂРµРјРµРЅРё Р±С‹Р»Рѕ РЅРµСЃРєРѕР»СЊРєРѕ СЂРµР»РµРІР°РЅС‚РЅС‹С… РІРѕРїСЂРѕСЃРѕРІ.\n"
                "- РџСЂРёРІСЏР·С‹РІР°Р№ РІРѕРїСЂРѕСЃС‹ Рє СЃРѕРґРµСЂР¶Р°РЅРёСЋ Р»РµРєС†РёРё: С‚РµСЂРјРёРЅР°Рј, РѕРїСЂРµРґРµР»РµРЅРёСЏРј, С€Р°РіР°Рј, РїСЂРёРјРµСЂР°Рј.\n"
                "- Р’РµСЂРЅРё РўРћР›Р¬РљРћ JSON-РјР°СЃСЃРёРІ РѕР±СЉРµРєС‚РѕРІ РІРёРґР°:\n"
                "  [{\"text\":\"...\",\"start\":\"HH:mm:ss\",\"end\":\"HH:mm:ss\"}, ...]\n"
                "- Р‘РµР· РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕРіРѕ С‚РµРєСЃС‚Р°, Р±РµР· РєРѕРјРјРµРЅС‚Р°СЂРёРµРІ Рё РїРѕСЏСЃРЅРµРЅРёР№. РўРѕР»СЊРєРѕ JSON.\n\n"
                "РўСЂР°РЅСЃРєСЂРёРїС‚ СЃ С‚Р°Р№Рј-РєРѕРґР°РјРё:\n{timecoded_transcript}"
            )
            # Avoid .format on JSON braces; replace known tokens manually
            def hhmmss_from_sec(sec: int) -> str:
                try:
                    sec = int(sec)
                except Exception:
                    sec = 60
                if sec < 0:
                    sec = 0
                h = sec // 3600
                m = (sec % 3600) // 60
                s = sec % 60
                return f"{h:02d}:{m:02d}:{s:02d}"

            min_dur_sec = int((config.get('suggestions_min_duration_sec') or 60))
            min_words = int((config.get('suggestions_min_words') or 3))
            max_words = int((config.get('suggestions_max_words') or 6))
            div = int((config.get('suggestions_min_count_divider') or 20))
            extra = int((config.get('suggestions_min_count_extra') or 10))
            try:
                min_count = int((subs_count or 0) // max(1, div)) + extra
            except Exception:
                min_count = extra

            user_prompt = (tpl
                .replace('{timecoded_transcript}', timecoded_transcript)
                .replace('{min_duration}', hhmmss_from_sec(min_dur_sec))
                .replace('{min_count}', str(min_count))
                .replace('{min_words}', str(min_words))
                .replace('{max_words}', str(max_words))
            )

            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=config.get('openai_api_base', 'https://api.openai.com/v1'))
            model = config.get('openai_model', 'gpt-5-nano')

            now_req = datetime.now().isoformat(timespec='seconds')
            append_log(filename, {"type": "suggestions_request", "time": now_req, "model": model, "content": user_prompt})

            last_err = None
            answer = ''
            for attempt in range(3):
                try:
                    resp = client.responses.create(model=model, input=user_prompt)
                    answer = getattr(resp, 'output_text', None) or resp.output[0].content[0].text
                    break
                except Exception as e:
                    last_err = e
                    msg = str(e)
                    if '429' in msg or 'rate' in msg.lower():
                        import time
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    break
            now = datetime.now().isoformat(timespec='seconds')
            if not answer:
                append_log(filename, {"type": "error", "time": now, "content": str(last_err) if last_err else 'empty_suggestions'})
                return []
            append_log(filename, {"type": "suggestions_response", "time": now, "content": answer})

            parsed = None
            try:
                parsed = json.loads(answer)
            except Exception:
                try:
                    cleaned = answer.strip()
                    if cleaned.startswith('```'):
                        cleaned = "\n".join([line for line in cleaned.splitlines() if not line.strip().startswith('```')])
                    parsed = json.loads(cleaned)
                except Exception:
                    try:
                        import re
                        m = re.search(r"\[[\s\S]*\]", answer)
                        if m:
                            parsed = json.loads(m.group(0))
                    except Exception:
                        parsed = None
            items = []
            if isinstance(parsed, list):
                for it in parsed:
                    text = (it or {}).get('text')
                    start = (it or {}).get('start')
                    end = (it or {}).get('end')
                    if text and start and end:
                        items.append({"text": str(text), "start": str(start), "end": str(end)})
            return items
        except Exception as e:
            append_log(filename, {"type": "error", "time": datetime.now().isoformat(timespec='seconds'), "content": f"suggestions_exception: {str(e)}"})
            return []

    @app.route('/api/chat', methods=['POST'])
    def api_chat():
        data = request.get_json(silent=True) or {}
        name = data.get('name') or ''
        current_time = float(data.get('currentTime') or 0)
        dialog = data.get('dialog') or []
        question = data.get('question') or ''
        api_key = config.get('openai_api_key')
        if not api_key:
            return jsonify({"answer": "LLM РЅРµ РЅР°СЃС‚СЂРѕРµРЅ"}), 200

        # Prepare context
        subs_json_path = os.path.join(subs_dir, f"{name}.json")
        subs_text = ""
        if os.path.isfile(subs_json_path):
            try:
                with open(subs_json_path, 'r', encoding='utf-8') as f:
                    segs = (json.load(f).get('segments') or [])
                # get text up to current_time (no timestamps)
                parts = []
                for s in segs:
                    if float(s.get('start', 0)) < current_time:
                        parts.append(s.get('text', ''))
                subs_text = (" ".join(parts))[-3000:]
            except Exception:
                subs_text = ""

        summary_text = read_summary(name)

        # Exclude the last student message (it's passed separately as question)
        dialog_items = list(dialog or [])
        if dialog_items and (dialog_items[-1].get('role') == 'student') and (dialog_items[-1].get('text', '').strip() == question.strip()):
            dialog_items = dialog_items[:-1]

        # Remove messages related to frame explanations from history
        dialog_items = [m for m in dialog_items if (m or {}).get('kind') != 'frame']

        # Build conversation log for prompt
        prev = []
        for m in dialog_items:
            role = m.get('role')
            txt = (m.get('text') or '').strip()
            if not txt:
                continue
            label = 'РЎС‚СѓРґРµРЅС‚' if role == 'student' else ('Р›РµРєС‚РѕСЂ' if role == 'lecturer' else 'РЎРёСЃС‚РµРјР°')
            label = 'РЎС‚СѓРґРµРЅС‚' if role == 'student' else ('Р›РµРєС‚РѕСЂ' if role == 'lecturer' else 'РЎРёСЃС‚РµРјР°')
            prev.append(f"{label}: {txt}")
        prev_text = "\n".join(prev)
        if len(prev_text) > 8000:
            prev_text = prev_text[-8000:]

        # Compose user prompt
        tpl = (config.get('prompts', {}) or {}).get('chat_user_template') or (
            "Р›РµРєС†РёСЏ: {lecture}\nРљСЂР°С‚РєРѕРµ СЃРѕРґРµСЂР¶Р°РЅРёРµ: {summary}\n\nРњС‹ РЅР°С…РѕРґРёРјСЃСЏ РІ СЂР°Р·РґРµР»Рµ:\n{context}\n\nРџСЂРµРґС‹РґСѓС‰РёР№ РґРёР°Р»РѕРі:\n{history}\n\nРЈ СЃС‚СѓРґРµРЅС‚Р° РІРѕР·РЅРёРє РЅРѕРІС‹Р№ РІРѕРїСЂРѕСЃ: {question}"
        )
        user_prompt = tpl.format(lecture=name, summary=summary_text, context=subs_text, history=prev_text, question=question)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=config.get('openai_api_base', 'https://api.openai.com/v1'))
            model = config.get('openai_model', 'gpt-5-nano')
            system = (config.get('prompts', {}) or {}).get('chat_system') or "РўС‹ РІС‹СЃС‚СѓРїР°РµС€СЊ РІ СЂРѕР»Рё Р»РµРєС‚РѕСЂР°, РѕС‚РІРµС‡Р°Р№ С‡РµС‚РєРѕ Рё РїРѕ РґРµР»Сѓ."
            prompt = f"{system}\n\n{user_prompt}"
            # Р‘РµР· temperature (РјРѕРіСѓС‚ Р±С‹С‚СЊ РјРѕРґРµР»Рё, РЅРµ РїРѕРґРґРµСЂР¶РёРІР°СЋС‰РёРµ РїР°СЂР°РјРµС‚СЂ)
            last_err = None
            answer = ""
            # Log request payload fully
            now_req = datetime.now().isoformat(timespec='seconds')
            append_log(name, {"type": "chat_request", "time": now_req, "model": model, "content": prompt})
            answer = call_openai_text(client, model, prompt)
            now = datetime.now().isoformat(timespec='seconds')
            if answer:
                append_log(name, {"type": "chat_response", "time": now, "content": answer})
                return jsonify({"answer": answer})
                err_text = "Не удалось получить ответ"
                append_log(name, {"type": "error", "time": now, "content": err_text})
                return jsonify({"answer": "Ошибка обращения к LLM"}), 200
                return jsonify({"answer": "РћС€РёР±РєР° РѕР±СЂР°С‰РµРЅРёСЏ Рє LLM"}), 200
        except Exception as e:
            now = datetime.now().isoformat(timespec='seconds')
            append_log(name, {"type": "error", "time": now, "content": str(e)})
            return jsonify({"answer": "РћС€РёР±РєР° РѕР±СЂР°С‰РµРЅРёСЏ Рє LLM"}), 200

    # Single video route: open specific existing video directly
    @app.route('/<path:filename>')
    def open_single(filename):
        # Skip reserved paths
        reserved = (
            'video/', 'subtitles/', 'frames/', 'summary/', 'suggestions/',
            'logs/', 'api/', 'static/', 'favicon.ico'
        )
        for pref in reserved:
            if filename.startswith(pref):
                return redirect(url_for('index'))
        safe_name = os.path.basename(filename)
        if not allowed_file(safe_name):
            return redirect(url_for('index'))
        candidate = os.path.join(video_dir, safe_name)
        if not os.path.isfile(candidate):
            return redirect(url_for('index'))
        return render_template('index.html', subtitles_panel_enabled=bool(config.get('subtitles_panel_enabled', True)), single_name=safe_name)

    return app


if __name__ == '__main__':
    application = create_app()
    # The host and port can be customised via environment variables; fall back to
    # defaults if not provided.
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    application.run(host=host, port=port, debug=True)
