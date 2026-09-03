#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MES字幕助手 - Flask Web 服务

本机运行的字幕处理服务，同事通过浏览器上传字幕文件，AI自动翻译。
"""

import logging
import os
import threading
import uuid
from datetime import datetime

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
)

import config as cfg
from core import (
    SRTEntry,
    build_srt,
    load_glossary,
    parse_srt,
    preprocess_srt,
    translate_srt_entries,
    polish_srt_entries,
    AIClient,
    create_error_handler,
    reflow_english_subtitles,
    GlossaryManager,
)

# 全局 AI 客户端实例
ai_client = AIClient(
    api_key=cfg.DEEPSEEK_API_KEY,
    api_base=cfg.DEEPSEEK_API_BASE,
    model=cfg.DEEPSEEK_MODEL,
    default_timeout=120,
    max_retries=3,
    default_temperature=0.3
)

app = Flask(__name__)
app.secret_key = cfg.SECRET_KEY
app.config['TEMPLATES_AUTO_RELOAD'] = True

@app.after_request
def add_no_cache_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(cfg.LOG_FOLDER, "app.log"), encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
error_handler = create_error_handler(logger)

sessions = {}
ENGLISH_REFLOW_LOCK = threading.Lock()
GLOSSARY_LOCK = threading.Lock()


def _default_glossary_path():
    return os.path.join(cfg.GLOSSARY_FOLDER, cfg.DEFAULT_GLOSSARY_FILENAME)


def _glossary_manager():
    return GlossaryManager(_default_glossary_path())


def _get_user_id():
    user_id = request.cookies.get("mes_user_id")
    if not user_id:
        user_id = uuid.uuid4().hex[:10]
    return user_id


@app.route("/")
def index():
    return render_template(
        "index.html",
        target_languages=cfg.TARGET_LANGUAGES,
        default_target_language=cfg.DEFAULT_TARGET_LANGUAGE,
    )


@app.route("/glossary")
def glossary_page():
    return render_template("glossary.html")


@app.route("/api/glossary")
def api_glossary():
    with GLOSSARY_LOCK:
        return jsonify({"success": True, **_glossary_manager().list_terms()})


@app.route("/api/glossary", methods=["POST"])
def api_save_glossary_term():
    data = request.get_json(silent=True) or {}
    try:
        with GLOSSARY_LOCK:
            term = _glossary_manager().save_term(data)
        logger.info("MES术语库已更新: %s -> %s", term["term"], term["translation"])
        return jsonify({"success": True, "term": term})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        logger.exception("保存MES术语库失败")
        return jsonify({"success": False, "message": f"保存术语失败: {error}"}), 500


@app.route("/api/glossary/delete", methods=["POST"])
def api_delete_glossary_term():
    data = request.get_json(silent=True) or {}
    try:
        with GLOSSARY_LOCK:
            _glossary_manager().delete_term(str(data.get("id", "")))
        logger.info("MES术语库已删除: %s", data.get("id", ""))
        return jsonify({"success": True})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 404
    except Exception as error:
        logger.exception("删除MES术语失败")
        return jsonify({"success": False, "message": f"删除术语失败: {error}"}), 500


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"success": False, "message": "未选择文件"}), 400

    file = request.files["file"]
    if not file.filename.endswith(".srt"):
        return jsonify({"success": False, "message": "仅支持 .srt 格式文件"}), 400

    target_language = request.form.get(
        "target_language", cfg.DEFAULT_TARGET_LANGUAGE
    )
    language_config = cfg.TARGET_LANGUAGES.get(target_language)
    if language_config is None:
        return jsonify({"success": False, "message": "不支持的目标语言"}), 400

    session_id = uuid.uuid4().hex[:12]
    upload_dir = os.path.join(cfg.UPLOAD_FOLDER, session_id)
    os.makedirs(upload_dir, exist_ok=True)

    srt_path = os.path.join(upload_dir, "input.srt")
    file.save(srt_path)

    try:
        entries = parse_srt(srt_path)
    except Exception as e:
        error_response, status_code = error_handler.handle_api_error(
            error=e,
            context={"endpoint": "/api/upload", "file": file.filename},
        )
        return jsonify(error_response), status_code

    if not entries:
        return jsonify({"success": False, "message": "SRT文件中没有有效的字幕条目"}), 400

    entries, corrections = preprocess_srt(entries)

    user_id = _get_user_id()
    client_ip = request.remote_addr

    sessions[session_id] = {
        "id": session_id,
        "filename": file.filename,
        "target_language": target_language,
        "target_language_label": language_config["label"],
        "srt_path": srt_path,
        "entries": entries,
        "corrections": corrections,
        "status": "uploaded",
        "user_edited": False,
        "english_reflow": True,
        "progress": {"step": "", "percent": 0, "message": "", "logs": []},
        "output_files": [],
        "api_calls": [],
        "user_id": user_id,
        "client_ip": client_ip,
        "created_at": datetime.now().isoformat(),
    }

    logger.info(
        f"[{session_id}] 上传成功: {file.filename}, {len(entries)} 条字幕, "
        f"{len(corrections)} 处基础清理, 用户: {user_id} ({client_ip})"
    )

    thread = threading.Thread(target=_polish_worker, args=(session_id,))
    thread.daemon = True
    thread.start()
    resp = jsonify(
        {"success": True, "session_id": session_id, "redirect": f"/processing/{session_id}"}
    )
    resp.set_cookie("mes_user_id", user_id, max_age=365 * 24 * 3600)
    return resp


@app.route("/edit/<session_id>")
def edit_page(session_id):
    if session_id not in sessions:
        abort(404)

    session = sessions[session_id]
    entries_data = []
    for e in session["entries"]:
        entries_data.append(
            {
                "index": e.index,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "text": e.text,
            }
        )

    return render_template(
        "edit.html",
        session_id=session_id,
        filename=session["filename"],
        entries=entries_data,
        corrections=session["corrections"],
        target_language_label=session.get("target_language_label", "英文"),
    )


@app.route("/api/save-edit", methods=["POST"])
def api_save_edit():
    data = request.get_json()
    session_id = data.get("session_id")
    edited_entries = data.get("entries", [])

    if session_id not in sessions:
        return jsonify({"success": False, "message": "会话不存在"}), 404

    session = sessions[session_id]
    updated = []
    for item in edited_entries:
        updated.append(
            SRTEntry(
                index=item["index"],
                start_time=item["start_time"],
                end_time=item["end_time"],
                text=item["text"],
            )
        )

    session["entries"] = updated
    session["status"] = "edited"
    session["user_edited"] = True

    srt_path = os.path.join(cfg.UPLOAD_FOLDER, session_id, "edited.srt")
    os.makedirs(os.path.dirname(srt_path), exist_ok=True)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(build_srt(updated))
    session["srt_path"] = srt_path

    logger.info(f"[{session_id}] 校对保存: {len(updated)} 条字幕")

    return jsonify({
        "success": True,
        "redirect": f"/processing/{session_id}",
    })


@app.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json() or {}
    session_id = data.get("session_id")

    if session_id not in sessions:
        return jsonify({"success": False, "message": "会话不存在"}), 404

    session = sessions[session_id]
    if session["status"] == "processing":
        return jsonify({"success": False, "message": "正在处理中，请勿重复提交"}), 400

    thread = threading.Thread(target=_process_worker, args=(session_id,))
    thread.daemon = True
    thread.start()

    return jsonify({"success": True, "redirect": f"/processing/{session_id}"})


def _polish_worker(session_id):
    session = sessions[session_id]
    session["status"] = "processing"
    progress = session["progress"]

    try:
        progress["step"] = "polish"
        progress["percent"] = 10
        progress["message"] = "正在优化中文字幕..."
        progress["logs"].append(
            f"{datetime.now().strftime('%H:%M:%S')} 开始AI中文字幕优化..."
        )

        cn_entries = session["entries"]

        if not cfg.DEEPSEEK_API_KEY:
            raise RuntimeError("未配置 DeepSeek API Key，无法进行中文字幕优化")

        glossary_text = load_glossary(_default_glossary_path())
        session["api_calls"].append({
            "step": "polish",
            "action": "AI中文字幕优化",
            "model": cfg.DEEPSEEK_MODEL,
            "time": datetime.now().strftime('%H:%M:%S'),
        })
        cn_entries = polish_srt_entries(
            entries=cn_entries,
            api_key=cfg.DEEPSEEK_API_KEY,
            api_base=cfg.DEEPSEEK_API_BASE,
            model=cfg.DEEPSEEK_MODEL,
            glossary_text=glossary_text,
            batch_size=cfg.BATCH_SIZE,
            temperature=cfg.TRANSLATION_TEMPERATURE,
        )
        progress["logs"].append(
            f"{datetime.now().strftime('%H:%M:%S')} [API] 中文字幕优化完成 -> {len(cn_entries)} 条"
        )

        session["entries"] = cn_entries
        progress["percent"] = 100
        progress["message"] = "中文字幕优化完成，请校对"
        progress["logs"].append(
            f"{datetime.now().strftime('%H:%M:%S')} 中文字幕优化完成，请校对字幕"
        )

        session["status"] = "optimized"
        logger.info(f"[{session_id}] 中文字幕优化完成: {len(cn_entries)} 条字幕")

    except Exception as e:
        error_handler.handle_worker_error(
            session_id=session_id,
            session=session,
            step_name="中文字幕优化",
            error=e,
        )


def _process_worker(session_id):
    session = sessions[session_id]
    session["status"] = "processing"
    progress = session["progress"]
    progress["step"] = "translate"
    progress["percent"] = 0
    progress["message"] = "正在准备目标语言翻译..."
    progress["logs"] = []
    output_dir = os.path.join(cfg.OUTPUT_FOLDER, session_id)
    os.makedirs(output_dir, exist_ok=True)

    try:
        cn_entries = session["entries"]
        original_base = os.path.splitext(session["filename"])[0]
        target_language = session.get(
            "target_language", cfg.DEFAULT_TARGET_LANGUAGE
        )
        language_config = cfg.TARGET_LANGUAGES[target_language]
        target_language_label = language_config["label"]
        target_language_name = language_config["prompt_name"]
        language_instruction = language_config["instruction"]

        progress["logs"].append(
            f"{datetime.now().strftime('%H:%M:%S')} 开始{target_language_label}翻译，"
            f"共 {len(cn_entries)} 条中文字幕"
        )
        if cn_entries:
            progress["logs"].append(
                f"{datetime.now().strftime('%H:%M:%S')} 首条内容: {cn_entries[0].text[:30]}..."
            )

        logger.info(
            f"[{session_id}] 翻译开始: {len(cn_entries)} 条, "
            f"首条: {cn_entries[0].text[:30] if cn_entries else 'N/A'}"
        )

        cn_path = os.path.join(output_dir, f"中文_{original_base}.srt")
        with open(cn_path, "w", encoding="utf-8") as f:
            f.write(build_srt(cn_entries))

        progress["step"] = "translate"
        progress["message"] = f"正在翻译为{target_language_label}..."

        if cfg.DEEPSEEK_API_KEY:
            session["api_calls"].append({
                "step": "translate",
                "action": f"AI{target_language_label}翻译",
                "model": cfg.DEEPSEEK_MODEL,
                "time": datetime.now().strftime('%H:%M:%S'),
            })
            progress["logs"].append(
                f"{datetime.now().strftime('%H:%M:%S')} [API] 调用DeepSeek翻译..."
            )
        else:
            progress["logs"].append(
                f"{datetime.now().strftime('%H:%M:%S')} [错误] 无API Key，无法翻译"
            )
            raise Exception("未配置DeepSeek API Key，无法进行翻译")

        glossary_text = load_glossary(_default_glossary_path())

        en_entries = translate_srt_entries(
            entries=cn_entries,
            ai_client=ai_client,
            glossary_text=glossary_text,
            batch_size=cfg.BATCH_SIZE,
            temperature=cfg.TRANSLATION_TEMPERATURE,
            target_language=target_language_name,
            language_instruction=language_instruction,
        )

        for i, en_entry in enumerate(en_entries):
            if i < len(cn_entries):
                en_entry.start_time = cn_entries[i].start_time
                en_entry.end_time = cn_entries[i].end_time
                en_entry.index = cn_entries[i].index

        progress["percent"] = 75
        progress["message"] = (
            f"翻译完成，正在优化{target_language_label}字幕可读性..."
        )
        progress["logs"].append(
            f"{datetime.now().strftime('%H:%M:%S')} [API] {target_language_label}翻译完成"
            f" -> {len(en_entries)} 条"
        )

        optimized_en_entries = en_entries
        if cfg.ENABLE_ENGLISH_REFLOW:
            progress["step"] = "english_reflow"
            session["api_calls"].append({
                "step": "english_reflow",
                "action": f"AI{target_language_label}字幕可读性优化",
                "model": cfg.DEEPSEEK_MODEL,
                "time": datetime.now().strftime('%H:%M:%S'),
            })
            progress["logs"].append(
                f"{datetime.now().strftime('%H:%M:%S')} [API] 根据字幕约束重排"
                f"{target_language_label}字幕碎片..."
            )
            try:
                def update_reflow_progress(batch_number, total_batches, detail):
                    progress["percent"] = 75 + int((batch_number - 1) / total_batches * 15)
                    progress["message"] = (
                        f"{target_language_label}可读性优化：第 {batch_number}/"
                        f"{total_batches} 批，{detail}"
                    )
                    progress["logs"].append(
                        f"{datetime.now().strftime('%H:%M:%S')} {target_language_label}"
                        "可读性优化："
                        f"第 {batch_number}/{total_batches} 批，{detail}"
                    )

                progress["message"] = f"{target_language_label}可读性优化排队中..."
                with ENGLISH_REFLOW_LOCK:
                    progress["logs"].append(
                        f"{datetime.now().strftime('%H:%M:%S')} 获得"
                        f"{target_language_label}可读性优化处理队列"
                    )
                    optimized_en_entries, mappings, reflow_report = reflow_english_subtitles(
                        cn_entries=cn_entries,
                        en_entries=en_entries,
                        ai_client=ai_client,
                        glossary_text=glossary_text,
                        batch_size=cfg.ENGLISH_REFLOW_BATCH_SIZE,
                        max_chars_per_line=language_config["max_chars_per_line"],
                        warning_wps=language_config["warning_reading_speed"],
                        hard_wps=language_config["hard_reading_speed"],
                        min_duration_ms=cfg.ENGLISH_MIN_DURATION_MS,
                        timeout=cfg.ENGLISH_REFLOW_TIMEOUT,
                        max_retries=cfg.ENGLISH_REFLOW_MAX_RETRIES,
                        revise_batches=cfg.ENGLISH_REFLOW_REVISE_BATCHES,
                        progress_callback=update_reflow_progress,
                        language=target_language_name,
                        language_code=target_language,
                        language_instruction=language_instruction,
                    )
                progress["logs"].append(
                    f"{datetime.now().strftime('%H:%M:%S')} {target_language_label}"
                    "可读性优化完成 -> "
                    f"{len(optimized_en_entries)} 条，合并 {reflow_report['merged_entries']} 条"
                )
            except Exception as e:
                logger.warning(
                    f"[{session_id}] {target_language_label}字幕可读性优化失败，"
                    f"保留逐条翻译: {e}"
                )
                progress["logs"].append(
                    f"{datetime.now().strftime('%H:%M:%S')} [警告] {target_language_label}"
                    "重排失败，保留原翻译结果"
                )

        target_prefix = language_config["file_prefix"]
        aligned_target_path = os.path.join(
            output_dir, f"{target_prefix}_{original_base}.srt"
        )
        with open(aligned_target_path, "w", encoding="utf-8") as f:
            f.write(build_srt(en_entries))

        readable_target_path = os.path.join(
            output_dir, f"{target_prefix}_可读优化版_{original_base}.srt"
        )
        with open(readable_target_path, "w", encoding="utf-8") as f:
            f.write(build_srt(optimized_en_entries))
        with open(cn_path, "w", encoding="utf-8") as f:
            f.write(build_srt(cn_entries))

        session["output_files"] = [
            {"name": f"中文_{original_base}.srt", "label": "中文字幕", "path": cn_path},
            {
                "name": f"{target_prefix}_{original_base}.srt",
                "label": f"{target_language_label}字幕（逐条对齐版）",
                "path": aligned_target_path,
            },
            {
                "name": f"{target_prefix}_可读优化版_{original_base}.srt",
                "label": f"{target_language_label}字幕（可读优化版）",
                "path": readable_target_path,
            },
        ]
        progress["step"] = "done"
        progress["percent"] = 100
        progress["message"] = "处理完成！"
        progress["logs"].append(
            f"{datetime.now().strftime('%H:%M:%S')} 全部处理完成！"
        )

        session["status"] = "completed"
        logger.info(
            f"[{session_id}] 处理完成: cn={len(cn_entries)}, "
            f"target={target_language}, entries={len(en_entries)}"
        )

    except Exception as e:
        error_handler.handle_worker_error(
            session_id=session_id,
            session=session,
            step_name="字幕处理",
            error=e,
        )


@app.route("/processing/<session_id>")
def processing_page(session_id):
    if session_id not in sessions:
        abort(404)
    return render_template(
        "processing.html",
        session_id=session_id,
        filename=sessions[session_id]["filename"],
        target_language_label=sessions[session_id].get(
            "target_language_label", "英文"
        ),
    )


@app.route("/api/progress/<session_id>")
def api_progress(session_id):
    if session_id not in sessions:
        return jsonify({"success": False, "message": "会话不存在"}), 404

    session = sessions[session_id]
    progress = session["progress"]

    return jsonify(
        {
            "success": True,
            "status": session["status"],
            "step": progress["step"],
            "progress": progress["percent"],
            "message": progress["message"],
            "logs": progress["logs"][-20:],
            "api_calls": session.get("api_calls", []),
        }
    )


@app.route("/download/<session_id>")
def download_page(session_id):
    if session_id not in sessions:
        abort(404)

    session = sessions[session_id]
    if session["status"] != "completed":
        return redirect(f"/processing/{session_id}")

    subtitle_files = session["output_files"]

    return render_template(
        "download.html",
        session_id=session_id,
        filename=session["filename"],
        subtitle_files=subtitle_files,
        target_language_label=session.get("target_language_label", "英文"),
        target_language_rtl=cfg.TARGET_LANGUAGES.get(
            session.get("target_language", cfg.DEFAULT_TARGET_LANGUAGE), {}
        ).get("rtl", False),
    )


@app.route("/api/download/<session_id>/<filename>")
def api_download(session_id, filename):
    client_ip = request.remote_addr
    user_id = _get_user_id()

    if session_id in sessions:
        session = sessions[session_id]
        for f in session.get("output_files", []):
            if f["name"] == filename:
                logger.info(
                    f"[下载] IP={client_ip} user={user_id} "
                    f"session={session_id} file={filename}"
                )
                directory = os.path.dirname(f["path"])
                return send_from_directory(directory, f["name"], as_attachment=True)

    output_subdir = os.path.join(cfg.OUTPUT_FOLDER, session_id)
    if os.path.exists(output_subdir):
        fp = os.path.join(output_subdir, filename)
        if os.path.exists(fp):
            logger.info(
                f"[下载] IP={client_ip} user={user_id} "
                f"session={session_id} file={filename} (from_disk)"
            )
            return send_from_directory(output_subdir, filename, as_attachment=True)

    logger.warning(
        f"[下载失败] IP={client_ip} user={user_id} "
        f"session={session_id} file={filename} NOT_FOUND"
    )
    abort(404)


@app.errorhandler(404)
def page_not_found(e):
    return render_template(
        "index.html",
        target_languages=cfg.TARGET_LANGUAGES,
        default_target_language=cfg.DEFAULT_TARGET_LANGUAGE,
    ), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"success": False, "message": "服务器内部错误"}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("  MES字幕助手 - Web 服务")
    print("=" * 50)
    print(f"  API: {cfg.DEEPSEEK_API_BASE}")
    print(f"  Model: {cfg.DEEPSEEK_MODEL}")
    print(f"  API Key: {'已配置' if cfg.DEEPSEEK_API_KEY else '未配置'}")
    print()
    print(f"  本机访问: http://localhost:{cfg.SERVER_PORT}")
    print("=" * 50)

    app.run(
        host=cfg.SERVER_HOST,
        port=cfg.SERVER_PORT,
        debug=False,
    )
