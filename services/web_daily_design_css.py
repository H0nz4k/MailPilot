"""DataShip visual layer; themes, zoom and legacy layout settings remain usable."""

DATASHIP_CSS = """
.dataship-ui {
    --ds-on-primary: var(--custom-on-primary, #ffffff);
    --ds-space: 16px;
    font-family: Inter, 'Segoe UI', Roboto, Arial, sans-serif;
    gap: 0;
    max-width: min(var(--app-content-max), 1360px);
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

/* One header contains both identity and navigation. */
.dataship-ui .app-topbar {
    border-radius: 14px;
    background: var(--app-surface);
    box-shadow: none;
    padding: 12px 16px;
    min-height: 84px;
    gap: 14px;
    flex-wrap: nowrap;
}
.ds-identity { flex: 0 1 280px; }
.dataship-ui .brand-mark { background: transparent; color: var(--app-ink); padding: 0; border: 0; }
.dataship-ui .brand-mark > .q-icon {
    width: 36px; height: 36px; color: var(--ds-on-primary);
    background: var(--app-primary); border-radius: 10px;
}
.dataship-ui .app-title { font-size: 26px; font-weight: 700; }
.dataship-ui .db-chip { padding: 0; background: transparent; border: 0; flex-wrap: wrap; gap: 5px; }
.dataship-ui .connection-caption { display: none; }
.dataship-ui .connection-name { font-size: var(--app-help); white-space: normal; overflow-wrap: anywhere; }
.dataship-ui .connection-details { display: none; }
.dataship-ui .app-nav { flex: 1 1 auto; padding: 0; width: auto; min-width: 0; }
.dataship-ui .app-nav .q-tab { min-height: 48px; border-radius: 8px; padding: 4px 12px; opacity: 1; }
.dataship-ui .app-nav .q-tab__label { font-size: var(--app-text); }
html.nav-side .dataship-ui .app-nav { width: auto; min-width: 0; border: 0; }
html.nav-side .dataship-ui .app-nav .q-tabs__content { flex-direction: row; flex: 1 1 auto; }
html.nav-side .dataship-ui .app-nav .q-tab { width: auto; }
.dataship-ui .app-nav .q-tab--active { color: var(--app-tab-active) !important; }
.dataship-ui .app-shell { margin-top: 12px; border: 0; border-radius: 12px; background: transparent; overflow: visible; }
.dataship-ui .q-tab-panel { padding: 12px 0; }
html.fields-husta .q-btn, .q-btn, .q-btn--dense { min-height: max(44px, var(--app-control-min)); }
.q-checkbox, .q-toggle, .picker-row { min-height: 44px; }
.dataship-ui .q-btn, .ds-mail-dialog .q-btn { min-height: 44px; border-radius: 8px; text-transform: none; }
.dataship-ui .q-btn.bg-primary { color: var(--ds-on-primary) !important; }
.dataship-ui .q-btn, .dataship-ui .ds-profile, .dataship-ui .ds-category {
    transition: color 150ms ease, background-color 180ms ease, border-color 180ms ease;
}
/* These rules also cover dialogs and menus mounted outside the page root. */
.q-field--dense .q-field__control, .q-field__control {
    min-height: max(54px, var(--app-field-min)); height: auto;
}
.q-field--dense .q-field__marginal { height: 54px; }
.q-field--labeled .q-field__native { padding-top: 24px; padding-bottom: 6px; }
.q-field--dense.q-field--float .q-field__label { transform: translateY(-4px) scale(1); }
.q-field__label { font-size: var(--app-help); line-height: 1.25; }
.q-field__native, .q-field__input { line-height: 1.25; }
.text-caption { font-weight: var(--app-weight-help) !important; font-size: var(--app-help) !important; line-height: 1.4 !important; }
.q-field--outlined .q-field__control:before { border-color: var(--app-field-border, var(--app-border)); }
:is(button, [role=button], input, [role=checkbox], [role=tab]):focus-visible {
    outline: 3px solid var(--app-primary); outline-offset: 3px;
}
.ds-page-heading { margin: 0 0 8px; gap: 8px; }
.ds-page-title { font-size: max(24px, var(--app-heading)); font-weight: var(--app-weight-heading); line-height: 1.2; }
.ds-preview-state { padding: 4px 8px; border-radius: 6px; background: var(--app-primary-soft); color: var(--app-ink); }
.ds-daily-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 20px; align-items: start; width: 100%; }
.ds-daily-grid > * { min-width: 0; }
.dataship-ui .ds-daily { padding: 0; border-left: 0; gap: 10px !important; }
.dataship-ui .ds-daily .app-card { padding: var(--ds-space); border-radius: 12px; gap: 12px; border: 1px solid var(--app-border); }
html.blocks-emphasized .dataship-ui .ds-daily { border: 0; }
html.blocks-emphasized .dataship-ui .ds-daily .app-card { border: 2px solid var(--app-primary); }
.ds-daily-fields { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 12px; width: 100%; }
.ds-profile-choices { display: block; }
.dataship-ui .ds-profile { min-height: 48px; width: 100%; padding: 6px 10px; text-align: left; justify-content: flex-start; }
.ds-profile .q-btn__content { justify-content: flex-start; overflow-wrap: anywhere; }
.ds-profile-active { color: var(--app-primary); background: var(--app-primary-soft); box-shadow: inset 0 0 0 1px var(--app-primary); }
.dataship-ui .q-btn.ds-profile-active { background: var(--app-primary-soft) !important; box-shadow: inset 0 0 0 1px var(--app-primary) !important; }
.ds-category-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; width: 100%; }
.ds-category { background: var(--app-block); border-radius: 6px; min-height: 44px; padding: 4px 8px; width: 100%; }
.ds-category .q-checkbox__label { overflow-wrap: anywhere; min-width: 0; }
.ds-category[aria-checked=true] { background: var(--app-primary-soft); color: var(--app-primary); }
.ds-editor .q-expansion-item__content { padding: 12px 0 0; }
.ds-editor .q-expansion-item__content > .q-card { background: transparent; }
.ds-editor .q-expansion-item__content > * { margin-bottom: 12px; }
.ds-editor-actions { border-top: 1px solid var(--app-separator); padding-top: 10px; gap: 8px; flex-wrap: wrap; }
.ds-summary-name { font-size: var(--app-text); font-weight: max(600, var(--app-weight-text)); overflow-wrap: anywhere; }
.ds-summary-total { font-size: 42px; font-weight: var(--app-weight-heading); line-height: 1.1; font-variant-numeric: tabular-nums; margin-top: 4px; }
.ds-summary-table { background: transparent; }
.ds-summary-table td { font-weight: var(--app-weight-text); }
.ds-summary-table td, .ds-summary-table th { font-size: var(--app-text); white-space: normal; overflow-wrap: anywhere; }
.ds-summary-table td:last-child { font-variant-numeric: tabular-nums; }
.ds-summary-table .q-table tbody td, .ds-summary-table .q-table thead th { height: 38px; padding: 6px 8px; line-height: 1.3; }
.dataship-ui .action-bar { flex-wrap: wrap; gap: 10px; margin-top: 8px; padding: 12px 16px; border-radius: 12px; background: var(--app-surface); }
.dataship-ui .action-bar .inline-status:empty { display: none; }
/* Short mail form, visible recipient chips and a footer that never scrolls away. */
.ds-mail-dialog.q-card { width: 740px; max-width: calc(100vw - 24px); max-height: calc(100dvh - 32px); padding: 0; gap: 0; display: flex; flex-direction: column; background: var(--app-surface); color: var(--app-ink); border-radius: 14px; }
.ds-mail-dialog { --ds-on-primary: var(--custom-on-primary, #ffffff); }
html.theme-tmave .ds-mail-dialog { --ds-on-primary: #101e3b; }
.ds-dialog-title { font-size: var(--app-heading); font-weight: var(--app-weight-heading); padding: 14px 20px; flex-shrink: 0; }
.ds-dialog-body { min-height: 0; overflow-y: auto; padding: 4px 20px 16px; gap: 12px; flex: 1 1 auto; }
.ds-dialog-footer { padding: 12px 20px; border-top: 1px solid var(--app-border); background: var(--app-surface); flex-shrink: 0; }
.ds-mail-schedule { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 12px; }
.ds-profile-details .q-item { min-height: 44px; padding: 4px 0; }
.ds-profile-details .q-expansion-item__content { padding: 8px 0; }
.ds-recipient-editor .ui-help:empty { display: none; }
.ds-recipient-entry .q-field { flex: 1; }
.ds-recipient-entry .q-field__native { padding-top: 8px; padding-bottom: 8px; }
.ds-recipient-chip { background: var(--app-primary-soft); color: var(--app-ink); border: 1px solid var(--app-primary); border-radius: 8px; padding: 0 0 0 10px; gap: 8px; max-width: 100%; }
.ds-recipient-chip > .q-icon { color: var(--app-primary); }
.ds-recipient-chip > .q-icon + div { overflow-wrap: anywhere; font-size: var(--app-text); }
.ds-recipient-chip .q-btn { min-width: 44px; min-height: 44px; }
html.theme-vlastni .q-btn.bg-primary { color: var(--custom-on-primary) !important; }
/* Keep the palette editor readable even while choosing low-contrast colors. */
.ds-palette-editor {
    --app-ink: #18243b; --app-muted: #4a5870; --app-field: #18243b;
    --app-field-label: #4a5870; --app-primary: #255bdd; --q-primary: #255bdd;
    --app-field-border: #7d8ba2; --app-border: #cbd4e2;
    background: #ffffff; color: #18243b; border: 1px solid #cbd4e2;
    border-radius: 10px; padding: 16px; gap: 12px;
}
.ds-palette-editor .q-field__control { background: #ffffff; }
.ds-palette-picker { --app-ink: #18243b; --app-field: #18243b; --app-field-label: #4a5870; color: #18243b; background: #ffffff; }
.ds-palette-preview { background: var(--app-page-to); color: var(--app-ink); border: 2px solid var(--app-border); padding: 12px; border-radius: 8px; gap: 8px; }
.ds-palette-sample { background: var(--app-surface); border: 1px solid var(--app-border); padding: 12px; border-radius: 6px; gap: 8px; }
.ds-palette-button { background: var(--app-primary); color: var(--custom-on-primary); border-radius: 6px; padding: 8px 12px; }
@media (max-width: 1200px) {
    .dataship-ui .app-topbar { flex-wrap: wrap; }
    .dataship-ui .app-nav { order: 5; width: 100%; flex-basis: 100%; }
    .dataship-ui .ds-identity { flex-grow: 1; }
}
@media (max-width: 1000px) {
    .ds-daily-grid { grid-template-columns: minmax(0,1fr); }
}
@media (max-width: 600px) {
    .dataship-ui { padding: 8px !important; }
    .dataship-ui .app-topbar { padding: 10px; gap: 8px; }
    .dataship-ui .ds-identity { flex-basis: 150px; }
    .dataship-ui .app-nav .q-tabs__content { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); transform: none !important; overflow: visible; }
    .dataship-ui .app-nav .q-tabs__arrow { display: none; }
    .dataship-ui .app-nav .q-tab { min-width: 0; padding: 8px 6px; white-space: normal; }
    .dataship-ui .app-nav .q-tab__label { white-space: normal; font-size: 18px; line-height: 1.3; }
    .dataship-ui .q-tab-panel { padding: 10px 0; }
    .ds-daily-fields, .ds-profile-choices, .ds-category-grid, .ds-mail-schedule { grid-template-columns: minmax(0,1fr); }
    .dataship-ui .action-bar { padding: 10px; }
    .ds-recipient-entry { flex-wrap: wrap; }
    .ds-recipient-entry > .q-field { flex-basis: 100%; }
    .ds-dialog-title { padding: 12px 16px; }
    .ds-dialog-body { padding: 4px 16px 12px; }
}
@media (prefers-reduced-motion: reduce) {
    *, *:before, *:after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
"""
