import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from tool.config import get_config
from backend.logger_setup import get_logger


class NewsProvider:
    """鍩轰簬澶╄仛鏁拌 TianAPI 缁煎悎鏂伴椈鎺ュ彛鐨勬柊闂绘彁渚涜€呫€?
    鏂囨。鍙傝浠撳簱鍐呫€婄患鍚堟柊闂籄PI鎺ュ彛 - 澶╄仛鏁拌TianAPI.html銆嬶紱
    鍏稿瀷璇锋眰锛欸ET base_url?key=APIKEY&num=10
    鍏稿瀷鍝嶅簲锛歿"code":200,"msg":"success","result":{"newslist":[...]}}
    姣忔潯 newslist 鍖呭惈鐨勫父鐢ㄥ瓧娈碉細title, description, source, url, ctime, picUrl
    """

    def __init__(self, ttl_minutes: int = 10, config_path: str = "./config.json"):
        self.logger = get_logger("news.tianapi")
        cfg = get_config(config_path)
        tcfg = cfg.get("tianapi", {})
        self.base_url: str = tcfg.get("base_url", "https://apis.tianapi.com/generalnews/index")
        self.key: str = tcfg.get("key", "")
        self.timeout: int = int(tcfg.get("timeout", 15))
        self.cache_items: List[Dict[str, Any]] | None = None
        self.cache_expire: datetime | None = None
        self.ttl = timedelta(minutes=ttl_minutes)

    def get_today_news(self, count: int = 8, keyword: str | None = None) -> List[Dict[str, Any]]:
        now = datetime.now()
        # 缂撳瓨锛堜粎鍦ㄦ湭鎸囧畾鍏抽敭璇嶆椂浣跨敤鍏ㄩ噺缂撳瓨锛?        if (not keyword) and self.cache_items and self.cache_expire and now < self.cache_expire:
            self.logger.info("use cached news, size=%d", len(self.cache_items))
            return self.cache_items[:count]

        if not self.key:
            self.logger.error("TianAPI key is empty. Please set tianapi.key in config.json")
            return []

        # 涓轰簡杩囨护褰撳ぉ鏁版嵁锛屽厛澶氬彇涓€浜涳紙鏈€澶?0锛?        today_str = now.strftime("%Y-%m-%d")
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
        # 浠呬繚鐣欎粖澶╃殑鏂伴椈
        items = [it for it in items if it.get("date") == today_str]
        # 璧?id
        for i, it in enumerate(items, start=1):
            it.setdefault("id", i)

        # 缂撳瓨锛堜粎缂撳瓨鏃犲叧閿瘝鐗堟湰锛?        if not keyword:
            self.cache_items = items
            self.cache_expire = now + self.ttl
        self.logger.info("tianapi got %d news items%s", len(items), f" (keyword='{keyword}')" if keyword else "")
        # 绠€浠嬪厹搴曪細涓虹┖鏃剁敤鏍囬
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
            source = str(obj.get("source", "")).strip() or "澶╄仛鏁拌"
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
        # 灏濊瘯鍖归厤 YYYY-MM-DD 鎴?YYYY-MM-DD HH:MM:SS
        m = re.search(r"(\d{4}-\d{2}-\d{2})", ctime)
        if m:
            return m.group(1)
        # 鍥為€€涓虹┖锛岃鍓嶇蹇界暐
        return ""

    def refresh(self, count: int = 30) -> List[Dict[str, Any]]:
        """寮哄埗鍒锋柊缂撳瓨骞惰繑鍥炴渶鏂版暟鎹€?""
        self.cache_items = None
        self.cache_expire = None
        return self.get_today_news(count=count, keyword=None)


