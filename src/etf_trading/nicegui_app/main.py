"""NiceGUI application entry point."""

from __future__ import annotations

from nicegui import ui


def create_app() -> None:
    """Register NiceGUI routes without starting a web server."""

    @ui.page("/")
    def index() -> None:
        ui.label("ETF 工作台")


def run(host: str = "127.0.0.1", port: int = 8502, reload: bool = False) -> None:
    create_app()
    ui.run(host=host, port=port, reload=reload, title="ETF 工作台")
