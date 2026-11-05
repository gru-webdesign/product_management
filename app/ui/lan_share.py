"""Pokretanje i zaustavljanje servera za deljenje u lokalnoj mreži iz aplikacije.

Server radi samo dok postoji bar jedan uključen link, i samo dok je Etapa otvorena. Komentar
stiže iz niti servera, a signal ga prebacuje u glavnu nit (Qt automatski koristi queued vezu).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.services import sharing
from app.share.local_server import LocalShareServer, local_ip
from app.ui.context import AppContext


class LanShare(QObject):
    comment_received = Signal(str)  # project_id

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.server: LocalShareServer | None = None
        self.error = ""
        self.comment_received.connect(self._comment)

    # --- stanje ----------------------------------------------------------------------------------

    def enabled(self) -> bool:
        with self.ctx.session() as s:
            return sharing.mode(s) == "lan"

    @property
    def running(self) -> bool:
        return self.server is not None

    def url(self, token: str) -> str:
        if self.server is None:
            return ""
        return self.server.url(token, local_ip())

    # --- pokretanje ------------------------------------------------------------------------------

    def sync(self) -> bool:
        """Pokreće server ako ima uključenih linkova (lokalni režim), inače ga gasi."""
        with self.ctx.session() as s:
            wanted = sharing.mode(s) == "lan" and sharing.has_live_links(s)
            port = sharing.lan_port(s)
        if not wanted:
            self.stop()
            return False
        if self.server is not None and self.server.port == port:
            return True
        self.stop()
        try:
            server = LocalShareServer(
                self.ctx.db, port, on_comment=lambda pid: self.comment_received.emit(pid)
            )
        except OSError:
            self.error = (
                f"Port {port} je zauzet ili nije dozvoljen. Izaberi drugi port u "
                "Podešavanja → Deljenje."
            )
            return False
        server.start()
        self.server, self.error = server, ""
        return True

    def stop(self) -> None:
        if self.server is not None:
            self.server.stop()
            self.server = None

    def _comment(self, project_id: str) -> None:
        self.ctx.notify("Stigao je novi komentar sa linka.")
        self.ctx.data_changed.emit()
