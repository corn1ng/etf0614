def test_nicegui_app_factory_imports_without_running_server():
    from etf_trading.nicegui_app.main import create_app, run

    assert callable(create_app)
    assert callable(run)


def test_nicegui_layout_exports_shell_renderer():
    from etf_trading.nicegui_app.layout import render_shell

    assert callable(render_shell)
