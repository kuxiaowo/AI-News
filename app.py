from flask import Flask, jsonify, send_from_directory, request
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from tool.config import get_config
from backend.logger_setup import get_logger
from backend.news_provider_tianapi import NewsProvider
from backend.deepseek_client import DeepseekClient


app = Flask(__name__, static_folder=None)
logger = get_logger("app")
cfg = get_config("./config.json")
app_cfg = cfg.get("app", {})
news_provider = NewsProvider(ttl_minutes=10)

_SCHED_STARTED = False


def _next_run_after(now: datetime) -> datetime:
    hours = [8, 14, 18]
    for h in hours:
        t = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if t > now:
            return t
    # next day's 08:00
    t = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    return t


def _schedule_thread_loop():
    try:
        cnt = int(app_cfg.get("curated_count", 30))
    except Exception:
        cnt = 30
    logger.info("scheduler start: initial refresh with count=%d", cnt)
    try:
        news_provider.refresh(count=cnt)
        logger.info("scheduler initial refresh done")
    except Exception:
        logger.exception("scheduler initial refresh failed")
    while True:
        try:
            now = datetime.now()
            nxt = _next_run_after(now)
            wait = max(1, int((nxt - now).total_seconds()))
            logger.info("scheduler sleeping until %s (%ds)", nxt.strftime("%Y-%m-%d %H:%M:%S"), wait)
            time.sleep(wait)
            logger.info("scheduler tick at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            news_provider.refresh(count=cnt)
            logger.info("scheduler refresh done")
        except Exception:
            logger.exception("scheduler loop error")


def _ensure_scheduler():
    global _SCHED_STARTED
    if not _SCHED_STARTED:
        th = threading.Thread(target=_schedule_thread_loop, daemon=True)
        th.start()
        _SCHED_STARTED = True
        logger.info("scheduler thread started")


# start scheduler on import
_ensure_scheduler()

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/news")
def api_news():
    try:
        cnt = int(request.args.get("count", app_cfg.get("curated_count", 5)))
    except Exception:
        cnt = int(app_cfg.get("curated_count", 5))
    keyword = request.args.get("word")
    items = news_provider.get_today_news(count=cnt, keyword=keyword)
    return jsonify({"items": items})


@app.get("/api/summary")
def api_summary():
    try:
        cnt = int(request.args.get("count", app_cfg.get("curated_count", 5)))
    except Exception:
        cnt = int(app_cfg.get("curated_count", 5))
    keyword = request.args.get("word")
    items = news_provider.get_today_news(count=cnt, keyword=keyword)
    if not items:
        return jsonify({"summary": "今日暂无新闻数据", "items": []})

    # 组织给 DeepSeek 的消息（system + user）
    system_prompt = (
        "你是一个专业的中文新闻编辑助手。请根据给定新闻，"
        "仅输出今日新闻总结；"
        "内容应客观、避免重复与夸张表述。"
    )

    lines = [
        "以下是今日新闻条目（标题/来源/链接/简述）：",
    ]
    for idx, it in enumerate(items, start=1):
        lines.append(
            f"[{idx}] 标题：{it['title']} | 来源：{it['source']} | 链接：{it['url']} | 简述：{it['brief']}"
        )
    lines.append("请仅输出3-5句中文总结，不要列表或标题。")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(lines)},
    ]

    client = DeepseekClient()
    reply = client.chat(name="news-summary", messages=messages)
    return jsonify({"summary": reply, "items": items})


@app.get("/")
def index_page():
    web_dir = Path("web")
    return send_from_directory(web_dir, "index.html")


def create_app():
    return app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
