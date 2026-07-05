"""Visual system for the NiceGUI ETF workbench."""

from __future__ import annotations

from nicegui import ui


WORKBENCH_CSS = """
:root {
  --wb-bg: #f4f7fb;
  --wb-panel: #ffffff;
  --wb-panel-soft: #f8fafc;
  --wb-ink: #111827;
  --wb-muted: #64748b;
  --wb-sidebar: #0f172a;
  --wb-sidebar-soft: #172554;
  --wb-line: #dbe3ef;
  --wb-blue: #2563eb;
  --wb-green: #16a34a;
  --wb-red: #dc2626;
  --wb-amber: #d97706;
}
body {
  background: var(--wb-bg);
  color: var(--wb-ink);
  letter-spacing: 0;
}
.workbench-shell {
  min-height: 100vh;
  background: var(--wb-bg);
}
.workbench-sidebar {
  width: 188px;
  background: linear-gradient(180deg, var(--wb-sidebar), #111c35);
  color: #e5edf7;
  border-right: 1px solid rgba(148, 163, 184, 0.16);
}
.workbench-brand {
  height: 44px;
  display: flex;
  align-items: center;
  padding: 0 14px;
  font-weight: 800;
  color: #f8fafc;
}
.workbench-nav-item {
  height: 38px;
  border-radius: 6px;
  padding: 0 10px;
  display: flex;
  align-items: center;
  color: #cbd5e1;
  text-decoration: none;
}
.workbench-nav-item:hover {
  background: rgba(37, 99, 235, 0.14);
  color: #ffffff;
}
.workbench-nav-item.is-active {
  background: rgba(37, 99, 235, 0.26);
  color: #ffffff;
  box-shadow: inset 2px 0 0 #60a5fa;
}
.workbench-main {
  min-width: 0;
}
.workbench-topbar {
  height: 42px;
  border-bottom: 1px solid var(--wb-line);
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(12px);
}
.workbench-page {
  padding: 12px 16px 16px;
  gap: 12px;
}
.workbench-page-title {
  font-size: 22px;
  line-height: 28px;
  font-weight: 800;
  letter-spacing: 0;
}
.workbench-page-caption {
  color: var(--wb-muted);
  font-size: 13px;
  line-height: 18px;
}
.workbench-toolbar {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.workbench-section-tab {
  height: 32px;
  border: 1px solid var(--wb-line);
  border-radius: 6px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  color: #475569;
  text-decoration: none;
  background: #ffffff;
}
.workbench-section-tab.is-active {
  border-color: rgba(37, 99, 235, 0.5);
  color: var(--wb-blue);
  background: #eff6ff;
}
.workbench-metric {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: var(--wb-panel);
  padding: 9px 10px;
  min-width: 128px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.workbench-metric-value {
  font-size: 20px;
  line-height: 24px;
  font-weight: 800;
}
.workbench-metric-label {
  color: var(--wb-muted);
  font-size: 12px;
}
.workbench-data-table {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  overflow: hidden;
  background: #ffffff;
}
.workbench-data-table .q-table th {
  height: 34px;
  font-size: 12px;
  color: #334155;
  background: #f8fafc;
  font-weight: 700;
}
.workbench-data-table .q-table td {
  height: 34px;
  font-size: 13px;
}
.workbench-chart-panel {
  min-height: 420px;
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.workbench-alert {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
}
.tone-neutral { color: #475569; }
.tone-info { color: var(--wb-blue); }
.tone-success { color: var(--wb-green); }
.tone-warning { color: var(--wb-amber); }
.tone-danger { color: var(--wb-red); }
@media (max-width: 720px) {
  .workbench-sidebar { width: 58px; }
  .workbench-brand { padding: 0 8px; font-size: 0; }
  .workbench-page { padding: 10px; }
  .workbench-page-title { font-size: 20px; }
}
"""


def apply_theme() -> None:
    ui.add_head_html(f"<style>{WORKBENCH_CSS}</style>")


def tone_class(tone: str) -> str:
    if tone in {"neutral", "info", "success", "warning", "danger"}:
        return f"tone-{tone}"
    return "tone-neutral"
