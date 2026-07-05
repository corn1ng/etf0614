def test_nicegui_app_factory_imports_without_running_server():
    from etf_trading.nicegui_app.main import create_app, run

    assert callable(create_app)
    assert callable(run)
