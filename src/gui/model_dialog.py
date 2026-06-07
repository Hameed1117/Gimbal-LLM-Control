"""Model Selection Dialog — provider picker + live OpenRouter model dropdown."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QListWidget, QPushButton, QLineEdit,
    QRadioButton, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt


class ModelDialog(QDialog):
    """Select LLM provider and model.

    OpenRouter section shows a ComboBox pre-populated with top-5 curated
    models; a Fetch button updates it live from the OpenRouter API.
    """

    def __init__(self, llm_service, parent=None):
        super().__init__(parent)
        self.llm_service = llm_service
        self.selected_model    = None
        self.selected_provider = "ollama"
        self.api_key           = ""

        self.setWindowTitle("Change LLM Model")
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #404040;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                background-color: #252525;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
            }
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover  { background-color: #4a4a4a; border-color: #2a82da; }
            QPushButton:pressed { background-color: #2a82da; }
            QLineEdit, QComboBox {
                background-color: #2a2a2a;
                border: 1px solid #505050;
                border-radius: 4px;
                padding: 5px 8px;
                color: #e0e0e0;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #2a82da; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                border: 1px solid #505050;
                selection-background-color: #2a82da;
            }
            QListWidget {
                background-color: #2a2a2a;
                border: 1px solid #505050;
                border-radius: 4px;
            }
            QListWidget::item:selected { background-color: #2a82da; }
            QRadioButton { padding: 4px; }
        """)

        self.setup_ui()
        self.refresh_ollama_models()
        self._populate_or_combo(llm_service.CURATED_MODELS)

    # ── UI construction ───────────────────────────────────────────────────────

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Provider ──────────────────────────────────────────────────────────
        provider_group  = QGroupBox("Provider")
        provider_layout = QHBoxLayout(provider_group)

        self.ollama_radio     = QRadioButton("Ollama (Local / Free)")
        self.openrouter_radio = QRadioButton("OpenRouter (Cloud API)")
        self.ollama_radio.setChecked(
            self.llm_service.config.llm_provider != "openrouter"
        )
        self.openrouter_radio.setChecked(
            self.llm_service.config.llm_provider == "openrouter"
        )
        self.ollama_radio.toggled.connect(self._on_provider_changed)
        provider_layout.addWidget(self.ollama_radio)
        provider_layout.addWidget(self.openrouter_radio)
        layout.addWidget(provider_group)

        # ── Ollama section ────────────────────────────────────────────────────
        self.ollama_section = QGroupBox("Ollama Models")
        ollama_layout       = QVBoxLayout(self.ollama_section)

        header = QHBoxLayout()
        header.addWidget(QLabel("Available on this machine:"))
        header.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMaximumWidth(80)
        refresh_btn.clicked.connect(self.refresh_ollama_models)
        header.addWidget(refresh_btn)
        ollama_layout.addLayout(header)

        self.model_list = QListWidget()
        self.model_list.setMaximumHeight(110)
        self.model_list.itemClicked.connect(self._on_ollama_item_clicked)
        ollama_layout.addWidget(self.model_list)

        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Model name:"))
        self.custom_model_input = QLineEdit()
        self.custom_model_input.setPlaceholderText("llama3.2:1b  mistral:7b  phi3:mini")
        self.custom_model_input.setText(self.llm_service.config.ollama_model)
        custom_row.addWidget(self.custom_model_input)
        ollama_layout.addLayout(custom_row)

        hint = QLabel("Pull new models: ollama pull <name>  |  List: ollama list")
        hint.setStyleSheet("color: #666; font-size: 10px;")
        ollama_layout.addWidget(hint)
        layout.addWidget(self.ollama_section)

        # ── OpenRouter section ────────────────────────────────────────────────
        self.or_section = QGroupBox("OpenRouter Configuration")
        or_layout       = QVBoxLayout(self.or_section)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("sk-or-v1-...")
        self.api_key_input.setText(self.llm_service.config.openrouter_api_key)
        key_row.addWidget(self.api_key_input)
        or_layout.addLayout(key_row)

        # Model ComboBox row
        model_header = QHBoxLayout()
        model_header.addWidget(QLabel("Model:"))
        model_header.addStretch()
        self.fetch_btn = QPushButton("Fetch from API")
        self.fetch_btn.setMaximumWidth(130)
        self.fetch_btn.setToolTip("Fetch top models live from OpenRouter API")
        self.fetch_btn.clicked.connect(self._on_fetch_models)
        model_header.addWidget(self.fetch_btn)
        or_layout.addLayout(model_header)

        self.or_model_combo = QComboBox()
        self.or_model_combo.setMinimumHeight(30)
        or_layout.addWidget(self.or_model_combo)

        or_info = QLabel(
            "Top 10 models shown (incl. Kimi K2, low-token options)  •  "
            "Click 'Fetch from API' to refresh\n"
            "Your key is read from the .env file — no need to re-enter it each time."
        )
        or_info.setStyleSheet("color: #666; font-size: 10px;")
        or_info.setWordWrap(True)
        or_layout.addWidget(or_info)
        layout.addWidget(self.or_section)

        # Initial section visibility
        self._on_provider_changed()

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(
            "background-color: #2a82da; color: white; font-weight: bold; padding: 6px 20px;"
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

    # ── Populate helpers ──────────────────────────────────────────────────────

    def refresh_ollama_models(self):
        self.model_list.clear()
        models = self.llm_service.get_available_ollama_models()
        if models:
            for m in models:
                self.model_list.addItem(m)
                if m == self.llm_service.config.ollama_model:
                    self.model_list.setCurrentRow(self.model_list.count() - 1)
        else:
            self.model_list.addItem("(No models found — is Ollama running?)")

    def _populate_or_combo(self, model_list: list):
        """Fill the OpenRouter ComboBox from a list of (display_name, model_id)."""
        self.or_model_combo.clear()
        current = self.llm_service.config.openrouter_model
        current_idx = 0
        for i, (display, model_id) in enumerate(model_list):
            self.or_model_combo.addItem(display, userData=model_id)
            if model_id == current:
                current_idx = i
        self.or_model_combo.setCurrentIndex(current_idx)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_ollama_item_clicked(self, item):
        text = item.text()
        if not text.startswith("("):
            self.custom_model_input.setText(text)

    def _on_provider_changed(self):
        is_ollama = self.ollama_radio.isChecked()
        self.ollama_section.setVisible(is_ollama)
        self.or_section.setVisible(not is_ollama)
        self.adjustSize()

    def _on_fetch_models(self):
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching…")

        # Temporarily apply API key from field so fetch uses it
        key = self.api_key_input.text().strip()
        if key:
            self.llm_service.config.openrouter_api_key = key

        # Run async fetch
        self._fetch_worker = self.llm_service.fetch_openrouter_models_async()
        self._fetch_worker.done.connect(self._on_fetch_done)
        self._fetch_worker.finished.connect(self._fetch_worker.deleteLater)
        self._fetch_worker.start()

    def _on_fetch_done(self, models: list):
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Fetch from API")
        self._populate_or_combo(models)

    def _on_apply(self):
        if self.ollama_radio.isChecked():
            model = self.custom_model_input.text().strip()
            if not model:
                items = self.model_list.selectedItems()
                if items and not items[0].text().startswith("("):
                    model = items[0].text()
            if not model:
                QMessageBox.warning(self, "No model selected",
                                    "Please enter or select a model name.")
                return
            self.selected_model    = model
            self.selected_provider = "ollama"
            self.api_key           = ""
        else:
            api_key  = self.api_key_input.text().strip()
            model_id = self.or_model_combo.currentData()
            if not model_id:
                model_id = self.or_model_combo.currentText().strip()
            if not api_key:
                QMessageBox.warning(self, "Missing API Key",
                                    "Please enter your OpenRouter API key.")
                return
            if not model_id:
                QMessageBox.warning(self, "No model selected",
                                    "Please select a model from the dropdown.")
                return
            self.selected_model    = model_id
            self.selected_provider = "openrouter"
            self.api_key           = api_key

        self.accept()

    def get_result(self):
        """Returns (model_name, provider, api_key) after accept()."""
        return self.selected_model, self.selected_provider, self.api_key
