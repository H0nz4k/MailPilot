# DataShip · BUILD quality pass

Source: `Jakeschincariol/master-skills/skills/build`. Adapted for the existing **PySide6 / Qt Widgets desktop app**, not a new website.

## 1. Product specification

**Audience:** office and canteen staff, including users 55+.
**Primary job:** prepare a daily report, export its PDF, or schedule/confirm reliable email delivery without struggling with configuration.

**Existing screens (do not remove):** Daily status, Closing, Z 17-01, Bulk message, Overview, Administration.
**Existing architecture:** Python + PySide6 UI, PostgreSQL data, PDFs, NSSM-compatible background scheduler, Windows portable EXE. Keep the current stack; do not migrate to Next.js/React or replace the database layer.
**Acceptance:** unchanged report contents and business rules; the scheduler runs with separately configured times, reports meaningful status/errors; admin access protected; saved report can export headlessly; GUI can be used at 1366×768 and 1920×1080, including high-DPI Windows.
**Not in scope:** replacing PostgreSQL, introducing online accounts, unrelated redesign, modifying live services or email recipients.

## 2. Design direction

Mode: **Use** (work tool, not marketing site). Clear, compact, accessible.
- At most three visible typography roles, consistent fonts and action button sizing.
- Preserve users' configurable themes, density, and text scaling.
- Keep the main action (preview / export / schedule / save) visible and explicit, with confirmation of success or a precise failure reason.
- Avoid unnecessary scrolling, especially in the report wizard. Prefer clear tabs or short progressive sections.
- The sidebar/navigation must not consume the content on a 1366×768 laptop.
- Keyboard focus order, tab navigation and button labels must work without a mouse.
- Reduced motion and minimum contrast for text and state colors. Do not sacrifice legibility for glass effects.

## 3. Incremental BUILD slices

1. **Baseline:** capture behavior and screenshots of each screen at 1366×768 / 1920×1080, and Windows 125%/150% scaling. Record user flows; execute existing automated tests.
2. **Wizard:** reduce unnecessary steps and scrolling while preserving all PDF/scheduler settings; write regression tests before changing behavior.
3. **Consistency:** consolidate repetitive Qt styles, fonts, primary actions and status badges using existing `gui_qt/theme.py`.
4. **Feedback:** verify export/email/scheduler loading, success, error, retry, empty-state UI; no silent failures.
5. **Access and keyboard:** verify 55+ legibility, contrast, focus, admin lock, large actionable controls.
6. **Ship:** run all tests, inspect screenshot diffs, build portable Windows EXE, smoke-test Windows/NSSM/email, publish only after verified approval.

## 4. QA matrix

| Flow | Acceptance |
|---|---|
| Daily report | Select date, report, PDF options; preview/export consistent with DB result |
| Scheduled mail | Separate times honored; no duplicate send; visible runtime status |
| Saved report headless export | CLI runs without UI and produces expected named PDF |
| Administration | Password protection and 60s inactivity lock preserved |
| Errors | Missing DB/credentials/network produce actionable status, no silent success |
| Window sizes | No clipping, horizontal overflow or inaccessible primary actions |
| Keyboard | Logical focus order, Enter/Space actions, visible focus and Escape dialogs |
| Builds | Tests pass; portable EXE launches on supported Windows; worker runs independently |

**Evidence rule:** no "fixed", "production ready" or "deployed" claims without executed tests and Windows verification. Record outstanding checks in PR.

## 5. Findings from initial repository inspection (2026-11-02)

- The current default branch README says **MailPilot v12.8** and primary UI is **PySide6**, whereas the end-user product is called **DataShip**; branding/CLI names deserve a separate backwards-compatible review.
- Existing desktop UI is concentrated in `gui_qt/main_window.py` (~83 KB), with theme tokens in `gui_qt/theme.py`; prefer incremental extraction, not rewrite.
- Numerous existing Python tests cover scheduler, PDF and GUI helpers. Run them before editing; passing status has **not** been confirmed in this audit.
- BUILD's `sitecheck.py` and browser viewport checks target HTML websites, **not native Qt windows**. Do not claim that running them validates this GUI. Qt screenshot, accessibility and keyboard testing are required instead.

## Status

This commit establishes scope/design/QA criteria. **No UI, backend, database or production behavior has been changed.** Build, test results, screenshots, live integrations and Windows checks remain **unverified**.
