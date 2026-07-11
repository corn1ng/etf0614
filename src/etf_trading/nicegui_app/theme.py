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
.workbench-page-header {
  min-width: 0;
}
.workbench-section-tabs {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}
.workbench-toolbar {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}
.workbench-chart-header {
  min-height: 36px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px 14px;
  flex-wrap: wrap;
  min-width: 0;
}
.workbench-chart-title-group {
  min-width: 220px;
  flex: 1 1 320px;
  gap: 0;
}
.workbench-chart-title {
  font-size: 13px;
  line-height: 18px;
  font-weight: 700;
  color: #334155;
}
.workbench-chart-meta-row {
  min-height: 16px;
}
.workbench-chart-meta {
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
}
.workbench-chart-custom-controls {
  min-height: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
.workbench-chart-selector {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 8px 12px;
  flex-wrap: wrap;
  min-width: 0;
}
.workbench-chart-selector .q-field {
  flex: 0 1 420px;
  max-width: 100%;
}
.workbench-chart-note {
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
  max-width: 560px;
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
  overflow-x: auto;
  overflow-y: hidden;
  background: #ffffff;
}
.workbench-data-table--compact {
  display: inline-block;
  width: fit-content;
  max-width: 100%;
  vertical-align: top;
}
.workbench-data-table .q-table__middle {
  overflow-x: auto;
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
.workbench-data-table--compact .q-table {
  width: fit-content;
  max-width: 100%;
}
.workbench-data-table--compact .q-table__middle {
  width: fit-content;
  max-width: 100%;
}
.workbench-data-table--compact .q-table th,
.workbench-data-table--compact .q-table td {
  white-space: nowrap;
}
.workbench-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
  width: 100%;
}
.workbench-detail-group {
  min-width: 0;
}
.workbench-detail-group-title {
  font-size: 13px;
  line-height: 18px;
  font-weight: 700;
  color: #334155;
}
.atomic-metric-strip {
  display: flex;
  align-items: stretch;
  gap: 8px;
  flex-wrap: wrap;
}
.atomic-data-health {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 9px 10px;
  gap: 7px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.atomic-data-health-header {
  min-height: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.atomic-data-health-status {
  border-radius: 999px;
  font-size: 12px;
  line-height: 18px;
  padding: 0 8px;
}
.atomic-data-health-status.is-ready {
  color: #047857;
  background: #ecfdf5;
}
.atomic-data-health-status.is-warning {
  color: #b45309;
  background: #fffbeb;
}
.atomic-data-health-note {
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
}
.atomic-data-health-items {
  display: flex;
  align-items: stretch;
  gap: 8px;
  flex-wrap: wrap;
}
.atomic-data-health-item {
  min-height: 30px;
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  background: #f8fafc;
  padding: 4px 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.atomic-data-health-item.is-empty {
  color: #64748b;
  background: #ffffff;
}
.atomic-data-health-detail {
  align-self: center;
  max-width: 140px;
  font-size: 11px;
  line-height: 14px;
  color: var(--wb-muted);
}
.atomic-workbench {
  min-width: 0;
}
.atomic-workbench-head {
  min-height: 48px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 10px 14px;
  flex-wrap: wrap;
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 9px 10px;
}
.atomic-mode-block {
  min-width: 240px;
}
.atomic-control-label,
.atomic-inspector-kicker {
  font-size: 11px;
  line-height: 14px;
  font-weight: 700;
  color: var(--wb-muted);
}
.atomic-actions {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
.atomic-detail-select {
  width: 260px;
  max-width: 100%;
}
.atomic-filter-bar {
  min-height: 42px;
  display: flex;
  align-items: center;
  gap: 8px 10px;
  flex-wrap: wrap;
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 8px 10px;
}
.atomic-query-input {
  flex: 1 1 280px;
  max-width: 420px;
}
.atomic-filter-select,
.atomic-filter-number {
  flex: 0 1 168px;
}
.atomic-filter-check {
  min-height: 32px;
  display: flex;
  align-items: center;
}
.atomic-workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 390px);
  gap: 10px;
  align-items: start;
  min-width: 0;
}
.atomic-table-pane {
  min-width: 0;
}
.atomic-inspector {
  min-width: 0;
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 10px;
  max-height: calc(100vh - 178px);
  overflow: auto;
  position: sticky;
  top: 54px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.atomic-inspector-title {
  font-size: 15px;
  line-height: 20px;
  font-weight: 800;
  color: #0f172a;
}
.atomic-detail-grid {
  display: grid;
  gap: 9px;
  width: 100%;
}
.atomic-detail-group {
  min-width: 0;
  border-top: 1px solid var(--wb-line);
  padding-top: 8px;
}
.atomic-detail-group-title {
  font-size: 12px;
  line-height: 16px;
  font-weight: 800;
  color: #334155;
}
.atomic-detail-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 26px;
  border-bottom: 1px solid #eef2f7;
}
.atomic-detail-label {
  min-width: 0;
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
}
.atomic-detail-value {
  max-width: 150px;
  overflow-wrap: anywhere;
  text-align: right;
  font-size: 12px;
  line-height: 16px;
  font-weight: 700;
}
.workbench-action-panel {
  width: 360px;
  max-width: 100%;
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 10px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.workbench-action-panel .q-field {
  width: 100%;
}
.workbench-form-panel {
  width: 100%;
}
.workbench-markdown-panel {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 12px 14px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.workbench-success-line,
.workbench-warning-line {
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 600;
}
.workbench-success-line {
  border: 1px solid rgba(22, 163, 74, 0.24);
  background: #ecfdf5;
  color: #047857;
}
.workbench-warning-line {
  border: 1px solid rgba(217, 119, 6, 0.24);
  background: #fffbeb;
  color: #b45309;
}
.workbench-task-panel {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
}
.workbench-task-center {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 10px 12px;
  gap: 6px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.workbench-task-center-header {
  min-height: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.workbench-task-center-status {
  border-radius: 999px;
  font-size: 12px;
  line-height: 18px;
  padding: 0 8px;
  color: #475569;
  background: #f1f5f9;
}
.workbench-task-center-status.is-running {
  color: #1d4ed8;
  background: #eff6ff;
}
.workbench-task-center-status.is-success {
  color: #047857;
  background: #ecfdf5;
}
.workbench-task-center-status.is-failed {
  color: #b91c1c;
  background: #fef2f2;
}
.workbench-task-center-status.is-cancelled {
  color: #b45309;
  background: #fffbeb;
}
.workbench-task-center-meta {
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
}
.workbench-task-center-result {
  margin-top: 4px;
}
.workbench-chart-panel {
  min-height: 420px;
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.workbench-echart-panel {
  min-height: 520px;
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.workbench-range-toggle {
  border: 1px solid var(--wb-line);
  border-radius: 7px;
  background: #ffffff;
  overflow: hidden;
}
.workbench-range-toggle .q-btn {
  min-height: 30px;
  padding: 0 9px;
  font-size: 12px;
}
.workbench-range-toggle .q-btn[aria-pressed="true"],
.workbench-range-toggle .q-btn.q-btn--active {
  color: var(--wb-blue);
  background: #eff6ff;
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
  .workbench-sidebar { width: 58px; flex-shrink: 0; }
  .workbench-brand { padding: 0 8px; font-size: 0; }
  .workbench-nav-item { padding: 0; justify-content: center; font-size: 0; }
  .workbench-nav-item::before {
    content: attr(data-short);
    font-size: 14px;
    font-weight: 700;
  }
  .workbench-page { padding: 10px; }
  .workbench-page-title { font-size: 20px; }
  .workbench-action-panel { width: 100%; }
  .workbench-page .q-field { max-width: 100%; }
  .atomic-workbench-grid { grid-template-columns: 1fr; }
  .atomic-inspector { position: static; max-height: none; }
  .atomic-actions { justify-content: flex-start; width: 100%; }
}
"""


def apply_theme() -> None:
    ui.add_head_html(f"<style>{WORKBENCH_CSS}</style>")


def tone_class(tone: str) -> str:
    if tone in {"neutral", "info", "success", "warning", "danger"}:
        return f"tone-{tone}"
    return "tone-neutral"
