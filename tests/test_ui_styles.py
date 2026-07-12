from etf_trading.ui import styles


def test_global_styles_keep_sidebar_compact(monkeypatch):
    rendered = {}

    def capture_markdown(body, *, unsafe_allow_html=False):
        rendered["body"] = body
        rendered["unsafe"] = unsafe_allow_html

    monkeypatch.setattr(styles.st, "markdown", capture_markdown)

    styles.inject_global_styles()

    css = rendered["body"]
    assert rendered["unsafe"] is True
    assert 'width: 11.5rem !important;' in css
    assert 'max-width: 11.5rem !important;' in css
    assert '15.5rem' not in css
    assert '[data-testid="stSidebarContent"]' in css
    assert 'padding: 0.55rem 0.5rem;' in css
    assert '[data-testid="stSidebar"] .stRadio' in css
    assert ".workbench-page-header" in css
    assert ".workbench-page-header__title" in css
    assert ".workbench-page-header__caption" in css
    assert "margin: 0 0 0.35rem 0;" in css
    assert '[data-testid="stVerticalBlock"]' in css
    assert '[data-testid="stAlert"]' in css
