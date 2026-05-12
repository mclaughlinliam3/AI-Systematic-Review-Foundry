"""
Systematic Review Foundry — Main Application Window.
QMainWindow with detachable/dockable tabs, File menu (Save/Save As/Load/Export),
Prompt Settings menu, auto-save timer, and session management.
"""
import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QTabBar, QMenuBar, QMenu,
    QFileDialog, QMessageBox, QStatusBar, QWidget, QVBoxLayout,
    QDockWidget, QStyle
)
from PyQt6.QtCore import Qt, QTimer, QByteArray
from PyQt6.QtGui import QAction, QKeySequence, QIcon

from config_manager import ConfigManager, get_default_session_dir
from api_manager import APIManager
from models import ReviewSession
from tabs.main_tab import MainReviewTab
from tabs.sources_tab import SourcesTab
from tabs.topics_stats_tab import TopicsTab, StatsTab
from dialogs import PromptSettingsDialog
from export_manager import export_to_latex, export_to_docx, export_to_pdf


class DetachableTabWidget(QTabWidget):
    """A QTabWidget that supports popping tabs out into floating windows
    and restoring them back into the tab bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(False)
        self.setMovable(True)
        self._detached_windows: dict[str, QDockWidget] = {}

    def detach_tab(self, index: int):
        widget = self.widget(index)
        title = self.tabText(index)

        if title in self._detached_windows:
            self._detached_windows[title].raise_()
            self._detached_windows[title].activateWindow()
            return

        self.removeTab(index)

        dock = QDockWidget(title, self.parent())
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        dock.setFloating(True)
        dock.resize(900, 700)

        def _on_dock_close(event, t=title, w=widget, d=dock):
            self._restore_tab(t, w, d)
            event.accept()

        dock.closeEvent = _on_dock_close

        dock.show()
        self._detached_windows[title] = dock

    def _restore_tab(self, title: str, widget: QWidget, dock: QDockWidget):
        dock.setWidget(None)
        self.addTab(widget, title)
        self._detached_windows.pop(title, None)

    def reattach_all(self):
        for title in list(self._detached_windows.keys()):
            dock = self._detached_windows[title]
            dock.close()


class MainWindow(QMainWindow):
    """Main application window for Systematic Review Foundry."""

    APP_TITLE = "Systematic Review Foundry"

    def __init__(self):
        super().__init__()

        # Core managers
        self.config = ConfigManager()
        self.api = APIManager(self.config)
        self.session = ReviewSession()

        self._load_initial_session()
        self._dirty = False

        self._build_menus()
        self._build_tabs()
        self._build_statusbar()

        # Auto-save timer
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.timeout.connect(self._auto_save)
        interval_ms = self.config.auto_save_interval * 1000
        self._auto_save_timer.start(interval_ms)

        self.setWindowTitle(self._window_title())
        self.resize(1280, 860)

        geom = self.config._config.get("window_geometry")
        if geom:
            try:
                self.restoreGeometry(QByteArray.fromHex(geom.encode()))
            except Exception:
                pass

    def _window_title(self) -> str:
        path = self.config.active_session_path
        name = Path(path).stem if path else "untitled"
        dirty_marker = " *" if self._dirty else ""
        return f"{name}{dirty_marker} — {self.APP_TITLE}"

    def _mark_dirty(self):
        self._dirty = True
        self.setWindowTitle(self._window_title())

    # ── Menu bar ─────────────────────────────────────────────────────

    def _build_menus(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As…", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_as)
        file_menu.addAction(save_as_action)

        load_action = QAction("&Load…", self)
        load_action.setShortcut(QKeySequence("Ctrl+O"))
        load_action.triggered.connect(self._load)
        file_menu.addAction(load_action)

        file_menu.addSeparator()

        export_menu = file_menu.addMenu("&Export")
        for fmt, label in [("docx", "Word Document (.docx)"),
                           ("pdf", "PDF (.pdf)"),
                           ("tex", "LaTeX (.tex)")]:
            act = QAction(label, self)
            act.triggered.connect(lambda checked, f=fmt: self._export(f))
            export_menu.addAction(act)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Prompt Settings menu
        settings_menu = menubar.addMenu("&Prompt Settings")
        open_settings_action = QAction("Open Prompt &Manager…", self)
        open_settings_action.triggered.connect(self._open_prompt_settings)
        settings_menu.addAction(open_settings_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        self._pop_actions = {}
        for tab_name in ["Main Review", "Sources", "Topics",
                         "Statistics (Beta)"]:
            act = QAction(f"Pop Out: {tab_name}", self)
            act.triggered.connect(
                lambda checked, n=tab_name: self._pop_out_tab_by_name(n))
            view_menu.addAction(act)
            self._pop_actions[tab_name] = act

        view_menu.addSeparator()
        reattach_action = QAction("Reattach All Tabs", self)
        reattach_action.triggered.connect(self._reattach_all)
        view_menu.addAction(reattach_action)

    # ── Tabs ─────────────────────────────────────────────────────────

    def _build_tabs(self):
        self.tab_widget = DetachableTabWidget(self)

        self.main_tab = MainReviewTab(
            self.config, self.api, self.session, self)
        self.sources_tab = SourcesTab(
            self.config, self.api, self.session, self)
        self.topics_tab = TopicsTab(
            self.config, self.api, self.session, self)
        self.stats_tab = StatsTab(
            self.config, self.api, self.session, self)

        self.tab_widget.addTab(self.main_tab, "Main Review")
        self.tab_widget.addTab(self.sources_tab, "Sources")
        self.tab_widget.addTab(self.topics_tab, "Topics")
        self.tab_widget.addTab(self.stats_tab, "Statistics (Beta)")

        self.tab_widget.tabBar().tabBarDoubleClicked.connect(
            self._on_tab_double_click)

        self.setCentralWidget(self.tab_widget)

        # Inter-tab wiring
        self.main_tab.section_changed.connect(self._mark_dirty)
        self.main_tab.request_sources_pop.connect(
            self._pop_sources_for_citations)
        try:
            self.sources_tab.sources_changed.connect(self._mark_dirty)
        except AttributeError:
            pass

    def _on_tab_double_click(self, index):
        if index >= 0:
            self.tab_widget.detach_tab(index)

    def _pop_out_tab_by_name(self, name: str):
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == name:
                self.tab_widget.detach_tab(i)
                return

    def _reattach_all(self):
        self.tab_widget.reattach_all()

    def _pop_sources_for_citations(self, numbers: list):
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Sources":
                self.tab_widget.detach_tab(i)
                break
        try:
            self.sources_tab.show_sources_for_citations(numbers)
        except AttributeError:
            pass

    # ── Status bar ───────────────────────────────────────────────────

    def _build_statusbar(self):
        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)
        self._update_status()

    def _update_status(self):
        n_sources = len(self.session.sources)
        n_topics = len(self.session.topics)
        api = self.config.active_api.capitalize()
        path = Path(self.config.active_session_path).name
        self.statusbar.showMessage(
            f"Session: {path}  |  Sources: {n_sources}  |  "
            f"Topics: {n_topics}  |  API: {api}")

    # ── Session I/O ──────────────────────────────────────────────────

    def _load_initial_session(self):
        path = self.config.active_session_path
        if path and Path(path).exists():
            try:
                self.session = ReviewSession.load_from_file(path)
            except Exception:
                self.session = ReviewSession()
        else:
            self.session = ReviewSession()

    def _save(self):
        path = self.config.active_session_path
        if not path:
            return self._save_as()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self.session.save_to_file(path)
            self._dirty = False
            self.setWindowTitle(self._window_title())
            self.statusbar.showMessage(f"Saved to {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _save_as(self):
        default_dir = str(get_default_session_dir())
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Session As", default_dir,
            "JSON Files (*.json);;All Files (*)")
        if path:
            if not path.endswith('.json'):
                path += '.json'
            self.config.active_session_path = path
            self._save()

    def _load(self):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before loading?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save()

        default_dir = str(get_default_session_dir())
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Session", default_dir,
            "JSON Files (*.json);;All Files (*)")
        if path:
            try:
                self.session = ReviewSession.load_from_file(path)
                self.config.active_session_path = path
                self._refresh_all_tabs()
                self._dirty = False
                self.setWindowTitle(self._window_title())
                self._update_status()
                self.statusbar.showMessage(f"Loaded {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Load Error", str(e))

    def _refresh_all_tabs(self):
        self.main_tab.session = self.session
        self.sources_tab.session = self.session
        self.topics_tab.session = self.session
        self.stats_tab.session = self.session

        self.main_tab.refresh_from_session()
        for tab in (self.sources_tab, self.topics_tab, self.stats_tab):
            try:
                tab.refresh_from_session()
            except AttributeError:
                pass

    # ── Export (FIX: correct reorder_citations_for_export signature) ─

    def _export(self, fmt: str):
        ext_map = {"docx": "Word (*.docx)",
                   "pdf": "PDF (*.pdf)",
                   "tex": "LaTeX (*.tex)"}
        default_name = Path(self.config.active_session_path).stem or "review"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export as .{fmt}",
            str(Path.home() / f"{default_name}.{fmt}"),
            f"{ext_map.get(fmt, '')};;All Files (*)")
        if not path:
            return

        try:
            from citation_manager import reorder_citations_for_export

            # reorder_citations_for_export takes a ReviewSession
            # and returns a ReviewSession with renumbered citations
            export_session = reorder_citations_for_export(self.session)

            title = self.session.paper_topic or "Systematic Review"

            if fmt == "tex":
                export_to_latex(export_session, path, title)
            elif fmt == "docx":
                export_to_docx(export_session, path, title)
            elif fmt == "pdf":
                export_to_pdf(export_session, path, title)

            self.statusbar.showMessage(f"Exported to {path}", 5000)
            QMessageBox.information(
                self, "Export Complete",
                f"Review exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── Prompt Settings ──────────────────────────────────────────────

    def _open_prompt_settings(self):
        dlg = PromptSettingsDialog(self.config, self.api, self)
        dlg.exec()

    # ── Auto-save ────────────────────────────────────────────────────

    def _auto_save(self):
        if self._dirty:
            path = self.config.active_session_path
            if path:
                try:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    self.session.save_to_file(path)
                    self._dirty = False
                    self.setWindowTitle(self._window_title())
                    self.statusbar.showMessage("Auto-saved", 2000)
                except Exception:
                    pass

    # ── Close event ──────────────────────────────────────────────────

    def closeEvent(self, event):
        self.tab_widget.reattach_all()

        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes", "Save before closing?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save()

        self.config._config["window_geometry"] = bytes(
            self.saveGeometry().toHex()).decode()
        self.config.save()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Systematic Review Foundry")
    app.setOrganizationName("SystematicReviewFoundry")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
