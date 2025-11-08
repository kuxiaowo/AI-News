# AI 今日新闻（AI News）

一个基于 Flask 的轻量服务：自动获取“今日新闻”，调用 DeepSeek 生成“3–5 句中文摘要”，并通过简洁网页展示。支持关键词筛选与每日定时更新。

- 新闻来源：天聚数行 TianAPI「综合新闻」接口
- 摘要生成：DeepSeek Chat Completions（v1 直连）
- 前端：原生 HTML/CSS/JS（无框架）
- 定时：启动即刷新；每日 08:00 / 14:00 / 18:00 自动刷新
- 记录：完整请求与响应日志，便于排错

## 功能特性
- 今日新闻聚合：仅返回当天（YYYY-MM-DD）的新闻
- 关键词筛选：前端输入关键词，后端以 `word` 传给 TianAPI 实时获取
- 摘要生成：基于当日新闻生成“3–5 句中文总结”，简洁客观
- 定时更新：后台守护线程按固定时间点刷新缓存
- 可观测性：请求/响应与调度信息写入日志

## 目录结构
- `main.py`：命令行入口
- `app.py`：Flask 应用与路由（含调度线程）
- `backend/news_provider_tianapi.py`：TianAPI 适配器（获取新闻）
- `backend/deepseek_client.py`：DeepSeek 客户端（生成摘要）
- `backend/logger_setup.py`：日志初始化（控制台 + 文件轮转）
- `tool/config.py`：配置加载
- `web/index.html`：前端页面
- `config.json`：应用与 API 配置
- `APIkey.json`：DeepSeek API Key
- `DEV_REPORT.md`：开发档案（汇报与反思）

## 环境要求
- Python 3.10+
- 网络能访问 TianAPI 与 DeepSeek（若使用摘要真实调用）

## 安装
```
pip install flask requests
```

## 配置
编辑根目录下的 `config.json` 与 `APIkey.json`。

`config.json` 示例：
```
{
  "local_api": {
    "deepseek_api": "https://api.deepseek.com/v1/chat/completions"
  },
  "app": {
    "mock_mode": false,
    "curated_count": 30,
    "log_dir": "logs",
    "log_level": "INFO"
  },
  "tianapi": {
    "base_url": "https://apis.tianapi.com/generalnews/index",
    "key": "YOUR_TIANAPI_KEY",
    "timeout": 15
  }
}
```

`APIkey.json`：
```
{ "APIKEY": "YOUR_DEEPSEEK_API_KEY" }
```

关键说明：
- `app.mock_mode`
  - `true`：不实际调用 DeepSeek（摘要用本地 mock 生成，仅供联调）
  - `false`：真实调用 DeepSeek
- `app.curated_count`：默认返回/生成的新闻条数（前端也会使用 30）
- `tianapi.key`：要替换为你的 TianAPI 有效密钥

## 运行
- 启动服务（默认 0.0.0.0:5000）：
```
python main.py
```
- 自定义参数：
```
python main.py --host 127.0.0.1 --port 8080 --debug
```
- 打开网页：`http://localhost:5000`

## API 文档
- 健康检查：
  - `GET /api/health` → `{ "status": "ok" }`

- 获取新闻：
  - `GET /api/news?count=30&word=芯片`
  - 请求参数：
    - `count`（可选，默认取自 `config.app.curated_count`）
    - `word`（可选，关键词；传入后将以 `word` 调 TianAPI）
  - 响应：
```
{
  "items": [
    {"title":"...","source":"...","url":"...","brief":"...","date":"YYYY-MM-DD","id":1},
    ...
  ]
}
```
  - 说明：仅返回当天新闻；若某条无简介，将以标题兜底。

- 生成摘要：
  - `GET /api/summary?count=30&word=新能源`
  - 同步使用与 `/api/news` 相同的源数据生成“3–5 句中文总结”。
  - 响应：
```
{ "summary": "...", "items": [ ... 同 /api/news ... ] }
```

## 前端使用
- 打开首页 `/`：
  - 顶部“今日新闻摘要”：加载 `/api/summary`
  - “精选新闻”：加载 `/api/news`
  - 右上角“关键词筛选”：输入后点击“筛选”或按回车，会携带 `word` 重新请求上面两接口。

## 定时更新
- 启动服务后立即刷新一次缓存。
- 每日 08:00、14:00、18:00 自动刷新。
- 实现：`app.py` 中后台线程 `_schedule_thread_loop`；日志会打印下次唤醒时间与刷新结果。

## 日志
- 目录：`logs/app.log`
- 覆盖：TianAPI 请求/响应片段、DeepSeek 请求/响应文本、定时任务状态、错误堆栈。
- 排错：
  - TianAPI 报错或空数据 → 检查 `tianapi.key`、配额、网络。
  - DeepSeek 401/403 → 检查 `APIkey.json` 的密钥与权限；429 → 限流；5xx → 服务端问题。

## 部署建议
- 生产请使用 WSGI（如 `gunicorn`）+ 反向代理（Nginx 等）。
- 关闭 Flask Debug，确保 `mock_mode=false`。
- 配置健壮的日志轮转与监控告警。

## 常见问题（FAQ）
- Q：摘要一直是“加载失败”？
  - A：检查 DeepSeek Key 与 `mock_mode` 设置；查看 `logs/app.log` 中 DeepSeek 的 `Raw response` 与错误堆栈。
- Q：`/api/news` 无数据？
  - A：确认 `tianapi.key` 有效、网络可达；关键词过窄也可能导致当天结果为空。
- Q：定时未触发？
  - A：查看日志中“scheduler sleeping until …”；确保系统时区正确，线程未被异常终止。

## 开发与调试
- 修改前端静态页：`web/index.html`
- 修改后端逻辑：`app.py`、`backend/*`
- 重要：任何改动后关注 `logs/app.log` 以快速定位问题。

## 路线图（可选）
- 分页与懒加载；更多新闻端点聚合与去重
- 摘要结果缓存；关键词级缓存策略
- CI/CD 与容器化部署脚本

---
如需二次开发或部署帮助，请在 `DEV_REPORT.md` 查看更详细的架构说明与反思总结。

