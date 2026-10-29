"""Glavni prozor. Korak 1: prazan prozor sa nazivom i statusnom trakom (tabovi u Koraku 3)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow

from app import APP_NAME, __version__
from app.db.base import Database


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(960, 600)

        placeholder = QLabel(f"{APP_NAME}\nupravljanje projektima, rokovima i budžetom")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("placeholder")
        placeholder.setStyleSheet("font-size: 18px; color: #6b6b75;")
        self.setCentralWidget(placeholder)

        self.statusBar().showMessage(f"Baza: {db.paths.db_path}   ·   v{__version__}")
