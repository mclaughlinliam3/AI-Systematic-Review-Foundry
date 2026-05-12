"""
Dialogs for the Systematic Review Foundry.
Includes prompt approval, context configuration, output approval, and settings.
"""
import ast
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QPushButton,
    QDialogButtonBox, QMessageBox, QToolTip, QGroupBox, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QSpinBox, QDoubleSpinBox,
    QTabWidget, QWidget, QScrollArea, QCheckBox, QSplitter, QAbstractItemView,
    QFormLayout
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QFont, QCursor, QColor


class PromptApprovalDialog(QDialog):
    """
    Dialog shown before sending any prompt to the LLM.
    Displays the prompt template with f-string variables abbreviated.
    Double-clicking a variable shows its full content in a popup.
    """

    def __init__(self, prompt_key: str, prompt_template: str,
                 variables: dict, config_manager, parent=None):
        super().__init__(parent)
        self.prompt_key = prompt_key
        self.original_template = prompt_template
        self.variables = variables
        self.config = config_manager
        self.result_action = None

        self.setWindowTitle(f"Approve Prompt: {prompt_key}")
        self.setMinimumSize(700, 500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        info = QLabel(f"<b>Prompt:</b> {self.prompt_key}")
        layout.addWidget(info)

        if self.variables:
            var_group = QGroupBox("Variables (click to expand)")
            var_layout = QVBoxLayout(var_group)
            for name, value in self.variables.items():
                val_str = str(value)
                short = (val_str[:80] + "..."
                         if len(val_str) > 80 else val_str)
                btn = QPushButton(f"  {{{name}}} = {short}")
                btn.setStyleSheet("text-align: left; padding: 4px;")
                btn.setToolTip("Click to see full value")
                full_value = val_str

                def make_handler(n, v):
                    def handler():
                        dlg = QDialog(self)
                        dlg.setWindowTitle(f"Variable: {{{n}}}")
                        dlg.setMinimumSize(500, 400)
                        lay = QVBoxLayout(dlg)
                        te = QTextEdit()
                        te.setReadOnly(True)
                        te.setPlainText(v)
                        lay.addWidget(te)
                        close_btn = QPushButton("Close")
                        close_btn.clicked.connect(dlg.close)
                        lay.addWidget(close_btn)
                        dlg.exec()
                    return handler

                btn.clicked.connect(make_handler(name, full_value))
                var_layout.addWidget(btn)
            layout.addWidget(var_group)

        layout.addWidget(QLabel("Prompt Template (editable):"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(self.original_template)
        self.prompt_edit.setFont(QFont("Consolas", 10))
        layout.addWidget(self.prompt_edit)

        btn_layout = QHBoxLayout()
        for label, handler in [
            ("Send As-Is", self._send),
            ("Send Edited (Don't Save)", self._send_edited),
            ("Save & Send", self._save_and_send),
            ("Reset to Default", self._reset),
            ("Cancel", self.reject),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

    def _validate_fstring(self, template: str) -> bool:
        try:
            template.format(**{k: "" for k in self.variables})
            return True
        except (KeyError, ValueError, IndexError):
            return False

    def _send(self):
        self.result_action = "send"
        self.accept()

    def _send_edited(self):
        edited = self.prompt_edit.toPlainText()
        if not self._validate_fstring(edited):
            QMessageBox.warning(
                self, "Invalid Template",
                "The edited prompt has invalid f-string variables. "
                "Edit was rejected.")
            return
        self.original_template = edited
        self.result_action = "send_edited"
        self.accept()

    def _save_and_send(self):
        edited = self.prompt_edit.toPlainText()
        if not self._validate_fstring(edited):
            QMessageBox.warning(
                self, "Invalid Template",
                "The edited prompt has invalid f-string variables. "
                "Edit was rejected.")
            return
        self.config.set_custom_prompt(self.prompt_key, edited)
        self.original_template = edited
        self.result_action = "save_and_send"
        self.accept()

    def _reset(self):
        from default_prompts import DEFAULT_PROMPTS
        default = DEFAULT_PROMPTS.get(self.prompt_key, "")
        self.prompt_edit.setPlainText(default)
        self.config.reset_prompt(self.prompt_key)

    def get_formatted_prompt(self) -> str:
        return self.original_template.format(**self.variables)


class OutputApprovalDialog(QDialog):
    """Dialog to approve or reject LLM output before writing to a section."""

    def __init__(self, section_name: str, output_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Approve Output: {section_name}")
        self.setMinimumSize(600, 450)
        self.approved = False

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"<b>LLM output for:</b> {section_name}"))

        self.output_view = QTextEdit()
        self.output_view.setPlainText(output_text)
        self.output_view.setReadOnly(True)
        layout.addWidget(self.output_view)

        btn_layout = QHBoxLayout()
        approve_btn = QPushButton("✓ Approve && Apply")
        approve_btn.clicked.connect(self._approve)
        btn_layout.addWidget(approve_btn)
        reject_btn = QPushButton("✗ Reject")
        reject_btn.clicked.connect(self.reject)
        btn_layout.addWidget(reject_btn)
        layout.addLayout(btn_layout)

    def _approve(self):
        self.approved = True
        self.accept()


# ═══════════════════════════════════════════════════════════════════
#  Helper: resolve the section_rate index for a section_key
# ═══════════════════════════════════════════════════════════════════

def _section_rate_index(section_key: str) -> int:
    """
    Map a section_key to the index in source['section_rate'].
    section_rate is built as: [intro, results_0, results_1, ...]
    Returns -1 for sections without a specific rating index.
    """
    if section_key == 'intro':
        return 0
    if section_key.startswith('results_'):
        try:
            return int(section_key.split('_')[1]) + 1
        except (ValueError, IndexError):
            return -1
    return -1


def _get_source_rating_for_section(src: dict, section_key: str,
                                    topic_id: str = None,
                                    stat_id: str = None) -> int:
    """
    Return the rating (1-10) of a source for a given section, topic,
    or stat. Returns 0 if no rating exists.
    """
    if topic_id:
        tr = src.get('topic_ratings') or {}
        return tr.get(topic_id, 0)

    if stat_id:
        sr = src.get('stat_ratings') or {}
        return sr.get(stat_id, 0)

    idx = _section_rate_index(section_key)
    if idx < 0:
        return 0
    sr = src.get('section_rate') or []
    if idx < len(sr):
        return sr[idx]
    return 0


# ═══════════════════════════════════════════════════════════════════
#  Filterable list with rating-aware auto-select
# ═══════════════════════════════════════════════════════════════════

class _FilterableList(QWidget):
    """A list widget with search, bulk buttons, and selection status label."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("🔍"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter items…")
        self.search_edit.textChanged.connect(self._filter)
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        # Bulk buttons
        bulk_row = QHBoxLayout()
        add_all = QPushButton("Select All")
        add_all.clicked.connect(self._select_all)
        bulk_row.addWidget(add_all)
        remove_all = QPushButton("Deselect All")
        remove_all.clicked.connect(self._deselect_all)
        bulk_row.addWidget(remove_all)
        bulk_row.addStretch()
        # Selection count label
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #666; font-style: italic;")
        bulk_row.addWidget(self.count_label)
        layout.addLayout(bulk_row)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        self.list_widget.itemSelectionChanged.connect(self._update_count)
        layout.addWidget(self.list_widget)

    def add_item(self, text: str, data, selected: bool = False,
                 rating: int = 0):
        """Add an item. If rating > 0, it is shown as a prefix."""
        if rating > 0:
            display = f"[Rating: {rating}] {text}"
        else:
            display = text
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, data)
        item.setData(Qt.ItemDataRole.UserRole + 1, rating)
        if selected:
            item.setSelected(True)
        # Color-code by rating
        if rating >= 7:
            item.setForeground(QColor("#27ae60"))
        elif 0 < rating <= 3:
            item.setForeground(QColor("#c0392b"))
        self.list_widget.addItem(item)

    def get_selected_data(self) -> list:
        return [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.list_widget.count())
                if self.list_widget.item(i).isSelected()]

    def select_top_n(self, n: int):
        """Select the top N items by rating (descending), deselect others."""
        items_with_ratings = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            rating = item.data(Qt.ItemDataRole.UserRole + 1) or 0
            items_with_ratings.append((i, rating))

        # Sort by rating descending
        items_with_ratings.sort(key=lambda x: x[1], reverse=True)

        for rank, (idx, rating) in enumerate(items_with_ratings):
            item = self.list_widget.item(idx)
            item.setSelected(rank < n and rating > 0)

        self._update_count()

    def has_any_ratings(self) -> bool:
        for i in range(self.list_widget.count()):
            r = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole + 1)
            if r and r > 0:
                return True
        return False

    def _filter(self, text: str):
        text_lower = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text_lower not in item.text().lower())

    def _select_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setSelected(True)
        self._update_count()

    def _deselect_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setSelected(False)
        self._update_count()

    def _update_count(self):
        total = self.list_widget.count()
        selected = len(self.get_selected_data())
        self.count_label.setText(f"{selected} / {total} included in context")


# ═══════════════════════════════════════════════════════════════════
#  Context Configuration Dialog
# ═══════════════════════════════════════════════════════════════════

class ContextConfigDialog(QDialog):
    """
    Dialog for configuring what context is sent to the LLM for a section.
    Knows which section_key it's configuring so it can look up relevant
    section ratings and auto-select top-rated sources.
    """

    def __init__(self, section_key: str, session,
                 current_config: dict = None, parent=None,
                 topic_id: str = None, stat_id: str = None):
        """
        section_key: e.g. 'intro', 'results_0', 'discussion', or a topic/stat id
        topic_id:    if set, use topic_ratings instead of section_rate
        stat_id:     if set, use stat_ratings instead of section_rate
        """
        super().__init__(parent)
        self.setWindowTitle(f"Context Configuration: {section_key}")
        self.setMinimumSize(850, 650)
        self.session = session
        self.section_key = section_key
        self.topic_id = topic_id
        self.stat_id = stat_id
        self.config = current_config or {}
        self._is_first_open = not bool(current_config)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Legend
        legend = QLabel(
            "<b>Legend:</b> "
            "<span style='color:#27ae60'>■ Green = high rating (7-10)</span> · "
            "<span style='color:#c0392b'>■ Red = low rating (1-3)</span> · "
            "Selected items = <b>included</b> in context. "
            "Ratings come from AI section/topic relevance scoring.")
        legend.setWordWrap(True)
        legend.setStyleSheet(
            "background: #f0f0f0; padding: 6px; border-radius: 4px;")
        layout.addWidget(legend)

        tabs = QTabWidget()

        # ── Source Summaries (with rating-aware auto-select) ──
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)

        # Top-N controls
        topn_row = QHBoxLayout()
        topn_row.addWidget(QLabel("Auto-select top"))
        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 999)
        self.top_n_spin.setValue(
            self.config.get('top_n', 10))
        topn_row.addWidget(self.top_n_spin)
        topn_row.addWidget(QLabel("rated sources"))
        auto_btn = QPushButton("Auto-Select Top N")
        auto_btn.setToolTip(
            "Deselect all, then select only the top N sources by rating")
        auto_btn.clicked.connect(self._auto_select_top_n)
        topn_row.addWidget(auto_btn)
        topn_row.addStretch()

        # Summary limit
        topn_row.addWidget(QLabel("Hard limit on summaries sent:"))
        self.summary_limit = QSpinBox()
        self.summary_limit.setRange(0, 9999)
        self.summary_limit.setValue(self.config.get('summary_limit', 0))
        self.summary_limit.setSpecialValueText("No limit")
        self.summary_limit.setToolTip(
            "Even among selected sources, cap how many summaries "
            "are included (0 = no cap)")
        topn_row.addWidget(self.summary_limit)
        summary_layout.addLayout(topn_row)

        self.summary_flist = _FilterableList()
        selected_summaries = set(self.config.get('summaries', []))

        # Determine which rating to show per source
        has_ratings = False
        for s in self.session.sources:
            src = (s if isinstance(s, dict)
                   else s.to_dict() if hasattr(s, 'to_dict') else s)
            num = src.get('number', '?')
            title = src.get('title', 'Untitled')[:55]
            has_summary = "✓" if src.get('summary') else "✗"
            rating = _get_source_rating_for_section(
                src, self.section_key, self.topic_id, self.stat_id)
            if rating > 0:
                has_ratings = True

            # Default selection logic:
            # If there's an existing config, use it.
            # If first open and no config yet, we'll auto-select after.
            if self._is_first_open and has_ratings:
                sel = False  # will be set by auto-select below
            elif selected_summaries:
                sel = num in selected_summaries
            else:
                sel = True  # no config and no ratings → include all

            self.summary_flist.add_item(
                f"[{num}] {has_summary} {title}",
                num, selected=sel, rating=rating)

        summary_layout.addWidget(self.summary_flist)
        tabs.addTab(summary_tab, "Source Summaries")

        # Auto-select top 10 on first open if ratings exist
        if self._is_first_open and has_ratings:
            self.summary_flist.select_top_n(self.top_n_spin.value())

        # ── Full Texts ──
        ft_tab = QWidget()
        ft_layout = QVBoxLayout(ft_tab)
        self.fulltext_flist = _FilterableList()
        selected_ft = set(self.config.get('full_texts', []))
        for s in self.session.sources:
            src = (s if isinstance(s, dict)
                   else s.to_dict() if hasattr(s, 'to_dict') else s)
            if src.get('full_text'):
                num = src.get('number', '?')
                title = src.get('title', 'Untitled')[:60]
                rating = _get_source_rating_for_section(
                    src, self.section_key, self.topic_id, self.stat_id)
                self.fulltext_flist.add_item(
                    f"[{num}] {title}", num,
                    selected=(num in selected_ft), rating=rating)
        ft_layout.addWidget(self.fulltext_flist)
        tabs.addTab(ft_tab, "Full Texts")

        # ── Topics ──
        topic_tab = QWidget()
        topic_layout = QVBoxLayout(topic_tab)
        self.topic_flist = _FilterableList()
        selected_topics = set(self.config.get('topics', []))
        for t in self.session.topics:
            top = (t if isinstance(t, dict)
                   else t.to_dict() if hasattr(t, 'to_dict') else t)
            tid = top.get('topic_id', '?')
            title = top.get('title', 'Untitled')[:60]
            has_text = "✓" if top.get('text') else "✗"
            self.topic_flist.add_item(
                f"{tid}: {has_text} {title}", tid,
                selected=(tid in selected_topics))
        topic_layout.addWidget(self.topic_flist)
        tabs.addTab(topic_tab, "Topics")

        # ── Statistics ──
        stat_tab = QWidget()
        stat_layout = QVBoxLayout(stat_tab)
        self.stat_flist = _FilterableList()
        selected_stats = set(self.config.get('statistics', []))
        for st in self.session.statistics:
            stat = (st if isinstance(st, dict)
                    else st.to_dict() if hasattr(st, 'to_dict') else st)
            sid = stat.get('stat_id', '?')
            q = stat.get('question', 'Untitled')[:60]
            self.stat_flist.add_item(
                f"{sid}: {q}", sid,
                selected=(sid in selected_stats))
        stat_layout.addWidget(self.stat_flist)
        tabs.addTab(stat_tab, "Statistics")

        # ── Review Sections ──
        section_tab = QWidget()
        section_layout = QVBoxLayout(section_tab)
        self.section_flist = _FilterableList()
        selected_sections = set(self.config.get('review_sections', []))
        for sec_name in ['abstract', 'intro', 'methods',
                         'discussion', 'conclusion']:
            self.section_flist.add_item(
                sec_name.capitalize(), sec_name,
                selected=(sec_name in selected_sections))
        for rs in self.session.results:
            r = rs if isinstance(rs, dict) else rs
            sec = r.get('section', 'Results')
            key = f"results_{r.get('section_number', 0)}"
            self.section_flist.add_item(
                f"Results: {sec}", key,
                selected=(key in selected_sections))
        section_layout.addWidget(self.section_flist)
        tabs.addTab(section_tab, "Review Sections")

        layout.addWidget(tabs)

        # ── Included summary at bottom ──
        self.included_label = QLabel("")
        self.included_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self.included_label)
        self._update_included_summary()

        # Connect change signals for live summary
        self.summary_flist.list_widget.itemSelectionChanged.connect(
            self._update_included_summary)
        self.fulltext_flist.list_widget.itemSelectionChanged.connect(
            self._update_included_summary)
        self.topic_flist.list_widget.itemSelectionChanged.connect(
            self._update_included_summary)

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Apply")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _auto_select_top_n(self):
        self.summary_flist.select_top_n(self.top_n_spin.value())
        self._update_included_summary()

    def _update_included_summary(self):
        n_sum = len(self.summary_flist.get_selected_data())
        n_ft = len(self.fulltext_flist.get_selected_data())
        n_top = len(self.topic_flist.get_selected_data())
        self.included_label.setText(
            f"Context will include: {n_sum} summaries, "
            f"{n_ft} full texts, {n_top} topics")

    def get_config(self) -> dict:
        return {
            'summaries': self.summary_flist.get_selected_data(),
            'summary_limit': self.summary_limit.value(),
            'top_n': self.top_n_spin.value(),
            'full_texts': self.fulltext_flist.get_selected_data(),
            'topics': self.topic_flist.get_selected_data(),
            'statistics': self.stat_flist.get_selected_data(),
            'review_sections': self.section_flist.get_selected_data(),
        }


# ═══════════════════════════════════════════════════════════════════
#  Prompt Settings Dialog
# ═══════════════════════════════════════════════════════════════════

class PromptSettingsDialog(QDialog):
    """
    Master prompt settings dialog.
    Allows viewing/editing all prompts, configuring APIs, and model params.
    """

    def __init__(self, config_manager, api_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.api = api_manager
        self.setWindowTitle("Prompt & API Settings")
        self.setMinimumSize(900, 650)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # === API Configuration Tab ===
        api_tab = QWidget()
        api_layout = QVBoxLayout(api_tab)

        api_select = QHBoxLayout()
        api_select.addWidget(QLabel("Active API:"))
        self.api_combo = QComboBox()
        self.api_combo.addItems(["claude", "ollama"])
        self.api_combo.setCurrentText(self.config.active_api)
        api_select.addWidget(self.api_combo)
        api_layout.addLayout(api_select)

        # Claude settings
        claude_group = QGroupBox("Claude API")
        claude_layout = QFormLayout(claude_group)
        self.claude_key_edit = QLineEdit(self.config.claude_api_key)
        self.claude_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        claude_layout.addRow("API Key:", self.claude_key_edit)
        self.claude_model_combo = QComboBox()
        self.claude_model_combo.setEditable(True)
        claude_models = [
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5-20251001",
        ]
        self.claude_model_combo.addItems(claude_models)
        self.claude_model_combo.setCurrentText(self.config.claude_model)
        claude_layout.addRow("Model:", self.claude_model_combo)
        api_layout.addWidget(claude_group)

        # Ollama settings
        ollama_group = QGroupBox("Ollama (Local)")
        ollama_layout = QFormLayout(ollama_group)
        self.ollama_url_edit = QLineEdit(self.config.ollama_url)
        ollama_layout.addRow("URL:", self.ollama_url_edit)
        model_row = QHBoxLayout()
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)
        for m in self.config.ollama_models:
            self.ollama_model_combo.addItem(m)
        if self.config.active_ollama_model:
            self.ollama_model_combo.setCurrentText(
                self.config.active_ollama_model)
        refresh_btn = QPushButton("Refresh Models")
        refresh_btn.clicked.connect(self._refresh_ollama_models)
        model_row.addWidget(self.ollama_model_combo)
        model_row.addWidget(refresh_btn)
        ollama_layout.addRow("Model:", model_row)

        add_model_row = QHBoxLayout()
        self.new_model_edit = QLineEdit()
        self.new_model_edit.setPlaceholderText("model_name:tag")
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_ollama_model)
        add_model_row.addWidget(self.new_model_edit)
        add_model_row.addWidget(add_btn)
        ollama_layout.addRow("Add Model:", add_model_row)
        api_layout.addWidget(ollama_group)

        # NCBI API Key
        ncbi_group = QGroupBox("NCBI PubMed")
        ncbi_layout = QFormLayout(ncbi_group)
        self.ncbi_key_edit = QLineEdit(self.config.ncbi_api_key)
        self.ncbi_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        ncbi_layout.addRow("API Key:", self.ncbi_key_edit)
        cred = self.config.institutional_credentials
        self.inst_user_edit = QLineEdit(cred.get('username', ''))
        ncbi_layout.addRow("Institutional User (Beta):",
                           self.inst_user_edit)
        self.inst_pass_edit = QLineEdit(cred.get('password', ''))
        self.inst_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        ncbi_layout.addRow("Institutional Pass (Beta):",
                           self.inst_pass_edit)
        api_layout.addWidget(ncbi_group)

        test_btn = QPushButton("Test Active API Connection")
        test_btn.clicked.connect(self._test_connection)
        api_layout.addWidget(test_btn)
        self.test_label = QLabel("")
        api_layout.addWidget(self.test_label)
        api_layout.addStretch()
        tabs.addTab(api_tab, "API Settings")

        # === Prompts Tab ===
        prompt_tab = QWidget()
        prompt_layout = QHBoxLayout(prompt_tab)

        self.prompt_list = QListWidget()
        for key in self.config.get_all_prompt_keys():
            item = QListWidgetItem(key)
            if self.config.is_prompt_customized(key):
                item.setText(f"★ {key}")
            self.prompt_list.addItem(item)
        self.prompt_list.currentRowChanged.connect(
            self._on_prompt_selected)
        prompt_layout.addWidget(self.prompt_list, 1)

        right = QVBoxLayout()
        self.prompt_key_label = QLabel("")
        right.addWidget(self.prompt_key_label)
        self.prompt_text_edit = QTextEdit()
        self.prompt_text_edit.setFont(QFont("Consolas", 10))
        right.addWidget(self.prompt_text_edit)

        param_group = QGroupBox("Parameters for this prompt")
        param_layout = QFormLayout(param_group)
        self.p_max_tokens = QSpinBox()
        self.p_max_tokens.setRange(100, 100000)
        param_layout.addRow("Max Tokens:", self.p_max_tokens)
        self.p_temperature = QDoubleSpinBox()
        self.p_temperature.setRange(0.0, 2.0)
        self.p_temperature.setSingleStep(0.1)
        param_layout.addRow("Temperature:", self.p_temperature)
        right.addWidget(param_group)

        prompt_btn_layout = QHBoxLayout()
        save_prompt_btn = QPushButton("Save Prompt")
        save_prompt_btn.clicked.connect(self._save_current_prompt)
        prompt_btn_layout.addWidget(save_prompt_btn)
        reset_prompt_btn = QPushButton("Reset to Default")
        reset_prompt_btn.clicked.connect(self._reset_current_prompt)
        prompt_btn_layout.addWidget(reset_prompt_btn)
        right.addLayout(prompt_btn_layout)

        prompt_layout.addLayout(right, 2)
        tabs.addTab(prompt_tab, "Prompts")

        # === Master Parameters Tab ===
        master_tab = QWidget()
        master_layout = QFormLayout(master_tab)
        master_params = self.config.get_master_params()

        self.m_max_tokens = QSpinBox()
        self.m_max_tokens.setRange(100, 100000)
        self.m_max_tokens.setValue(
            master_params.get('max_tokens', 2000))
        master_layout.addRow("Default Max Tokens:", self.m_max_tokens)

        self.m_temperature = QDoubleSpinBox()
        self.m_temperature.setRange(0.0, 2.0)
        self.m_temperature.setSingleStep(0.1)
        self.m_temperature.setValue(
            master_params.get('temperature', 0.3))
        master_layout.addRow("Default Temperature:", self.m_temperature)

        self.m_max_retries = QSpinBox()
        self.m_max_retries.setRange(1, 20)
        self.m_max_retries.setValue(
            master_params.get('max_retries', 5))
        master_layout.addRow("Max Retries:", self.m_max_retries)

        self.m_num_ctx = QSpinBox()
        self.m_num_ctx.setRange(2048, 131072)
        self.m_num_ctx.setValue(
            master_params.get('num_ctx', 32768))
        master_layout.addRow("Ollama Context Window:", self.m_num_ctx)

        tabs.addTab(master_tab, "Master Parameters")
        layout.addWidget(tabs)

        # Dialog buttons
        btn_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply && Close")
        apply_btn.clicked.connect(self._apply_and_close)
        btn_layout.addWidget(apply_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _refresh_ollama_models(self):
        models = self.api.list_ollama_models()
        self.ollama_model_combo.clear()
        for m in models:
            self.ollama_model_combo.addItem(m)
        if models:
            self.config.ollama_models = models

    def _add_ollama_model(self):
        name = self.new_model_edit.text().strip()
        if name:
            self.ollama_model_combo.addItem(name)
            models = self.config.ollama_models
            if name not in models:
                models.append(name)
                self.config.ollama_models = models
            self.new_model_edit.clear()

    def _test_connection(self):
        self._apply_api_settings()
        result = self.api.test_connection()
        self.test_label.setText(result)

    def _on_prompt_selected(self, row):
        if row < 0:
            return
        key = self.config.get_all_prompt_keys()[row]
        self.prompt_key_label.setText(f"<b>{key}</b>")
        self.prompt_text_edit.setPlainText(self.config.get_prompt(key))
        params = self.config.get_params_for_prompt(key)
        self.p_max_tokens.setValue(params.get('max_tokens', 2000))
        self.p_temperature.setValue(params.get('temperature', 0.3))

    def _save_current_prompt(self):
        row = self.prompt_list.currentRow()
        if row < 0:
            return
        key = self.config.get_all_prompt_keys()[row]
        self.config.set_custom_prompt(
            key, self.prompt_text_edit.toPlainText())
        self.config.set_params_for_prompt(key, {
            'max_tokens': self.p_max_tokens.value(),
            'temperature': self.p_temperature.value(),
        })
        self.prompt_list.item(row).setText(f"★ {key}")

    def _reset_current_prompt(self):
        row = self.prompt_list.currentRow()
        if row < 0:
            return
        key = self.config.get_all_prompt_keys()[row]
        self.config.reset_prompt(key)
        self.config.reset_params_for_prompt(key)
        from default_prompts import DEFAULT_PROMPTS
        self.prompt_text_edit.setPlainText(
            DEFAULT_PROMPTS.get(key, ""))
        self.prompt_list.item(row).setText(key)

    def _apply_api_settings(self):
        self.config.active_api = self.api_combo.currentText()
        self.config.claude_api_key = self.claude_key_edit.text()
        self.config.claude_model = self.claude_model_combo.currentText()
        self.config.ollama_url = self.ollama_url_edit.text()
        self.config.active_ollama_model = \
            self.ollama_model_combo.currentText()
        self.config.ncbi_api_key = self.ncbi_key_edit.text()
        self.config.institutional_credentials = {
            'username': self.inst_user_edit.text(),
            'password': self.inst_pass_edit.text(),
        }
        self.config.set_master_params({
            'max_tokens': self.m_max_tokens.value(),
            'temperature': self.m_temperature.value(),
            'max_retries': self.m_max_retries.value(),
            'num_ctx': self.m_num_ctx.value(),
        })

    def _apply_and_close(self):
        self._apply_api_settings()
        self.accept()
