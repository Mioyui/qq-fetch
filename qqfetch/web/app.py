"""FastAPI 浏览页入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Config, load_config
from ..errors import ConfigError
from .services import BrowserService


def create_app(config_path: Optional[str] = None, config: Optional[Config] = None) -> FastAPI:
    """创建浏览页应用。"""
    cfg = config or load_config(config_path)
    app = FastAPI(title="qqfetch 浏览页", docs_url=None, redoc_url=None)
    _register_views(app, cfg)
    return app


def run_web_server(config: Config, host: str, port: int) -> int:
    """启动本地浏览页服务。"""
    import uvicorn

    app = create_app(config=config)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def _register_views(app: FastAPI, config: Config) -> None:
    """注册页面与 API 路由。"""
    service = BrowserService(config)
    web_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(web_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        """返回主页面。"""
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "request": request,
                "title": "qqfetch 说说浏览页",
                "default_source": "local",
                "default_page_size": 20,
                "default_comment_page_size": 10,
            },
        )

    @app.get("/api/friends")
    def api_friends(source: str = Query("local")):
        """列出某个数据源下可用的好友。"""
        try:
            return {"items": service.list_friends(source)}
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/shuoshuo")
    def api_shuoshuo(
        source: str = Query("local"),
        target_qq: int = Query(...),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        sort: str = Query("desc"),
        start_date: str | None = Query(None),
        end_date: str | None = Query(None),
        preset: str = Query("all"),
    ):
        """查询说说分页数据。"""
        try:
            return service.list_shuoshuo(
                source=source,
                target_qq=target_qq,
                page=page,
                page_size=page_size,
                sort=sort,
                start_date=start_date,
                end_date=end_date,
                preset=preset,
            )
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/comments")
    def api_comments(
        source: str = Query("local"),
        target_qq: int = Query(...),
        tid: str = Query(...),
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
    ):
        """查询评论分页数据。"""
        try:
            return service.list_comments(
                source=source,
                target_qq=target_qq,
                tid=tid,
                page=page,
                page_size=page_size,
            )
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
