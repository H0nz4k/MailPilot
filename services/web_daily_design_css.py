"""DataShip visual layer; themes, zoom and legacy layout settings remain usable."""

DATASHIP_CSS = """
.dataship-ui {
    --ds-on-primary: #ffffff;
    --ds-space: 12px;
    font-family: Inter, 'Segoe UI', Roboto, Arial, sans-serif;
    gap: 0;
    max-width: min(var(--app-content-max), 1240px);
    padding: 10px !important;
}
html.theme-svetle .dataship-ui {
    --app-ink: #18243b; --app-muted: #5b6980;
    --app-surface: #ffffff; --app-block: #f8faff; --app-note: #f8faff;
    --app-primary: #255bdd; --q-primary: #255bdd;
    --app-primary-soft: #edf3ff; --app-hover: #edf3ff;
    --app-border: #dce3ed; --app-field-border: #7d8ba2;
    --app-tab: #5b6980; --app-tab-active: #255bdd;
    --app-tab-active-bg: #edf3ff; --app-separator: #dce3ed;
}
html.theme-tmave .dataship-ui {
    --app-ink: #edf2fc; --app-muted: #a7b6cc;
    --app-surface: #151e2f; --app-block: #111a2a; --app-note: #111a2a;
    --app-primary: #91b3ff; --q-primary: #91b3ff;
    --app-primary-soft: #223452; --app-hover: #223452;
    --app-border: #33415a; --app-field-border: #718099;
    --app-tab: #a7b6cc; --app-tab-active: #91b3ff;
    --app-tab-active-bg: #223452; --app-separator: #33415a;
    --ds-on-primary: #101e3b;
}
.dataship-ui .app-topbar {
    border-radius: 14px 14px 0 0;
    background: var(--app-surface);
    box-shadow: none;
    min-height: 56px;
    padding: 8px var(--ds-space);
    flex-wrap: wrap;
    gap: 12px;
}
.dataship-ui .brand-mark { background: transparent; color: var(--app-ink); padding: 0; }
.dataship-ui .brand-mark > .q-icon {
    padding: 8px; width: 40px; height: 40px;
    color: var(--ds-on-primary); background: var(--app-primary); border-radius: 11px;
}
.dataship-ui .app-title { font-size: max(22px, var(--app-heading)); letter-spacing: -.6px; }
.dataship-ui .app-shell { margin-top: 0; border-radius: 0 0 14px 14px; }
.dataship-ui .app-nav { padding: 0 var(--ds-space); }
.dataship-ui .app-nav .q-tab { min-height: 40px; border-radius: 0; }
.dataship-ui .q-tab-panel { padding: var(--ds-space); }
.dataship-ui .q-btn { min-height: 36px; border-radius: 7px; text-transform: none; }
.dataship-ui .q-btn.bg-primary { color: var(--ds-on-primary) !important; }
.dataship-ui .q-btn, .dataship-ui .ds-profile, .dataship-ui .ds-category {
    transition: color 150ms ease, background-color 180ms ease, border-color 180ms ease;
}
.dataship-ui .q-field--outlined .q-field__control:before { border-color: var(--app-field-border, var(--app-muted)); }
.dataship-ui :is(button, [role=button], input, [role=checkbox], [role=tab]):focus-visible {
    outline: 3px solid var(--app-primary); outline-offset: 3px;
}
.ds-page-heading { margin: 0 0 6px; gap: 8px; }
.ds-eyebrow { font-size: 11px; font-weight: 600; letter-spacing: 1.5px; color: var(--app-muted); }
.ds-page-title { font-size: max(22px, var(--app-heading)); font-weight: 600; line-height: 1.2; letter-spacing: -.5px; }
.ds-page-subtitle { color: var(--app-muted); font-size: var(--app-text); }
.ds-daily-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, .85fr); gap: 12px; align-items: start; width: 100%; }
.ds-daily-grid > * { min-width: 0; }
.dataship-ui .ds-daily .app-card { padding: var(--ds-space); border-radius: 10px; gap: 8px; }
.ds-daily-fields { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 10px; width: 100%; }
.ds-profile-choices { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; }
.dataship-ui .ds-profile { min-height: 42px; width: 100%; padding: 6px 10px; text-align: left; justify-content: flex-start; }
.ds-profile .q-btn__content { justify-content: flex-start; overflow-wrap: anywhere; }
.ds-profile-active { color: var(--app-primary); background: var(--app-primary-soft); box-shadow: inset 0 0 0 1px var(--app-primary); }
.dataship-ui .q-btn.ds-profile-active { background: var(--app-primary-soft) !important; box-shadow: inset 0 0 0 1px var(--app-primary); }
.dataship-ui .app-nav .q-tab--active { color: var(--app-tab-active) !important; }
.ds-category-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 4px; width: 100%; }
.ds-category { background: var(--app-block); border-radius: 6px; min-height: 32px; padding: 3px 6px; width: 100%; }
.ds-category .q-checkbox__label { overflow-wrap: anywhere; min-width: 0; }
.ds-category[aria-checked=true] { background: var(--app-primary-soft); color: var(--app-primary); }
.ds-editor-actions { border-top: 1px solid var(--app-separator); padding-top: 8px; gap: 8px; flex-wrap: wrap; }
.ds-summary-name { font-size: max(19px,var(--app-text)); font-weight: 600; overflow-wrap: anywhere; }
.ds-summary-total { font-size: 34px; font-weight: 600; line-height: 1; letter-spacing: -1px; font-variant-numeric: tabular-nums; margin-top: 4px; }
.ds-summary-table { background: transparent; }
.ds-summary-table td, .ds-summary-table th { font-size: var(--app-text); white-space: normal; overflow-wrap: anywhere; }
.ds-summary-table td:last-child { font-variant-numeric: tabular-nums; }
.ds-summary-table .q-table tbody td, .ds-summary-table .q-table thead th { height: 26px; padding: 3px 8px; line-height: 1.25; }
.ds-next-step .q-btn { align-self: flex-start; }
.dataship-ui .action-bar { flex-wrap: wrap; gap: 8px; margin-top: 4px; padding: 10px; border-radius: 10px; }
@media (max-width: 1000px) {
    .ds-daily-grid { grid-template-columns: minmax(0,1fr); }
    .dataship-ui .ds-daily .app-card { padding: 12px; }
}
@media (max-width: 600px) {
    .dataship-ui { padding: 8px !important; }
    .dataship-ui .app-topbar { padding: 12px; }
    .dataship-ui .db-chip { order: 5; flex-basis: 100%; white-space: normal; }
    .dataship-ui .connection-name { flex-shrink: 1; overflow-wrap: anywhere; }
    .dataship-ui .connection-details { display: none; }
    .dataship-ui .q-tab-panel { padding: 14px 10px; }
    .dataship-ui .app-nav { padding: 0 6px; }
    .dataship-ui .app-nav .q-tabs__content { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); transform: none !important; overflow: visible; }
    .dataship-ui .app-nav .q-tabs__arrow { display: none; }
    .dataship-ui .app-nav .q-tab { min-width: 0; padding: 8px 6px; white-space: normal; }
    .dataship-ui .app-nav .q-tab__label { white-space: normal; font-size: 14px; line-height: 1.4; }
    html.nav-side .dataship-ui .workspace { flex-direction: column; }
    html.nav-side .dataship-ui .app-nav { width: 100%; min-width: 0; }
    .ds-daily-fields, .ds-profile-choices, .ds-category-grid { grid-template-columns: minmax(0,1fr); }
    .ds-page-title { font-size: max(22px,var(--app-heading)); }
    .ds-daily .q-field input { font-size: max(16px,var(--app-text)); }
    .ds-daily .action-bar { position: static; }
    .dataship-ui .ds-daily .form-grid { grid-template-columns: minmax(0,1fr); }
}
@media (pointer: coarse) {
    .dataship-ui .q-btn, .dataship-ui .ds-profile, .ds-category { min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) {
    .dataship-ui *, .dataship-ui *:before, .dataship-ui *:after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
"""
