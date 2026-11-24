"""Searchable LaTeX symbol picker dialog."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QPushButton, QLabel
)
from PyQt6.QtCore import Qt


SYMBOLS = [
    ("α", "\\alpha"), ("β", "\\beta"), ("γ", "\\gamma"), ("δ", "\\delta"),
    ("ε", "\\epsilon"), ("ζ", "\\zeta"), ("η", "\\eta"), ("θ", "\\theta"),
    ("ι", "\\iota"), ("κ", "\\kappa"), ("λ", "\\lambda"), ("μ", "\\mu"),
    ("ν", "\\nu"), ("ξ", "\\xi"), ("π", "\\pi"), ("ρ", "\\rho"),
    ("σ", "\\sigma"), ("τ", "\\tau"), ("υ", "\\upsilon"), ("φ", "\\phi"),
    ("χ", "\\chi"), ("ψ", "\\psi"), ("ω", "\\omega"),
    ("Γ", "\\Gamma"), ("Δ", "\\Delta"), ("Θ", "\\Theta"), ("Λ", "\\Lambda"),
    ("Ξ", "\\Xi"), ("Π", "\\Pi"), ("Σ", "\\Sigma"), ("Φ", "\\Phi"),
    ("Ψ", "\\Psi"), ("Ω", "\\Omega"),
    ("×", "\\times"), ("÷", "\\div"), ("±", "\\pm"), ("∓", "\\mp"),
    ("≤", "\\leq"), ("≥", "\\geq"), ("≠", "\\neq"), ("≈", "\\approx"),
    ("≡", "\\equiv"), ("∞", "\\infty"), ("∂", "\\partial"), ("∇", "\\nabla"),
    ("∑", "\\sum"), ("∏", "\\prod"), ("∫", "\\int"), ("√", "\\sqrt{}"),
    ("∈", "\\in"), ("∉", "\\notin"), ("⊂", "\\subset"), ("⊆", "\\subseteq"),
    ("∪", "\\cup"), ("∩", "\\cap"), ("∅", "\\emptyset"), ("∀", "\\forall"),
    ("∃", "\\exists"), ("¬", "\\neg"), ("∧", "\\wedge"), ("∨", "\\vee"),
    ("→", "\\rightarrow"), ("←", "\\leftarrow"), ("↔", "\\leftrightarrow"),
    ("⇒", "\\Rightarrow"), ("⇐", "\\Leftarrow"), ("⇔", "\\Leftrightarrow"),
    ("↑", "\\uparrow"), ("↓", "\\downarrow"),
    ("{", "\\{"), ("}", "\\}"), ("%", "\\%"), ("&", "\\&"), ("_", "\\_"),
    ("é", "\\'e"), ("è", "\\`e"), ("ê", "\\^e"), ("ë", "\\\"e"),
]


class SymbolPickerDialog(QDialog):
    """Dialog for picking a LaTeX command from a searchable symbol list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert Symbol")
        self.setMinimumSize(420, 360)
        self.selected_command = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Search symbols or LaTeX commands:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("e.g. alpha, \\alpha, Ω")
        self.search_edit.textChanged.connect(self._filter_symbols)
        layout.addWidget(self.search_edit)

        self.symbol_list = QListWidget()
        self.symbol_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.symbol_list)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.insert_btn = QPushButton("Insert")
        self.insert_btn.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.insert_btn)
        layout.addLayout(buttons)

        self._populate(SYMBOLS)
        self.search_edit.setFocus()

    def _populate(self, symbols) -> None:
        self.symbol_list.clear()
        for glyph, command in symbols:
            self.symbol_list.addItem(f"{glyph}    {command}")

    def _filter_symbols(self, text: str) -> None:
        needle = text.strip().lower()
        if not needle:
            self._populate(SYMBOLS)
            return
        matches = [
            (glyph, command) for glyph, command in SYMBOLS
            if needle in glyph.lower() or needle in command.lower()
        ]
        self._populate(matches)

    def accept(self) -> None:
        item = self.symbol_list.currentItem()
        if item:
            # The command is always the second whitespace-separated field.
            self.selected_command = item.text().split()[-1]
        super().accept()

    @classmethod
    def pick(cls, parent=None) -> str:
        """Open the dialog and return the selected command, or an empty string."""
        dialog = cls(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_command or ""
        return ""
