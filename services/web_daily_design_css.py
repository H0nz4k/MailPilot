"""DataShip visual layer; themes, zoom and legacy layout settings remain usable."""

DATASHIP_CSS = """
.dataship-ui {
    --ds-on-primary: var(--custom-on-primary, #ffffff);
    --ds-space: 16px;
    font-family: 'Segoe UI', Inter, Roboto, Arial, sans-serif;
    gap: 0;
    max-width: var(--app-content-max);
    padding: 10px !important;
}
html.theme-svetle .dataship-ui {
    --app-ink: #131b2e; --app-muted: #444651;
    --app-surface: #ffffff; --app-block: #f2f3ff; --app-note: #f2f3ff;
    --app-primary: #00236f; --q-primary: #00236f;
    --app-primary-soft: #eaedff; --app-hover: #eaedff;
    --app-border: #c5c5d3; --app-field-border: #7d8ba2;
    --app-tab: #444651; --app-tab-active: #00236f;
    --app-tab-active-bg: #eaedff; --app-separator: #c5c5d3;
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
    border-radius: 8px;
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
    background: var(--app-primary); border-radius: 6px;
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
.dataship-ui .app-shell { margin-top: 12px; border: 0; border-radius: 8px; background: transparent; overflow: visible; }
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
.ds-daily-grid { display: grid; grid-template-columns: minmax(320px, .85fr) minmax(0, 1.4fr); gap: 20px; align-items: start; width: 100%; }
.ds-daily-grid > * { min-width: 0; }
.dataship-ui .ds-daily { padding: 0; border-left: 0; gap: 10px !important; }
.dataship-ui .ds-daily .app-card { padding: var(--ds-space); border-radius: 8px; gap: 12px; border: 1px solid var(--app-border); }
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
.dataship-ui .action-bar { flex-wrap: wrap; gap: 10px; margin-top: 8px; padding: 12px 16px; border-radius: 8px; background: var(--app-surface); }
.dataship-ui .action-bar .inline-status:empty { display: none; }
/* Short mail form, visible recipient chips and a footer that never scrolls away. */
.ds-mail-dialog.q-card { width: 740px; max-width: calc(100vw - 24px); max-height: calc(100dvh - 32px); padding: 0; gap: 0; display: flex; flex-direction: column; background: var(--app-surface); color: var(--app-ink); border-radius: 8px; }
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
    --app-ink: #131b2e; --app-muted: #4a5870; --app-field: #131b2e;
    --app-field-label: #4a5870; --app-primary: #00236f; --q-primary: #00236f;
    --app-field-border: #7d8ba2; --app-border: #cbd4e2;
    background: #ffffff; color: #131b2e; border: 1px solid #cbd4e2;
    border-radius: 6px; padding: 16px; gap: 12px;
}
.ds-palette-editor .q-field__control { background: #ffffff; }
.ds-palette-picker { --app-ink: #131b2e; --app-field: #131b2e; --app-field-label: #4a5870; color: #131b2e; background: #ffffff; }
.ds-palette-preview { background: var(--app-page-to); color: var(--app-ink); border: 2px solid var(--app-border); padding: 12px; border-radius: 8px; gap: 8px; }
.ds-palette-sample { background: var(--app-surface); border: 1px solid var(--app-border); padding: 12px; border-radius: 6px; gap: 8px; }
.ds-palette-button { background: var(--app-primary); color: var(--custom-on-primary); border-radius: 6px; padding: 8px 12px; }
/* Stitch: strong hierarchy, complete frames and compact operating screens. */
.dataship-ui .app-topbar { border: 1.5px solid var(--app-border); padding: 12px 16px; }
.dataship-ui .app-shell > .q-tab-panels { background: transparent !important; }
.dataship-ui .app-topbar .q-tabs { background: transparent !important; border: 0; }
.dataship-ui .app-nav .q-tab--active { background: var(--app-primary-soft); box-shadow: inset 0 -3px 0 var(--app-primary); }
.dataship-ui .db-chip { border-radius: 6px; padding: 3px 6px; }
.dataship-ui .db-chip.connection-ready { color: var(--app-ok); background: var(--app-ok-bg); }
.dataship-ui .db-chip.connection-ready .connection-name { color: inherit; }
.dataship-ui .app-card, .dataship-ui .q-card:not(.ds-mail-dialog) {
    border: 1.5px solid var(--app-border); border-radius: 8px;
    background: var(--app-surface); color: var(--app-ink); box-shadow: none;
}
.dataship-ui .app-card { padding: var(--ds-space); gap: 12px; }
.dataship-ui .ui-block { border: 0; padding: 0; }
html.blocks-emphasized .dataship-ui :is(.app-card,.q-card,.app-note,.ui-block,.ds-selected-category) {
    border: 2px solid var(--app-primary);
}
html.blocks-emphasized .dataship-ui .ds-daily { border: 0; }
.dataship-ui .ds-report-toolbar { display: flex; flex-direction: row; align-items: center; flex-wrap: wrap; width: 100%; }
.dataship-ui .ds-report-toolbar .ds-profile-choices { flex: 1 1 320px; display: block; min-width: 0; }
.dataship-ui .ds-editor-actions { border: 0; padding: 0; margin-left: auto; }
.dataship-ui .ds-preview-state { padding: 6px 12px; border: 1px solid var(--app-primary); border-radius: 6px; background: var(--app-primary-soft); color: var(--app-ink); }
.dataship-ui .ds-daily-fields { grid-template-columns: minmax(0,1fr); }
.dataship-ui .ds-selected-categories { gap: 6px; }
.dataship-ui .ds-selected-category { max-width: 100%; gap: 6px; padding: 4px 8px; border: 1px solid var(--app-border); border-radius: 4px; background: var(--app-primary-soft); font-size: var(--app-help); }
.ds-selected-category > div { overflow-wrap: anywhere; }
.dataship-ui .ds-summary-total { color: var(--app-primary); font-size: 44px; }
.ds-summary-table thead { background: var(--app-primary-soft); }
.ds-summary-table tbody tr:nth-child(even) { background: var(--app-block); }
.ds-summary-table .q-table tbody td, .ds-summary-table .q-table thead th { height: 44px; padding: 8px 12px; }
.dataship-ui .ds-summary .action-bar { width: 100%; padding: 12px 0 0; border-radius: 0; box-shadow: none; border: 0; border-top: 1px solid var(--app-border); position: static; margin-top: 0; }
.dataship-ui .ds-summary .action-bar > .q-col { flex-basis: 100%; }
.dataship-ui .ds-summary .inline-status { white-space: normal; overflow-wrap: anywhere; }
.dataship-ui .ds-summary .inline-status:empty { display: none; }
.ds-next-step { padding: 0 2px; gap: 10px; }
.ds-admin-layout > .q-tab-panels { width: 100%; background: transparent !important; }
.ds-admin-nav { border: 1px solid var(--app-border); border-radius: 8px; padding: 6px; }
.ds-admin-nav .q-tabs__content { flex-wrap: wrap; justify-content: flex-start; overflow: visible; }
.ds-admin-nav .q-tab { flex: 0 1 auto; min-height: 48px; }
.ds-admin-nav .q-tab__label { white-space: normal; text-align: left; }
.ds-admin-nav .q-tabs__arrow { display: none; }
.ds-settings-grid { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 20px; width: 100%; align-items: start; }
.ds-settings-column { min-width: 0; gap: 20px; }
.ds-settings-card { width: 100%; padding: 20px; gap: 14px; }
.ds-settings-card > .app-heading { width: calc(100% + 40px); margin: -20px -20px 4px; padding: 16px 20px; background: var(--app-primary-soft); border-bottom: 1px solid var(--app-border); border-radius: 6px 6px 0 0; }
.ds-settings-card .q-field, .ds-settings-card .q-expansion-item { width: 100%; min-width: 0; }
.ds-settings-card .q-field__control { border-radius: 4px; }
.ds-settings-card .ds-service-status { padding: 12px; border: 1px solid var(--app-border); border-radius: 6px; background: var(--app-block); overflow-wrap: anywhere; width: 100%; }
.ds-settings-card .q-btn__content { white-space: normal; }
.ds-settings-save { width: 100%; justify-content: flex-end; padding: 12px 0; }
.ds-mail-task { border: 1.5px solid var(--app-border); padding: 18px; border-radius: 8px; box-shadow: none; }
.ds-mail-task .ds-task-title { font-size: var(--app-heading); font-weight: var(--app-weight-heading); }
.ds-task-line { font-size: var(--app-text); overflow-wrap: anywhere; }
.ds-task-badge { font-size: var(--app-help); color: var(--app-ink) !important; background: var(--app-primary-soft) !important; border: 1px solid var(--app-primary); padding: 6px 10px; }
.ds-task-actions { border-top: 1px solid var(--app-border); padding-top: 12px; width: 100%; }
.ds-closing-card { width: 100%; }
.ds-closing-period { max-width: 600px; gap: 16px; }
.ds-report-option { padding: 8px 12px; background: var(--app-block); border: 1px solid var(--app-border); border-radius: 6px; }
.ds-report-option:has(.q-checkbox[aria-checked=true]) { border-color: var(--app-primary); background: var(--app-primary-soft); }
.ds-option-help { padding-left: 40px; }
.ds-output-file { padding: 10px 0; border-top: 1px solid var(--app-border); gap: 12px; }
.ds-output-file > .app-text { flex: 1 1 240px; min-width: 0; overflow-wrap: anywhere; }
.ds-closing-results:empty { display: none; }
.nicegui-content:has(> .dataship-ui) { padding: 4px; gap: 0; }
.dataship-ui .app-topbar { min-height: 72px; padding: 8px 16px; }
.dataship-ui .ds-daily .ds-summary { gap: 8px; }
.dataship-ui .ds-summary-heading { gap: 12px; }
.dataship-ui .ds-summary-heading .ds-summary-name { font-size: var(--app-help); }
.dataship-ui .ds-summary .action-bar { border-top: 0; padding: 0 0 10px; border-bottom: 1px solid var(--app-border); }
.dataship-ui .ds-summary .ds-next-step { padding-bottom: 8px; border-bottom: 1px solid var(--app-border); }
.ds-summary-table .q-table__middle { max-height: clamp(220px, calc(100dvh - 550px), 540px); overflow: auto; }
.ds-summary-table thead th { position: sticky; top: 0; z-index: 1; background: var(--app-primary-soft); }
.ds-closing-options { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }
@media (max-width: 700px) {
    .ds-closing-options { grid-template-columns: minmax(0,1fr); }
    .ds-summary-table .q-table__middle { max-height: none; }
}
@media (max-width: 1100px) {
    .ds-settings-grid { grid-template-columns: minmax(0,1fr); }
}
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
    .ds-admin-nav .q-tab { flex-basis: 50%; }
    .ds-report-toolbar .ds-editor-actions { width: 100%; margin-left: 0; }
    .ds-settings-card { padding: 16px; }
    .ds-settings-card > .app-heading { width: calc(100% + 32px); margin: -16px -16px 4px; padding: 12px 16px; }
    .ds-dialog-title { padding: 12px 16px; }
    .ds-dialog-body { padding: 4px 16px 12px; }
}
@media (prefers-reduced-motion: reduce) {
    *, *:before, *:after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
"""
