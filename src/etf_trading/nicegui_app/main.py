"""NiceGUI application entry point."""

from __future__ import annotations

from urllib.parse import unquote

from nicegui import ui

from .layout import render_shell


NICEGUI_RECONNECT_TIMEOUT_SECONDS = 60.0


def create_app() -> None:
    """Register NiceGUI routes without starting a web server."""

    @ui.page("/")
    def index() -> None:
        render_shell()

    @ui.page("/page/{page_slug}")
    def page(page_slug: str) -> None:
        render_shell(page_slug=page_slug)

    @ui.page("/page/{page_slug}/{section}")
    def page_section(page_slug: str, section: str) -> None:
        render_shell(page_slug=page_slug, section=unquote(section))


def run(host: str = "127.0.0.1", port: int = 8502, reload: bool = False) -> None:
    create_app()
    ui.run(
        host=host,
        port=port,
        reload=reload,
        title="ETF 工作台",
        reconnect_timeout=NICEGUI_RECONNECT_TIMEOUT_SECONDS,
    )
