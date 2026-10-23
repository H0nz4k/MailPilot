"""Per-window administrator inactivity lock; workers have no GUI session."""
from __future__ import annotations

from time import monotonic

from nicegui import ui

ADMIN_IDLE_SECONDS = 10 * 60

ACTIVITY_SCRIPT = """
<script>
(() => {
  window.datashipActivityController?.abort();
  const controller = new AbortController();
  window.datashipActivityController = controller;
  let lastSent = -Infinity;
  const activity = event => {
    if (!event.isTrusted || document.hidden || !window.did_handshake) return;
    const now = performance.now();
    if (now - lastSent < 1000) return;
    lastSent = now;
    emitEvent('dataship_admin_activity');
  };
  for (const name of ['pointerdown', 'pointermove', 'keydown', 'input', 'wheel', 'touchstart'])
    document.addEventListener(name, activity, {capture: true, passive: true, signal: controller.signal});
})();
</script>
"""


class AdminSessionMixin:
    def _install_admin_session(self) -> None:
        self._admin_client = ui.context.client
        self._admin_before_lock = []
        self._admin_last_activity = None
        ui.on("dataship_admin_activity", self._record_admin_activity, args=[])
        ui.add_body_html(ACTIVITY_SCRIPT)
        self._admin_idle_timer = ui.timer(10, self._check_admin_idle)
        self._admin_client.on_disconnect(self.lock_admin)
        self._admin_client.on_connect(self._check_admin_idle)

    def _start_admin_session(self) -> None:
        self._admin_last_activity = monotonic()
        self.admin_unlocked = True

    def _admin_session_expired(self) -> bool:
        last = getattr(self, "_admin_last_activity", None)
        return last is not None and monotonic() - last >= ADMIN_IDLE_SECONDS

    def _check_admin_idle(self) -> None:
        if self.admin_unlocked and self._admin_session_expired():
            self.lock_admin()
            self.set_status("Administrace byla po 10 minutách nečinnosti uzamčena. Pro změnu nastavení zadejte znovu heslo.")

    def _record_admin_activity(self) -> None:
        # A late browser event must never revive an expired session.
        self._check_admin_idle()
        if self.admin_unlocked:
            self._admin_last_activity = monotonic()

    def _require_admin(self, *, silent: bool = False) -> bool:
        self._check_admin_idle()
        if self.admin_unlocked:
            return True
        if not silent:
            ui.notify("Nastavení je uzamčené. Přihlaste se znovu do administrace.", type="warning")
        return False

    def _close_admin_session(self) -> None:
        if self.admin_unlocked and not self._admin_session_expired():
            for flush in getattr(self, "_admin_before_lock", ()):
                flush()
        self.admin_unlocked = False
        self._admin_last_activity = None
        # Close an administrator's picker as well as the credentials dialog.
        client = getattr(self, "_admin_client", None)
        if self.tabs.value == "admin" and client is not None:
            for element in list(client.elements.values()):
                if isinstance(element, ui.dialog):
                    element.close()
        for name in ("admin_dialog", "database_setup_dialog"):
            dialog = getattr(self, name, None)
            if dialog is not None:
                dialog.close()
        self.admin_password_input.value = ""
        self.admin_password_repeat.value = ""
