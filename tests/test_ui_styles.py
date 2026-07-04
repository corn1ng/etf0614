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
    assert 'width: 15.5rem !important;' in css
    assert 'max-width: 15.5rem !important;' in css
    assert '[data-testid="stSidebarContent"]' in css
    assert 'padding: 0.75rem 0.65rem;' in css
    assert '[data-testid="stSidebar"] .stRadio' in css
