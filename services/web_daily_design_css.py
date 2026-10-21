"""DataShip visual layer; themes, zoom and legacy layout settings remain usable."""

DATASHIP_CSS = """
.dataship-ui {
    --ds-space: 20px;
    font-family: Inter, 'Segoe UI', Roboto, Arial, sans-serif;
    gap: 0;
    max-width: min(var(--app-content-max), 1240px);
    padding: 24px !important;
}
/* Barvy dodává UI_THEMES (ui_theme.py): horcicova (výchozí), svestkova, kremova. */
html body, html body.body--dark { background: var(--app-page-to) !important; }
.dataship-ui .app-topbar {
    position: sticky; top: 0; z-index: 20;
    background: var(--ds-bar, var(--app-surface));
    border: 0; border-bottom: 1px solid var(--app-border);
    border-radius: 0;
    box-shadow: 0 2px 10px rgba(0,0,0,.18);
    min-height: 64px;
    padding: 0 24px;
    margin: -24px -24px 24px;
    display: flex; align-items: center;
    flex-wrap: nowrap;
    gap: 24px;
}
html.theme-kremova .dataship-ui .app-topbar {
    --app-ink: #ffffff; --app-muted: #f1dfe3; --app-tab: #f1dfe3; --app-tab-active: #ffffff;
    --app-border: rgba(255,255,255,.35); color: #ffffff;
}
html.theme-kremova .dataship-ui .app-topbar .brand-mark > .q-icon { background: #ffffff; color: var(--app-primary); }
.dataship-ui .brand-mark { background: transparent; color: var(--app-ink); padding: 0; }
.dataship-ui .brand-mark > .q-icon {
    padding: 8px; width: 40px; height: 40px;
    color: var(--ds-on-primary); background: var(--app-primary); border-radius: 11px;
}
.dataship-ui .app-title { font-size: 18px; font-weight: 700; letter-spacing: -.3px; line-height: 1.1; }
.dataship-ui .ds-stage { font-size: 11px; color: var(--app-muted); }
.dataship-ui .app-topbar .connection-name { font-size: 13px; color: var(--app-muted); max-width: 220px; }
.dataship-ui .ds-period { font-size: 13px; color: var(--app-muted); white-space: nowrap; margin-left: auto; }
.dataship-ui .ds-connection-pill {
    height: 32px; padding: 0 12px; border-radius: 999px; cursor: pointer;
    background: var(--app-bad-bg); color: var(--app-bad); font-size: 13px; font-weight: 600;
}
.dataship-ui .ds-connection-pill.connection-ready { background: var(--app-ok-bg); color: var(--app-ok); }
.dataship-ui .ds-connection-pill .connection-caption { color: inherit; font-size: 13px; font-weight: 600; }
.dataship-ui .ds-period + .ds-connection-pill, .dataship-ui .ds-connection-pill { margin-left: auto; }
.dataship-ui .ds-period:not([style*="display: none"]) + .ds-connection-pill { margin-left: 0; }
.ds-hide { display: none !important; }
.dataship-ui .app-shell { margin-top: 0; border: 0 !important; box-shadow: none !important; background: transparent !important; }
.dataship-ui .ds-top-nav { background: transparent !important; border: 0 !important; padding: 0; min-width: 0; align-self: stretch; }
.dataship-ui .ds-top-nav .q-tab { min-height: 64px; padding: 0 14px; border-radius: 0; color: var(--app-tab); background: transparent !important; }
.dataship-ui .ds-top-nav .q-tab:hover { color: var(--app-ink); background: var(--ds-surface-2, var(--app-hover)) !important; }
.dataship-ui .ds-top-nav .q-tab__label { font-size: 15px; font-weight: 500; }
.dataship-ui .ds-top-nav .q-tab--active .q-tab__label { font-weight: 700; }
.dataship-ui .ds-top-nav .q-tab__indicator { height: 3px; color: var(--app-primary); background: var(--app-primary); }
.dataship-ui .ds-top-nav .q-tab[name=admin], .dataship-ui .ds-top-nav .q-tab:last-child { margin-left: 8px; border-left: 1px solid var(--app-border); }
.dataship-ui .q-tab-panel { padding: var(--ds-space); }
.dataship-ui .q-btn { min-height: 40px; border-radius: 10px; text-transform: none; font-weight: 600; }
.dataship-ui .q-btn:active { transform: translateY(1px); }
.dataship-ui .q-btn--outline:hover, .dataship-ui .q-btn--flat:hover { background: var(--ds-surface-2, var(--app-hover)); }
.dataship-ui .q-btn.bg-primary, .q-dialog .q-btn.bg-primary { color: var(--ds-on-primary) !important; }
.dataship-ui .ds-primary-cta, .q-dialog .ds-primary-cta {
    min-height: 48px; padding: 0 24px; font-size: 15px; font-weight: 700;
    background: var(--app-primary) !important; color: var(--ds-on-primary) !important;
    box-shadow: 0 2px 8px color-mix(in srgb, var(--app-primary) 40%, transparent);
}
.dataship-ui .ds-primary-cta:hover, .q-dialog .ds-primary-cta:hover { filter: brightness(1.1); }
.dataship-ui .app-card, .q-dialog .ds-drawer {
    background: var(--app-surface) !important; border: 1px solid var(--app-border) !important; border-radius: 10px;
    box-shadow: 0 2px 4px rgba(0,0,0,.35), 0 10px 28px rgba(0,0,0,.4);
}
html.theme-kremova .dataship-ui .app-card { box-shadow: 0 1px 3px rgba(40,30,20,.12), 0 8px 24px rgba(40,30,20,.1); }
.dataship-ui .app-heading, .ds-section-title { font-size: 17px !important; font-weight: 700; color: var(--app-ink); }
.ds-section-title { margin-top: 8px; }
.dataship-ui .q-btn, .dataship-ui .ds-profile, .dataship-ui .ds-category {
    transition: color 150ms ease, background-color 180ms ease, border-color 180ms ease;
}
.dataship-ui .q-field--outlined .q-field__control:before, .q-dialog .q-field--outlined .q-field__control:before { border: 1px solid var(--app-muted) !important; }
.dataship-ui .q-field--outlined .q-field__control { background: var(--ds-surface-2, var(--app-block)); border-radius: 8px; }
.dataship-ui .q-field--outlined:hover .q-field__control:before { border-color: var(--app-ink) !important; }
.dataship-ui :is(button, [role=button], input, [role=checkbox], [role=tab]):focus-visible {
    outline: 3px solid var(--app-primary); outline-offset: 3px;
}
.ds-page-heading { margin: 0 0 6px; gap: 8px; }
.ds-eyebrow { font-size: 12px; font-weight: 600; letter-spacing: 1.5px; color: var(--app-muted); }
.ds-page-title { font-size: max(24px, var(--app-heading)); font-weight: 600; line-height: 1.2; letter-spacing: -.5px; }
.ds-page-subtitle { color: var(--app-muted); font-size: var(--app-text); }
.dataship-ui .q-field__label { font-size: 13px; color: var(--app-muted); }
.dataship-ui .q-field__native, .dataship-ui .q-checkbox__label { font-size: var(--app-text); }
.ds-daily-grid.ds-daily-single { grid-template-columns: minmax(0, 1fr); max-width: 760px; margin: 0 auto; }
.ds-daily .ds-page-heading, .ds-daily .action-bar { max-width: 760px; margin-left: auto; margin-right: auto; width: 100%; }
.ds-daily-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, .85fr); gap: 20px; align-items: start; width: 100%; }
.ds-daily-grid > * { min-width: 0; }
.dataship-ui .ds-daily .app-card { padding: var(--ds-space); border-radius: 10px; gap: 16px; }
.ds-daily-fields { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 16px; width: 100%; }
.ds-profile-choices { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; }
.dataship-ui .ds-profile { min-height: 42px; width: 100%; padding: 6px 10px; text-align: left; justify-content: flex-start; }
.ds-profile .q-btn__content { justify-content: flex-start; overflow-wrap: anywhere; }
.ds-profile-active { color: var(--app-primary); background: var(--app-primary-soft); box-shadow: inset 0 0 0 1px var(--app-primary); }
.dataship-ui .q-btn.ds-profile-active { background: var(--app-primary-soft) !important; box-shadow: inset 0 0 0 1px var(--app-primary); }
.dataship-ui .app-nav .q-tab--active { color: var(--app-tab-active) !important; }
.ds-category-grid { display: flex; flex-wrap: wrap; gap: 8px; width: 100%; }
.ds-category { border: 1px solid var(--app-muted); border-radius: 999px; min-height: 40px; padding: 4px 14px 4px 6px; background: transparent; color: var(--app-ink); cursor: pointer; }
.ds-category:hover { border-color: var(--ds-accent-text, var(--app-primary)); background: var(--ds-surface-2, var(--app-hover)); }
.ds-category .q-checkbox__label { overflow-wrap: anywhere; min-width: 0; font-size: 14px; }
.ds-category[aria-checked=true] { background: var(--app-primary); border-color: var(--app-primary); color: var(--ds-on-primary); font-weight: 700; }
.ds-category[aria-checked=true] .q-checkbox__bg { border-color: var(--ds-on-primary) !important; background: var(--ds-on-primary) !important; }
.ds-category[aria-checked=true] .q-checkbox__svg { color: var(--app-primary) !important; }
.ds-category.ds-zero { opacity: .6; }
.ds-total-line { margin-top: 12px; padding: 14px 18px; border-radius: 10px; background: var(--ds-surface-2, var(--app-block)); border: 1px solid var(--app-border); }
.ds-total-caption { font-size: 17px; font-weight: 600; }
.ds-detail-toggle { color: var(--ds-accent-text, var(--app-primary)) !important; font-size: 13px; min-height: 32px !important; }
.ds-advanced { margin-top: 8px; border-top: 1px solid var(--app-separator); }
.ds-toggle-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; width: 100%; }
.ds-toggle-card { border: 1px solid var(--app-muted); border-radius: 10px; padding: 12px 14px; background: transparent; min-height: 56px; }
.ds-toggle-card:hover { border-color: var(--ds-accent-text, var(--app-primary)); background: var(--ds-surface-2, var(--app-hover)); }
.ds-toggle-card[aria-checked=true] { background: var(--app-primary); border-color: var(--app-primary); color: var(--ds-on-primary); font-weight: 700; }
.ds-toggle-card[aria-checked=true] .q-checkbox__bg { border-color: var(--ds-on-primary) !important; background: var(--ds-on-primary) !important; }
.ds-toggle-card[aria-checked=true] .q-checkbox__svg { color: var(--app-primary) !important; }
.ds-narrow { max-width: 760px; }
.ds-toggle-card[aria-checked=true] .q-checkbox__label, .ds-category[aria-checked=true] .q-checkbox__label { color: var(--ds-on-primary) !important; }
.dataship-ui .q-tab-panels, .dataship-ui .q-tab-panel { background: transparent !important; }
.dataship-ui .ds-top-nav .q-tab--active { background: transparent !important; }
.ds-steps { gap: 28px !important; }
.ds-step { gap: 16px; align-items: flex-start; }
.ds-step-num { width: 32px; height: 32px; flex: none; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 13px; background: var(--app-primary); color: var(--ds-on-primary); }
.ds-step-body { flex: 1; min-width: 0; gap: 12px; }
.ds-switch-row { padding: 10px 0; border-top: 1px solid var(--app-separator); }
.ds-empty { max-width: 760px; margin: 24px 0; padding: 56px 40px; text-align: center; gap: 12px; background: var(--app-surface); border: 1px solid var(--app-border); border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,.35), 0 10px 28px rgba(0,0,0,.4); }
.ds-empty-icon { width: 72px; height: 72px; border-radius: 20px; display: grid; place-items: center; background: var(--app-primary-soft); color: var(--ds-accent-text, var(--app-primary)); margin-bottom: 8px; }
.ds-empty-title { font-size: 24px; font-weight: 700; }
.ds-empty-text { color: var(--app-muted); max-width: 440px; margin-bottom: 16px; }
.ds-info-icon { color: var(--app-muted); cursor: help; }
.ds-task-card { max-width: 760px; }
.q-dialog .ds-drawer { width: 440px; max-width: 100vw; height: 100vh; border-radius: 0 !important; padding: 24px; gap: 16px; display: flex; flex-direction: column; overflow-y: auto; }
.ds-drawer-title { font-size: 20px; font-weight: 700; }
.ds-drawer-actions { margin-top: auto; padding-top: 16px; border-top: 1px solid var(--app-separator); }
.ds-editor-actions { border-top: 1px solid var(--app-separator); padding-top: 16px; gap: 12px; flex-wrap: wrap; }
.ds-summary-name { font-size: max(19px,var(--app-text)); font-weight: 600; overflow-wrap: anywhere; }
.ds-summary-total { font-size: 34px; font-weight: 600; line-height: 1; letter-spacing: -1px; font-variant-numeric: tabular-nums; margin-top: 4px; }
.ds-summary-table { background: transparent; }
.ds-summary-table td, .ds-summary-table th { font-size: var(--app-text); white-space: normal; overflow-wrap: anywhere; }
.ds-summary-table td:last-child { font-variant-numeric: tabular-nums; }
.ds-summary-table .q-table tbody td, .ds-summary-table .q-table thead th { height: 36px; padding: 6px 12px; line-height: 1.35; }
.ds-next-step .q-btn { align-self: flex-start; }
.dataship-ui .action-bar { flex-wrap: wrap; gap: 12px; margin-top: 16px; padding: 14px 16px; border-radius: 10px; background: var(--app-surface); border: 1px solid var(--app-border); box-shadow: 0 -4px 16px rgba(0,0,0,.25); align-items: center; }
@media (max-width: 1000px) {
    .ds-daily-grid { grid-template-columns: minmax(0,1fr); }
    .dataship-ui .ds-daily .app-card { padding: 12px; }
}
@media (max-width: 600px) {
    .dataship-ui { padding: 8px !important; }
    .dataship-ui .app-topbar { padding: 8px 12px; flex-wrap: wrap; margin: -8px -8px 16px; }
    .ds-toggle-cards { grid-template-columns: minmax(0,1fr); }
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
