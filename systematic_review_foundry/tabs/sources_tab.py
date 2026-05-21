"""
Sources Tab — manages source retrieval, summarization, inclusion screening,
and section relevance rating.
"""
import webbrowser
from functools import partial

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QGroupBox, QLabel, QTextEdit, QComboBox, QSpinBox,
    QMessageBox, QInputDialog, QListWidget, QListWidgetItem, QTabWidget,
    QLineEdit, QCheckBox, QProgressBar, QMenu, QAbstractItemView, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QAction, QColor

from dialogs import PromptApprovalDialog, OutputApprovalDialog


class SourceRetrievalWorker(QThread):
    """Background worker for source retrieval."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(object, list, list)
    error = pyqtSignal(str)

    def __init__(self, api_key, search_terms, retmax, per_term_limits=None):
        super().__init__()
        self.api_key = api_key
        self.search_terms = search_terms
        self.retmax = retmax
        self.per_term_limits = per_term_limits

    def run(self):
        try:
            from ncbi_retrieval import retrieve_sources
            sources, textless, abless = retrieve_sources(
                self.api_key, self.search_terms, self.retmax,
                self.per_term_limits,
                progress_callback=lambda msg: self.progress.emit(msg)
            )
            self.finished.emit(sources, textless, abless)
        except Exception as e:
            self.error.emit(str(e))


class SourcesTab(QWidget):
    """Tab for managing sources."""

    sources_changed = pyqtSignal()

    def __init__(self, config_manager, api_manager, session, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.api = api_manager
        self.session = session
        self._per_term_limits = {}  # term -> custom limit
        self._build_ui()
        self._load_from_session()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel: Source list ──
        left = QWidget()
        left_layout = QVBoxLayout(left)

        toolbar = QHBoxLayout()
        retrieve_btn = QPushButton("🔍 Retrieve Sources")
        retrieve_btn.clicked.connect(self._retrieve_sources)
        toolbar.addWidget(retrieve_btn)

        add_btn = QPushButton("+ Add Manual Source")
        add_btn.clicked.connect(self._add_manual_source)
        toolbar.addWidget(add_btn)

        summarize_btn = QPushButton("✦ Batch Summarize")
        summarize_btn.clicked.connect(self._batch_summarize)
        summarize_btn.setToolTip("Summarize All Non Excluded Abstracts")
        toolbar.addWidget(summarize_btn)

        screen_btn = QPushButton("✦ Screen for Inclusion")
        screen_btn.clicked.connect(self._screen_inclusion)
        screen_btn.setToolTip("Screens all sources for included that do not yet have an inclusion verdict")
        toolbar.addWidget(screen_btn)

        rate_btn = QPushButton("✦ Rate for Sections")
        rate_btn.clicked.connect(self._rate_for_sections)
        toolbar.addWidget(rate_btn)

        remove_src_btn = QPushButton("- Remove Source")
        remove_src_btn.clicked.connect(self._remove_source)
        toolbar.addWidget(remove_src_btn)

        left_layout.addLayout(toolbar)

        self.status_label = QLabel("Ready")
        left_layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        self.source_table = QTableWidget()
        self.source_table.setColumnCount(6)
        self.source_table.setHorizontalHeaderLabels(
            ["#", "Title", "Year", "Journal", "Rating", "Summary"])
        self.source_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.source_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.source_table.itemSelectionChanged.connect(
            self._on_source_selected_from_selection)
        left_layout.addWidget(self.source_table)
        splitter.addWidget(left)

        # ── Right panel: Source detail ──
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.detail_title = QLabel("<b>Select a source</b>")
        right_layout.addWidget(self.detail_title)
        self.detail_tabs = QTabWidget()

        # Abstract tab
        abstract_tab = QWidget()
        ab_layout = QVBoxLayout(abstract_tab)
        self.abstract_edit = QTextEdit()
        ab_layout.addWidget(self.abstract_edit)
        save_ab_btn = QPushButton("Save Abstract")
        save_ab_btn.clicked.connect(lambda: self._save_field('abstract'))
        ab_layout.addWidget(save_ab_btn)
        self.detail_tabs.addTab(abstract_tab, "Abstract")

        # Full Text tab
        ft_tab = QWidget()
        ft_layout = QVBoxLayout(ft_tab)
        self.fulltext_edit = QTextEdit()
        ft_layout.addWidget(self.fulltext_edit)
        save_ft_btn = QPushButton("Save Full Text")
        save_ft_btn.clicked.connect(lambda: self._save_field('full_text'))
        ft_layout.addWidget(save_ft_btn)
        self.detail_tabs.addTab(ft_tab, "Full Text")

        # Summary tab
        sum_tab = QWidget()
        sum_layout = QVBoxLayout(sum_tab)
        self.summary_edit = QTextEdit()
        sum_layout.addWidget(self.summary_edit)
        sum_btn_layout = QHBoxLayout()
        save_sum_btn = QPushButton("Save Summary")
        save_sum_btn.clicked.connect(lambda: self._save_field('summary'))
        sum_btn_layout.addWidget(save_sum_btn)
        gen_sum_btn = QPushButton("✦ Generate Summary")
        gen_sum_btn.clicked.connect(self._generate_summary_single)
        sum_btn_layout.addWidget(gen_sum_btn)
        sum_layout.addLayout(sum_btn_layout)
        self.detail_tabs.addTab(sum_tab, "Summary")

        # Info tab
        info_tab = QWidget()
        info_layout = QFormLayout(info_tab)
        self.info_citation = QTextEdit()
        self.info_citation.setMaximumHeight(80)
        info_layout.addRow("Citation:", self.info_citation)
        self.info_doi = QLineEdit()
        info_layout.addRow("DOI:", self.info_doi)
        doi_link_btn = QPushButton("Open DOI in Browser")
        doi_link_btn.clicked.connect(self._open_doi)
        info_layout.addRow("", doi_link_btn)
        self.info_pmid = QLineEdit()
        self.info_pmid.setReadOnly(True)
        info_layout.addRow("PMID:", self.info_pmid)
        self.info_rating = QLabel("")
        info_layout.addRow("Inclusion:", self.info_rating)
        self.info_explanation = QTextEdit()
        self.info_explanation.setMaximumHeight(80)
        self.info_explanation.setReadOnly(True)
        info_layout.addRow("Explanation:", self.info_explanation)
        include_btn = QPushButton("Include")
        include_btn.clicked.connect(lambda: self._set_inclusion(True))
        exclude_btn = QPushButton("Exclude")
        exclude_btn.clicked.connect(lambda: self._set_inclusion(False))
        ai_reassess = QPushButton("AI Assess ✦")
        ai_reassess.clicked.connect(self._ai_solo_screen)
        btn_row = QHBoxLayout()
        btn_row.addWidget(include_btn)
        btn_row.addWidget(exclude_btn)
        btn_row.addWidget(ai_reassess)
        info_layout.addRow("Manual:", btn_row)
        self.detail_tabs.addTab(info_tab, "Info")

        # ── NEW: Ratings tab ──
        ratings_tab = QWidget()
        ratings_layout = QVBoxLayout(ratings_tab)

        ratings_layout.addWidget(QLabel(
            "<b>Section Relevance Ratings</b> (1-10 per results subsection):"))
        self.section_ratings_table = QTableWidget()
        self.section_ratings_table.setColumnCount(2)
        self.section_ratings_table.setHorizontalHeaderLabels(
            ["Section", "Rating"])
        self.section_ratings_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.section_ratings_table.setMaximumHeight(200)
        ratings_layout.addWidget(self.section_ratings_table)

        ratings_layout.addWidget(QLabel(
            "<b>Topic Relevance Ratings</b> (1-10 per topic):"))
        self.topic_ratings_table = QTableWidget()
        self.topic_ratings_table.setColumnCount(2)
        self.topic_ratings_table.setHorizontalHeaderLabels(
            ["Topic", "Rating"])
        self.topic_ratings_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.topic_ratings_table.setMaximumHeight(200)
        ratings_layout.addWidget(self.topic_ratings_table)

        ratings_layout.addWidget(QLabel(
            "<b>Stat Relevance Ratings</b> (1-10 per stat question):"))
        self.stat_ratings_table = QTableWidget()
        self.stat_ratings_table.setColumnCount(2)
        self.stat_ratings_table.setHorizontalHeaderLabels(
            ["Stat Question", "Rating"])
        self.stat_ratings_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.stat_ratings_table.setMaximumHeight(200)
        ratings_layout.addWidget(self.stat_ratings_table)

        ratings_layout.addStretch()
        self.detail_tabs.addTab(ratings_tab, "Ratings")

        right_layout.addWidget(self.detail_tabs)
        splitter.addWidget(right)
        splitter.setSizes([500, 400])
        layout.addWidget(splitter)

        # ── Search Terms section (with per-term limits) ──
        search_group = QGroupBox("Boolean Search Terms")
        search_layout = QVBoxLayout(search_group)

        search_toolbar = QHBoxLayout()
        gen_terms_btn = QPushButton("✦ Generate Search Terms")
        gen_terms_btn.clicked.connect(self._generate_search_terms)
        search_toolbar.addWidget(gen_terms_btn)

        add_term_btn = QPushButton("+ Add Term")
        add_term_btn.clicked.connect(self._add_search_term)
        search_toolbar.addWidget(add_term_btn)

        remove_term_btn = QPushButton("- Remove Selected")
        remove_term_btn.clicked.connect(self._remove_search_term)
        search_toolbar.addWidget(remove_term_btn)

        search_toolbar.addStretch()
        search_toolbar.addWidget(QLabel("Default per-term limit:"))
        self.default_retmax = QSpinBox()
        self.default_retmax.setRange(1, 1000)
        self.default_retmax.setValue(100)
        search_toolbar.addWidget(self.default_retmax)

        set_all_btn = QPushButton("Set All to Default")
        set_all_btn.setToolTip(
            "Reset all per-term limits to the default value")
        set_all_btn.clicked.connect(self._set_all_limits_to_default)
        search_toolbar.addWidget(set_all_btn)

        search_layout.addLayout(search_toolbar)

        # Search terms table with per-term limit column
        self.search_terms_table = QTableWidget()
        self.search_terms_table.setColumnCount(2)
        self.search_terms_table.setHorizontalHeaderLabels(
            ["Search Term", "Limit"])
        self.search_terms_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.search_terms_table.setColumnWidth(1, 80)
        search_layout.addWidget(self.search_terms_table)

        # Inclusion criteria
        criteria_group = QGroupBox(
            "Inclusion Criteria (used for AI screening)")
        criteria_layout = QVBoxLayout(criteria_group)
        self.criteria_edit = QTextEdit()
        self.criteria_edit.setPlaceholderText(
            "Enter criteria, one per line. E.g.:\n"
            "- Must be a primary study\n"
            "- Sample size > 10\n"
            "- Published after 2015")
        self.criteria_edit.setMaximumHeight(100)
        criteria_layout.addWidget(self.criteria_edit)
        search_layout.addWidget(criteria_group)

        layout.addWidget(search_group)

    # ── Helpers ───────────────────────────────────────────────────────

    def _on_source_selected_from_selection(self):
        self._on_source_selected(self.source_table.currentRow())

    def _load_from_session(self):
        self._refresh_table()
        self._refresh_search_terms_table()
        criteria_text = "\n".join(self.session.inclusion_criteria)
        self.criteria_edit.setPlainText(criteria_text)

    def _refresh_table(self):
        self.source_table.setRowCount(0)
        for s in self.session.sources:
            src = s if isinstance(s, dict) else s
            row = self.source_table.rowCount()
            self.source_table.insertRow(row)

            self.source_table.setItem(
                row, 0, QTableWidgetItem(str(src.get('number', ''))))
            self.source_table.setItem(
                row, 1, QTableWidgetItem(str(src.get('title', ''))[:80]))
            self.source_table.setItem(
                row, 2, QTableWidgetItem(str(src.get('year', ''))))
            self.source_table.setItem(
                row, 3, QTableWidgetItem(str(src.get('journal', ''))[:30]))

            rating = src.get('rating')
            rating_text = ("✓" if rating is True
                           else "✗" if rating is False
                           else "?")
            rating_item = QTableWidgetItem(rating_text)
            if rating is True:
                rating_item.setForeground(QColor("#2ecc71"))
            elif rating is False:
                rating_item.setForeground(QColor("#e74c3c"))
            self.source_table.setItem(row, 4, rating_item)

            has_summary = "Yes" if src.get('summary') else "No"
            self.source_table.setItem(
                row, 5, QTableWidgetItem(has_summary))

    def _refresh_search_terms_table(self):
        """Populate the search terms table with per-term limits."""
        self.search_terms_table.setRowCount(0)
        default_limit = self.default_retmax.value()
        for term in self.session.search_terms:
            row = self.search_terms_table.rowCount()
            self.search_terms_table.insertRow(row)
            self.search_terms_table.setItem(
                row, 0, QTableWidgetItem(term))

            limit_spin = QSpinBox()
            limit_spin.setRange(1, 1000)
            limit_spin.setValue(
                self._per_term_limits.get(term, default_limit))
            limit_spin.valueChanged.connect(
                lambda val, t=term: self._on_term_limit_changed(t, val))
            self.search_terms_table.setCellWidget(row, 1, limit_spin)

    def _on_term_limit_changed(self, term: str, value: int):
        self._per_term_limits[term] = value

    def _set_all_limits_to_default(self):
        default_val = self.default_retmax.value()
        self._per_term_limits.clear()
        for row in range(self.search_terms_table.rowCount()):
            widget = self.search_terms_table.cellWidget(row, 1)
            if isinstance(widget, QSpinBox):
                widget.blockSignals(True)
                widget.setValue(default_val)
                widget.blockSignals(False)

    def _on_source_selected(self, row):
        if row < 0 or row >= len(self.session.sources):
            return
        src = self.session.sources[row]
        s = src if isinstance(src, dict) else (
            src.to_dict() if hasattr(src, 'to_dict') else src)

        self.detail_title.setText(
            f"<b>[{s.get('number')}] {s.get('title', 'Untitled')}</b>")
        self.abstract_edit.setPlainText(s.get('abstract') or "")
        self.fulltext_edit.setPlainText(
            s.get('full_text') or "⚠ No full text available")
        self.summary_edit.setPlainText(s.get('summary') or "")
        self.info_citation.setPlainText(s.get('citation') or "")
        self.info_doi.setText(s.get('doi') or "")
        self.info_pmid.setText(s.get('pmid') or "")

        rating = s.get('rating')
        if rating is True:
            self.info_rating.setText("✓ Included")
            self.info_rating.setStyleSheet(
                "color: #2ecc71; font-weight: bold;")
        elif rating is False:
            self.info_rating.setText("✗ Excluded")
            self.info_rating.setStyleSheet(
                "color: #e74c3c; font-weight: bold;")
        else:
            self.info_rating.setText("Not yet screened")
            self.info_rating.setStyleSheet("")

        self.info_explanation.setPlainText(s.get('rate_explain') or "")

        # ── Populate Ratings tab ──
        self._populate_ratings(s)

    def _populate_ratings(self, src: dict):
        """Fill the section and topic ratings tables for a source."""
        # Section ratings
        self.section_ratings_table.setRowCount(0)
        section_rate = src.get('section_rate') or []
        if section_rate:
            # Build section names
            section_names = [f"Intro ({self.session.paper_topic or 'Topic'})"]
            for rs in self.session.results:
                section_names.append(rs.get('section', 'Untitled'))

            for i, rating in enumerate(section_rate):
                row = self.section_ratings_table.rowCount()
                self.section_ratings_table.insertRow(row)
                name = (section_names[i]
                        if i < len(section_names)
                        else f"Section {i}")
                self.section_ratings_table.setItem(
                    row, 0, QTableWidgetItem(name))
                rating_item = QTableWidgetItem(str(rating))
                if rating >= 7:
                    rating_item.setForeground(QColor("#2ecc71"))
                elif rating <= 3:
                    rating_item.setForeground(QColor("#e74c3c"))
                self.section_ratings_table.setItem(row, 1, rating_item)

        # Topic ratings
        self.topic_ratings_table.setRowCount(0)
        topic_ratings = src.get('topic_ratings') or {}
        if topic_ratings:
            topic_names = {}
            for t in self.session.topics:
                top = t if isinstance(t, dict) else t
                topic_names[top.get('topic_id', '')] = top.get(
                    'title', 'Untitled')

            for tid, rating in topic_ratings.items():
                row = self.topic_ratings_table.rowCount()
                self.topic_ratings_table.insertRow(row)
                name = topic_names.get(tid, tid)
                self.topic_ratings_table.setItem(
                    row, 0, QTableWidgetItem(name))
                rating_item = QTableWidgetItem(str(rating))
                if rating >= 7:
                    rating_item.setForeground(QColor("#2ecc71"))
                elif rating <= 3:
                    rating_item.setForeground(QColor("#e74c3c"))
                self.topic_ratings_table.setItem(row, 1, rating_item)

        # Stat ratings
        self.stat_ratings_table.setRowCount(0)
        stat_ratings = src.get('stat_ratings') or {}
        if stat_ratings:
            stat_names = {}
            for st in self.session.statistics:
                stat = st if isinstance(st, dict) else st
                stat_names[stat.get('stat_id', '')] = stat.get(
                    'question', 'Untitled')

            for sid, rating in stat_ratings.items():
                row = self.stat_ratings_table.rowCount()
                self.stat_ratings_table.insertRow(row)
                name = stat_names.get(sid, sid)
                self.stat_ratings_table.setItem(
                    row, 0, QTableWidgetItem(name[:60]))
                rating_item = QTableWidgetItem(str(rating))
                if rating >= 7:
                    rating_item.setForeground(QColor("#2ecc71"))
                elif rating <= 3:
                    rating_item.setForeground(QColor("#e74c3c"))
                self.stat_ratings_table.setItem(row, 1, rating_item)

    # ── Field save ───────────────────────────────────────────────────

    def _save_field(self, field_name):
        row = self.source_table.currentRow()
        if row < 0:
            return
        widgets = {
            'abstract': self.abstract_edit,
            'full_text': self.fulltext_edit,
            'summary': self.summary_edit,
        }
        text = widgets[field_name].toPlainText()
        if isinstance(self.session.sources[row], dict):
            self.session.sources[row][field_name] = text if text else None
        self.sources_changed.emit()

    def _open_doi(self):
        doi = self.info_doi.text().strip()
        if doi:
            url = (f"https://doi.org/{doi}"
                   if not doi.startswith('http') else doi)
            webbrowser.open(url)

    def _set_inclusion(self, included: bool):
        row = self.source_table.currentRow()
        if row < 0:
            return
        if isinstance(self.session.sources[row], dict):
            self.session.sources[row]['rating'] = included
            self.session.sources[row]['rate_explain'] = \
                'Manually set by user'
        self._refresh_table()
        self._on_source_selected(row)
        self.sources_changed.emit()

    def _ai_solo_screen(self):
        row = self.source_table.currentRow()
        if row < 0:
            return

        criteria_text = self.criteria_edit.toPlainText().strip()
        self.session.inclusion_criteria = [
            c.strip() for c in criteria_text.split('\n') if c.strip()]

        has_criteria = bool(self.session.inclusion_criteria)
        prompt_key = ('screen_source_criteria' if has_criteria
                      else 'screen_source_subjective')
        prompt_template = self.config.get_prompt(prompt_key)

        sample_vars = {
            'topic': self.session.paper_topic,
            'source_text': '(source text)',
        }
        if has_criteria:
            sample_vars['criteria'] = '\n'.join(
                self.session.inclusion_criteria)

        dlg = PromptApprovalDialog(
            prompt_key, prompt_template, sample_vars, self.config, self)
        if not dlg.exec():
            return
        template = dlg.original_template

        # prompt
        s = self.session.sources[row]
        src = s if isinstance(s, dict) else s
        text = src.get('abstract') or src.get('title') or ""
        if not text:
            return
        variables = {
            'topic': self.session.paper_topic,
            'source_text': text,
        }
        if has_criteria:
            variables['criteria'] = '\n'.join(
                self.session.inclusion_criteria)
        formatted = template.format(**variables)
        try:
            import ast
            result = self.api.query(
                formatted, max_tokens=200, temperature=0.3)
            print(f"Result for AI screen: {result}")
            parsed = aggro_parse_reason(result)
            s['rating'] = bool(parsed[0])
            s['rate_explain'] = str(parsed[1])
            self.status_label.setText(
                f"Screened source {src.get('number')}: "
                f"{'Include' if parsed[0] else 'Exclude'}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error screening source: {e}")
            self.status_label.setText(
                f"Error screening source: {e}")
            s['rate_explain'] = result

        self._refresh_table()
        self._on_source_selected(row)
        self.sources_changed.emit()

    def _add_manual_source(self):
        title, ok = QInputDialog.getText(
            self, "Add Manual Source", "Source title:")
        if not ok or not title.strip():
            return
        source = {
            "number": len(self.session.sources) + 1,
            "title": title.strip(), "year": "", "journal": "",
            "abstract": "", "full_text": "", "summary": "",
            "citation": "", "doi": "", "pmid": "",
            "rating": None, "rate_explain": "",
        }
        self.session.sources.append(source)
        self._refresh_table()
        self.sources_changed.emit()

    def _remove_source(self):
        row = self.source_table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self, "No Selection",
                "Please select a source to remove.")
            return
        src = self.session.sources[row]
        src_d = src if isinstance(src, dict) else src
        title = src_d.get('title', 'Untitled')[:50]
        num = src_d.get('number', '?')
        reply = QMessageBox.question(
            self, "Remove Source",
            f"Remove source [{num}] \"{title}\"?\n\n"
            f"Note: this will not update existing citation numbers "
            f"in the review text. You may need to fix citations "
            f"manually or re-export with reordering.",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # Clean up citation_validations for this source number
            num_str = str(num)
            self.session.citation_validations.pop(num_str, None)
            # Clean up section_contexts referencing this source
            for cfg in self.session.section_contexts.values():
                for key in ('summaries', 'full_texts'):
                    ref_list = cfg.get(key, [])
                    if num in ref_list:
                        ref_list.remove(num)
            del self.session.sources[row]
            self._refresh_table()
            self.sources_changed.emit()

    # ── Search terms ─────────────────────────────────────────────────

    def _generate_search_terms(self):
        if not self.session.paper_topic:
            QMessageBox.warning(
                self, "No Topic",
                "Please set a paper topic in the Main tab first.")
            return

        prompt_template = self.config.get_prompt('suggest_search_terms')
        variables = {'topic': self.session.paper_topic}
        dlg = PromptApprovalDialog(
            'suggest_search_terms', prompt_template,
            variables, self.config, self)
        if dlg.exec():
            formatted = dlg.get_formatted_prompt()
            try:
                result = self.api.query(
                    formatted, max_tokens=1000, temperature=0.5)
                terms = [t.strip() for t in result.split(';') if t.strip()]
                self.session.search_terms = terms
                self._per_term_limits.clear()
                self._refresh_search_terms_table()
                self.sources_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _add_search_term(self):
        term, ok = QInputDialog.getText(
            self, "Add Search Term", "Boolean search term:")
        if ok and term:
            self.session.search_terms.append(term)
            self._refresh_search_terms_table()
            self.sources_changed.emit()

    def _remove_search_term(self):
        row = self.search_terms_table.currentRow()
        if row >= 0:
            item = self.search_terms_table.item(row, 0)
            if item:
                term = item.text()
                self._per_term_limits.pop(term, None)
            if row < len(self.session.search_terms):
                del self.session.search_terms[row]
            self._refresh_search_terms_table()
            self.sources_changed.emit()

    # ── Retrieval ────────────────────────────────────────────────────

    def _retrieve_sources(self):
        if not self.config.ncbi_api_key:
            QMessageBox.warning(
                self, "No NCBI Key",
                "Please set your NCBI API key in Prompt Settings.")
            return
        if not self.session.search_terms:
            QMessageBox.warning(
                self, "No Search Terms",
                "Please generate or add search terms first.")
            return

        # Build per-term limits from table
        per_term = {}
        for row in range(self.search_terms_table.rowCount()):
            item = self.search_terms_table.item(row, 0)
            widget = self.search_terms_table.cellWidget(row, 1)
            if item and isinstance(widget, QSpinBox):
                per_term[item.text()] = widget.value()

        self.status_label.setText("Retrieving sources...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self._retrieval_worker = SourceRetrievalWorker(
            self.config.ncbi_api_key,
            self.session.search_terms,
            self.default_retmax.value(),
            per_term_limits=per_term if per_term else None)
        self._retrieval_worker.progress.connect(
            lambda msg: self.status_label.setText(msg))
        self._retrieval_worker.finished.connect(self._on_retrieval_done)
        self._retrieval_worker.error.connect(self._on_retrieval_error)
        self._retrieval_worker.start()

    def _on_retrieval_done(self, sources, textless, abless):
        self.progress_bar.setVisible(False)
        self.session.sources = [
            s.to_dict() if hasattr(s, 'to_dict') else s for s in sources]
        self._refresh_table()
        self.status_label.setText(
            f"Retrieved {len(sources)} sources. "
            f"{len(textless)} missing full text, "
            f"{len(abless)} missing abstracts.")
        self.sources_changed.emit()

    def _on_retrieval_error(self, msg):
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Retrieval Error", msg)

    # ── Summarization ────────────────────────────────────────────────

    def _batch_summarize(self):
        sources_to_summarize = []
        for i, s in enumerate(self.session.sources):
            src = s if isinstance(s, dict) else s
            if src.get('rating') is False:
                continue
            if src.get('summary'):
                continue
            if src.get('abstract') or src.get('full_text'):
                sources_to_summarize.append(i)

        if not sources_to_summarize:
            QMessageBox.information(
                self, "Nothing to Summarize",
                "All applicable sources already have summaries.")
            return
        print(f"Summarizing source {i}")
        prompt_template = self.config.get_prompt('summarize_source')
        sample_text = "(source text will be inserted here)"
        dlg = PromptApprovalDialog(
            'summarize_source', prompt_template,
            {'source_text': sample_text}, self.config, self)
        if not dlg.exec():
            return

        template = dlg.original_template
        self.status_label.setText(
            f"Summarizing {len(sources_to_summarize)} sources...")

        for idx in sources_to_summarize:
            src = self.session.sources[idx]
            text = src.get('full_text') or src.get('abstract') or ""
            if not text:
                continue
            formatted = template.format(source_text=text)
            try:
                result = self.api.query(
                    formatted, max_tokens=2000, temperature=0.3)
                self.session.sources[idx]['summary'] = result
                self.status_label.setText(
                    f"Summarized source {src.get('number', idx)}")
            except Exception as e:
                self.status_label.setText(
                    f"Error on source {src.get('number', idx)}: {e}")

        self._refresh_table()
        self.sources_changed.emit()
        self.status_label.setText("Batch summarization complete.")

    def _generate_summary_single(self):
        row = self.source_table.currentRow()
        if row < 0:
            return
        src = self.session.sources[row]
        text = src.get('full_text') or src.get('abstract') or ""
        if not text:
            QMessageBox.warning(
                self, "No Text",
                "This source has no text to summarize.")
            return

        prompt_template = self.config.get_prompt('summarize_source')
        variables = {'source_text': text}
        dlg = PromptApprovalDialog(
            'summarize_source', prompt_template,
            variables, self.config, self)
        if dlg.exec():
            formatted = dlg.get_formatted_prompt()
            try:
                result = self.api.query(
                    formatted, max_tokens=2000, temperature=0.3)
                self.session.sources[row]['summary'] = result
                self.summary_edit.setPlainText(result)
                self._refresh_table()
                self.sources_changed.emit()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ── Screening ────────────────────────────────────────────────────

    def _screen_inclusion(self):
        criteria_text = self.criteria_edit.toPlainText().strip()
        self.session.inclusion_criteria = [
            c.strip() for c in criteria_text.split('\n') if c.strip()]

        has_criteria = bool(self.session.inclusion_criteria)
        prompt_key = ('screen_source_criteria' if has_criteria
                      else 'screen_source_subjective')
        prompt_template = self.config.get_prompt(prompt_key)

        sample_vars = {
            'topic': self.session.paper_topic,
            'source_text': '(source text)',
        }
        if has_criteria:
            sample_vars['criteria'] = '\n'.join(
                self.session.inclusion_criteria)

        dlg = PromptApprovalDialog(
            prompt_key, prompt_template, sample_vars, self.config, self)
        if not dlg.exec():
            return
        template = dlg.original_template

        for i, s in enumerate(self.session.sources):
            src = s if isinstance(s, dict) else s
            if src.get('rating') is not None:
                continue
            text = src.get('abstract') or src.get('title') or ""
            if not text:
                continue
            variables = {
                'topic': self.session.paper_topic,
                'source_text': text,
            }
            if has_criteria:
                variables['criteria'] = '\n'.join(
                    self.session.inclusion_criteria)
            formatted = template.format(**variables)
            try:
                import ast
                result = self.api.query(
                    formatted, max_tokens=200, temperature=0.3)
                parsed = aggro_parse_reason(result)
                self.session.sources[i]['rating'] = bool(parsed[0])
                self.session.sources[i]['rate_explain'] = str(parsed[1])
                self.status_label.setText(
                    f"Screened source {src.get('number', i)}: "
                    f"{'Include' if parsed[0] else 'Exclude'}")
                print(f'Screening source: {i}; Inclusion verdict: {bool(parsed[0])}')
            except Exception as e:
                print(f"Error in response: {e}")
                self.status_label.setText(
                    f"Error screening source {src.get('number', i)}: {e}")
                self.session.sources[i]['rate_explain'] = result

        self._refresh_table()
        self.sources_changed.emit()
        self.status_label.setText("Screening complete.")

    # ── Section rating ───────────────────────────────────────────────

    def _rate_for_sections(self):
        if not self.session.results:
            QMessageBox.warning(
                self, "No Results Sections",
                "Please generate results topics first in the Main tab.")
            return

        all_topics = [f"An introduction about {self.session.paper_topic}"]
        for rs in self.session.results:
            all_topics.append(rs.get('section', 'Untitled'))

        prompt_template = self.config.get_prompt('rate_source_sections')
        # Show prompt approval with a sample batch
        sample_batch = all_topics[:10]
        sample_vars = {
            'topics': str(sample_batch),
            'journal': '(journal)',
            'summary': '(summary)',
        }
        dlg = PromptApprovalDialog(
            'rate_source_sections', prompt_template,
            sample_vars, self.config, self)
        if not dlg.exec():
            return
        template = dlg.original_template

        # Batch the topics into chunks of 10
        BATCH_SIZE = 10
        batches = []
        for start in range(0, len(all_topics), BATCH_SIZE):
            batches.append(
                (start, all_topics[start:start + BATCH_SIZE]))

        for i, s in enumerate(self.session.sources):
            src = s if isinstance(s, dict) else s
            # Skip explicitly excluded sources
            if src.get('rating') is False:
                continue
            summary = src.get('summary')
            if not summary:
                continue

            # Collect ratings across all batches for this source
            all_ratings = []
            batch_failed = False

            for batch_start, batch_topics in batches:
                variables = {
                    'topics': str(batch_topics),
                    'journal': src.get('journal', 'Unknown'),
                    'summary': summary,
                }
                formatted = template.format(**variables)
                try:
                    import ast
                    result = self.api.query(formatted, max_tokens=200)
                    ratings = ast.literal_eval(result)
                    batch_ratings = [int(r) for r in ratings]
                    # Pad or truncate to match batch size
                    while len(batch_ratings) < len(batch_topics):
                        batch_ratings.append(5)
                    batch_ratings = batch_ratings[:len(batch_topics)]
                    all_ratings.extend(batch_ratings)
                except Exception as e:
                    self.status_label.setText(
                        f"Error rating source "
                        f"{src.get('number', i)} batch: {e}")
                    # Fill with neutral ratings so indices stay aligned
                    all_ratings.extend([5] * len(batch_topics))
                    batch_failed = True

            self.session.sources[i]['section_rate'] = all_ratings
            status = ("(partial)" if batch_failed else "")
            self.status_label.setText(
                f"Rated source {src.get('number', i)} "
                f"across {len(batches)} batch(es) {status}")

        self.sources_changed.emit()
        self.status_label.setText("Section rating complete.")

    # ── Citation linking ─────────────────────────────────────────────

    def show_sources_for_citations(self, numbers: list):
        for row in range(self.source_table.rowCount()):
            item = self.source_table.item(row, 0)
            if item and int(item.text()) in numbers:
                self.source_table.selectRow(row)
                self.source_table.scrollToItem(item)
                break

    def refresh_from_session(self):
        self._load_from_session()


def aggro_parse_reason(result):
    raw = result.strip()

    if raw.startswith("[True,"):
        flag = True
        reason = raw[len("[True,"):].strip().rstrip("]").strip().strip("'\"")
        parsed = [flag, reason]
    elif raw.startswith("[False,"):
        flag = False
        reason = raw[len("[False,"):].strip().rstrip("]").strip().strip("'\"")
        parsed = [flag, reason]
    else:
        raise ValueError(f"Unexpected AI response format: {raw}")
    return parsed
