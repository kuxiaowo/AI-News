import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from tool.config import get_config
from backend.logger_setup import get_logger
from backend.deepseek_client import DeepseekClient


class NewsProvider:
    """基于天聚数行 TianAPI 综合新闻接口的新闻提供者。

    文档参见仓库内《综合新闻API接口 - 天聚数行TianAPI.html》；
    典型请求：GET base_url?key=APIKEY&num=10
    典型响应：{"code":200,"msg":"success","result":{"newslist":[...]}}
    每条 newslist 包含的常用字段：title, description, source, url, ctime, picUrl
    """

    def __init__(self, ttl_minutes: int = 10, config_path: str = "./config.json"):
        self.logger = get_logger("news.tianapi")
        cfg = get_config(config_path)
        self.cfg = cfg
        tcfg = cfg.get("tianapi", {})
        self.base_url: str = tcfg.get("base_url", "https://apis.tianapi.com/generalnews/index")
        self.key: str = tcfg.get("key", "")
        self.timeout: int = int(tcfg.get("timeout", 15))
        self.cache_items: List[Dict[str, Any]] | None = None
        self.cache_expire: datetime | None = None
        self.ttl = timedelta(minutes=ttl_minutes)
        self.brief_enrich: bool = bool(cfg.get("app", {}).get("brief_enrich", True))
        self.brief_len_min: int = int(cfg.get("app", {}).get("brief_len_min", 12))
        self.brief_len_max: int = int(cfg.get("app", {}).get("brief_len_max", 24))

    def get_today_news(self, count: int = 8, keyword: str | None = None) -> List[Dict[str, Any]]:
        now = datetime.now()
        # 缓存（仅在未指定关键词时使用全量缓存）
        if (not keyword) and self.cache_items and self.cache_expire and now < self.cache_expire:
            self.logger.info("use cached news, size=%d", len(self.cache_items))
            return self.cache_items[:count]

        if not self.key:
            self.logger.error("TianAPI key is empty. Please set tianapi.key in config.json")
            return []

        # 为了过滤当天数据，先多取一些（最多50）
        today_str = now.strftime("%Y-%m-%d")
        fetch_num = min(50, max(count * 2, count, 30))
        params = {
            "key": self.key,
            "num": fetch_num,
        }
        if keyword:
            params["word"] = keyword
        try:
            self.logger.info("GET %s params=%s", self.base_url, params)
            resp = requests.get(self.base_url, params=params, timeout=self.timeout)
            raw = resp.text
            self.logger.info("Raw TianAPI response: %s", raw[:2000])
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            self.logger.exception("request TianAPI failed")
            return []

        items = self._parse_response(data)
        # 仅保留今天的新闻
        items = [it for it in items if it.get("date") == today_str]
        # 补充空简介
        if self.brief_enrich and items:
            self._enrich_briefs(items)
        # 赋 id
        for i, it in enumerate(items, start=1):
            it.setdefault("id", i)

        # 缓存（仅缓存无关键词版本）
        if not keyword:
            self.cache_items = items
            self.cache_expire = now + self.ttl
        self.logger.info("tianapi got %d news items%s", len(items), f" (keyword='{keyword}')" if keyword else "")
        # 简介兜底：为空时用标题
        for it in items:
            if not (it.get("brief") or "").strip():
                it["brief"] = it.get("title", "")
        return items[:count]

    def _parse_response(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            if data.get("code") not in (200, "200"):
                self.logger.error("TianAPI non-200 code: %s, msg=%s", data.get("code"), data.get("msg"))
                return []
            result = data.get("result") or {}
            newslist = result.get("newslist") or []
        except Exception:
            self.logger.exception("invalid TianAPI payload structure")
            return []

        items: List[Dict[str, Any]] = []
        for obj in newslist:
            if not isinstance(obj, dict):
                continue
            title = str(obj.get("title", "")).strip()
            url = str(obj.get("url", "")).strip()
            if not title or not url:
                continue
            source = str(obj.get("source", "")).strip() or "天聚数行"
            brief = str(obj.get("description", "")).strip()
            ctime = str(obj.get("ctime", "")).strip()
            date_str = self._to_date(ctime)
            items.append({
                "title": title,
                "source": source,
                "url": url,
                "brief": brief,
                "date": date_str,
            })
        return items

    @staticmethod
    def _to_date(ctime: str) -> str:
        # 尝试匹配 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS
        m = re.search(r"(\d{4}-\d{2}-\d{2})", ctime)
        if m:
            return m.group(1)
        # 回退为空，让前端忽略
        return ""

    def refresh(self, count: int = 30) -> List[Dict[str, Any]]:
        """强制刷新缓存并返回最新数据。"""
        self.cache_items = None
        self.cache_expire = None
        return self.get_today_news(count=count, keyword=None)

    def _enrich_briefs(self, items: List[Dict[str, Any]]):
        targets = [(idx, it) for idx, it in enumerate(items) if not (it.get("brief") or "").strip()]
        if not targets:
            return
        titles = [f"标题：{it['title']}（来源：{it.get('source','')}）" for _, it in targets]

        # 组织 DeepSeek 批量请求：要求严格 JSON 数组，顺序对齐
        sys = (
            "你是新闻编辑助手。根据给定‘标题（和来源）’，为每条生成一条中文简介，"
            f"长度约为{self.brief_len_min}-{self.brief_len_max}个汉字，客观精炼，避免夸张与标点过多。"
            "严格输出 JSON 数组（仅字符串数组），顺序与输入一致，不要任何额外说明或代码块。"
        )
        user = "请为以下标题生成简介：\n" + "\n".join([f"- {t}" for t in titles])

        client = DeepseekClient()
        # 若处于 mock 模式，直接用标题截断兜底
        if client.mock_mode:
            for _, it in targets:
                it["brief"] = it["title"][: self.brief_len_max]
            return

        try:
            reply = client.chat(
                name="brief-enrich",
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": user},
                ],
                max_tokens=800,
            )
            arr = None
            try:
                arr = json.loads(reply)
            except Exception:
                # 尝试从文本中截取 JSON 数组
                s = reply.find("[")
                e = reply.rfind("]")
                if s != -1 and e != -1 and e > s:
                    arr = json.loads(reply[s:e+1])
            if not isinstance(arr, list):
                raise ValueError("brief-enrich is not array")
            # 赋值（长度不匹配时按可用部分）
            for i, (idx, it) in enumerate(targets):
                if i < len(arr) and isinstance(arr[i], str) and arr[i].strip():
                    it["brief"] = arr[i].strip()
                else:
                    it["brief"] = it["title"][: self.brief_len_max]
        except Exception:
            self.logger.exception("brief enrichment failed, fallback to title truncate")
            for _, it in targets:
                it["brief"] = it["title"][: self.brief_len_max]
