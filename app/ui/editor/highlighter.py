"""LaTeX syntax highlighter for the code editor."""

from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression, QTimer

from core.themes import get_palette, qcolor


class LatexHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for LaTeX documents."""
    
    def __init__(self, document, theme: str = "dark"):
        super().__init__(document)
        self.theme = theme
        self._setup_formats()
        self._setup_rules()
    
    def _setup_formats(self) -> None:
        """Build text formats from the active palette."""
        p = get_palette(self.theme)

        # category: (colour, bold, italic, underline)
        specs = {
            'command': (p.syn_command, p.syn_command_bold, False, False),
            'environment': (p.syn_environment, p.syn_environment_bold, False, False),
            'math': (p.syn_math, False, False, False),
            'comment': (p.syn_comment, False, p.syn_comment_italic, False),
            'heading': (p.syn_heading, p.syn_heading_bold, False, False),
            'keyword': (p.syn_keyword, p.syn_keyword_bold, False, False),
            'brace': (p.syn_brace, False, False, False),
            'bracket': (p.syn_bracket, False, False, False),
            'text': (p.syn_text, False, False, False),
            'number': (p.syn_number, False, False, False),
            'string': (p.syn_string, False, False, False),
            'reference': (p.syn_reference, p.syn_reference_bold, False, False),
            'citation': (p.syn_citation, p.syn_citation_bold, False, False),
            'file': (p.syn_file, False, p.syn_file_italic, False),
            'url': (p.syn_url, False, False, p.syn_url_underline),
            'invalid': (p.syn_invalid, True, False, False),
        }
        self.formats = {
            name: self._format(qcolor(color), bold, italic, underline)
            for name, (color, bold, italic, underline) in specs.items()
        }
    
    def _format(self, color: QColor, bold: bool = False, italic: bool = False, 
                underline: bool = False) -> QTextCharFormat:
        """Create a text format."""
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        if underline:
            fmt.setFontUnderline(True)
        return fmt
    
    def _setup_rules(self) -> None:
        """Set up highlighting rules."""
        self.rules = []
        
        # Commands: \command or \command[opt]{arg}
        self.rules.append((
            QRegularExpression(r'\\(?:[a-zA-Z@]+|[^a-zA-Z@])'),
            self.formats['command']
        ))
        
        # Environments: \begin{env} ... \end{env}
        self.rules.append((
            QRegularExpression(r'\\begin\{([a-zA-Z*]+)\}'),
            self.formats['environment']
        ))
        self.rules.append((
            QRegularExpression(r'\\end\{([a-zA-Z*]+)\}'),
            self.formats['environment']
        ))
        
        # Math mode: $...$ or $$...$$ or \(...\) or \[...\]
        self.rules.append((
            QRegularExpression(r'\$\$.*?\$\$'),
            self.formats['math']
        ))
        self.rules.append((
            QRegularExpression(r'\$[^$\n]*\$'),
            self.formats['math']
        ))
        self.rules.append((
            QRegularExpression(r'\\\(.*?\\\)'),
            self.formats['math']
        ))
        self.rules.append((
            QRegularExpression(r'\\\[.*?\\\]'),
            self.formats['math']
        ))
        
        # Comments: %...
        self.rules.append((
            QRegularExpression(r'%.*$'),
            self.formats['comment']
        ))
        
        # Keywords: \documentclass, \usepackage, etc.
        keywords = [
            'documentclass', 'usepackage', 'begin', 'end', 'title', 'author', 'date',
            'maketitle', 'tableofcontents', 'section', 'subsection', 'subsubsection',
            'chapter', 'part', 'paragraph', 'subparagraph', 'label', 'ref', 'pageref',
            'cite', 'bibliography', 'bibliographystyle', 'include', 'input', 'includegraphics',
            'caption', 'centering', 'textbf', 'textit', 'texttt', 'emph', 'underline',
            'hline', 'cline', 'multicolumn', 'multirow', 'footnote', 'footnotemark',
            'footnotetext', 'newpage', 'clearpage', 'pagebreak', 'linebreak', 'vspace',
            'hspace', 'vfill', 'hfill', 'noindent', 'indent', 'par', 'mbox', 'fbox',
            'framebox', 'parbox', 'minipage', 'raisebox', 'rule', 'dotfill', 'hrulefill',
        ]
        keyword_pattern = r'\\(?:' + '|'.join(keywords) + r')\b'
        self.rules.append((
            QRegularExpression(keyword_pattern),
            self.formats['keyword']
        ))

        # Sectioning commands are headings, not ordinary keywords.  This rule
        # comes after the keyword rule so it wins where they overlap.
        headings = [
            'part', 'chapter', 'section', 'subsection', 'subsubsection',
            'paragraph', 'subparagraph',
        ]
        heading_pattern = r'\\(?:' + '|'.join(headings) + r')\b'
        self.rules.append((
            QRegularExpression(heading_pattern),
            self.formats['heading']
        ))
        
        # Braces and brackets
        self.rules.append((
            QRegularExpression(r'[\{\}]'),
            self.formats['brace']
        ))
        self.rules.append((
            QRegularExpression(r'[\[\]]'),
            self.formats['bracket']
        ))
        
        # Numbers
        self.rules.append((
            QRegularExpression(r'\b\d+(\.\d+)?(?:pt|cm|mm|in|ex|em|bp|dd|cc|sp|pc)?\b'),
            self.formats['number']
        ))
        
        # File paths in \includegraphics, \input, \include
        self.rules.append((
            QRegularExpression(r'\\(?:input|include|includegraphics(?:\[[^\]]*\])?)\{([^}]+)\}'),
            self.formats['file']
        ))
        
        # References and citations
        self.rules.append((
            QRegularExpression(r'\\(?:ref|pageref|nameref|autoref|cref)\{([^}]+)\}'),
            self.formats['reference']
        ))
        self.rules.append((
            QRegularExpression(r'\\(?:cite|parencite|footcite|textcite|nocite)\{([^}]+)\}'),
            self.formats['citation']
        ))
        
        # URLs
        self.rules.append((
            QRegularExpression(r'\\url\{([^}]+)\}'),
            self.formats['url']
        ))
        
        # Special characters
        self.rules.append((
            QRegularExpression(r'\\(?:#|\$|%|&|_|\{|\}|~)'),
            self.formats['command']
        ))
    
    def highlightBlock(self, text: str) -> None:
        """Apply highlighting to a block of text."""
        for pattern, fmt in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                start = match.capturedStart()
                length = match.capturedLength()
                if start >= 0 and length > 0:
                    self.setFormat(start, length, fmt)
        
        # Handle multi-line comments (not really applicable for LaTeX % comments)
        # But we could handle verbatim environments if needed
    
    def set_theme(self, theme: str) -> None:
        """Change the highlighting theme and recolour the open document."""
        self.theme = theme
        self._setup_formats()
        # Rules capture format objects, so they must be rebuilt too.
        self._setup_rules()
        # Defer rehighlighting until the event loop is idle; calling it while
        # stylesheets are being swapped caused reentrancy crashes previously.
        QTimer.singleShot(0, self.rehighlight)


class LatexCompleter:
    """Provides auto-completion for LaTeX commands."""
    
    COMMANDS = [
        # Document structure
        'documentclass', 'usepackage', 'begin', 'end',
        'title', 'author', 'date', 'maketitle',
        'tableofcontents', 'listoffigures', 'listoftables',
        'section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph',
        'chapter', 'part',
        'label', 'ref', 'pageref', 'nameref', 'autoref', 'cref',
        'cite', 'parencite', 'footcite', 'textcite', 'nocite',
        'bibliography', 'bibliographystyle',
        'include', 'input', 'includeonly',
        'newpage', 'clearpage', 'pagebreak', 'linebreak',
        'vspace', 'hspace', 'vfill', 'hfill',
        'noindent', 'indent', 'par',
        
        # Text formatting
        'textbf', 'textit', 'texttt', 'emph', 'underline',
        'uppercase', 'lowercase', 'textsc', 'textsf', 'mathtt',
        'footnote', 'footnotemark', 'footnotetext',
        
        # Math
        'frac', 'sqrt', 'sum', 'int', 'prod', 'lim', 'log', 'sin', 'cos', 'tan',
        'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta',
        'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi', 'omicron', 'pi', 'rho',
        'sigma', 'tau', 'upsilon', 'phi', 'chi', 'psi', 'omega',
        'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma', 'Upsilon',
        'Phi', 'Psi', 'Omega',
        'infty', 'partial', 'nabla', 'pm', 'mp', 'times', 'div', 'cdot',
        'leq', 'geq', 'neq', 'equiv', 'approx', 'sim', 'propto', 'in', 'notin',
        'subset', 'supset', 'subseteq', 'supseteq', 'cup', 'cap', 'setminus',
        'emptyset', 'forall', 'exists', 'nexists', 'implies', 'iff', 'neg',
        'land', 'lor', 'lnot', 'to', 'mapsto', 'leftarrow', 'rightarrow',
        'leftrightarrow', 'uparrow', 'downarrow', 'updownarrow',
        
        # Environments
        'document', 'abstract', 'itemize', 'enumerate', 'description',
        'figure', 'table', 'tabular', 'tabularx', 'longtable',
        'equation', 'align', 'align*', 'gather', 'multline', 'split',
        'theorem', 'lemma', 'corollary', 'proposition', 'definition', 'proof',
        'example', 'remark', 'note', 'warning',
        'verbatim', 'lstlisting', 'minted',
        'minipage', 'center', 'flushleft', 'flushright',
        'quote', 'quotation', 'verse',
        'itemize', 'enumerate', 'description',
        
        # Font sizes
        'tiny', 'scriptsize', 'footnotesize', 'small', 'normalsize',
        'large', 'Large', 'LARGE', 'huge', 'Huge',
        
        # Graphics
        'includegraphics', 'graphicspath', 'DeclareGraphicsExtensions',
        
        # Tables
        'hline', 'cline', 'multicolumn', 'multirow', 'vline',
        'toprule', 'midrule', 'bottomrule', 'cmidrule',
        
        # Cross-references
        'hyperref', 'href', 'url', 'nolinkurl',
        'autoref', 'cref', 'Cref', 'label', 'ref', 'pageref', 'nameref',
        
        # Counters
        'newcounter', 'setcounter', 'addtocounter', 'stepcounter', 'refstepcounter',
        'arabic', 'roman', 'Roman', 'alph', 'Alph',
        
        # Lengths
        'newlength', 'setlength', 'addtolength', 'settowidth', 'settoheight',
        'settodepth',
        
        # Boxes
        'mbox', 'fbox', 'framebox', 'parbox', 'makebox', 'raisebox',
        'rule', 'dotfill', 'hrulefill',
        
        # Colors
        'color', 'textcolor', 'definecolor', 'colorbox', 'fcolorbox',
        'pagecolor',
        
        # Misc
        'today', 'now', 'jobname', 'TeX', 'LaTeX', 'LaTeXe',
        'ldots', 'cdots', 'vdots', 'ddots', 'cdots', 'vdots',
        'quad', 'qquad', 'enskip', 'thinspace', 'negthinspace',
        'hskip', 'vskip', 'hfil', 'vfil', 'hfill', 'vfill',
        'null', 'relax', 'empty', 'ignorespaces', 'unskip',
    ]
    
    ENVIRONMENTS = [
        'document', 'abstract', 'itemize', 'enumerate', 'description',
        'figure', 'table', 'tabular', 'tabularx', 'longtable',
        'equation', 'align', 'align*', 'gather', 'multline', 'split',
        'theorem', 'lemma', 'corollary', 'proposition', 'definition', 'proof',
        'example', 'remark', 'note', 'warning',
        'verbatim', 'lstlisting', 'minted',
        'minipage', 'center', 'flushleft', 'flushright',
        'quote', 'quotation', 'verse',
        'itemize', 'enumerate', 'description',
        'picture', 'tikzpicture', 'pgfpicture',
        'alignat', 'xalignat', 'xxalignat',
        'flalign', 'eqnarray', 'eqnarray*',
        'subequations', 'cases', 'matrix', 'pmatrix', 'bmatrix',
        'Bmatrix', 'vmatrix', 'Vmatrix', 'smallmatrix',
        'array', 'tabbing',
    ]
    
    PACKAGES = [
        'amsmath', 'amssymb', 'amsthm', 'amsfonts', 'amscd', 'amstext',
        'graphicx', 'graphics', 'epsfig', 'epstopdf',
        'booktabs', 'longtable', 'tabularx', 'tabulary', 'multicol', 'multirow',
        'hyperref', 'url', 'href', 'bookmark',
        'geometry', 'fancyhdr', 'titlesec', 'titletoc', 'tocloft',
        'biblatex', 'natbib', 'cite', 'chapterbib',
        'algorithm', 'algorithmic', 'algpseudocode',
        'listings', 'minted', 'verbatim', 'moreverb',
        'tikz', 'pgf', 'pgfplots', 'tikz-3dplot',
        'siunitx', 'physics', 'mathtools', 'empheq', 'nccmath',
        'float', 'subcaption', 'subfig', 'caption',
        'enumitem', 'paralist', 'mdwlist',
        'footmisc', 'endnotes', 'pagenote',
        'appendix', 'chngcntr', 'remreset',
        'setspace', 'leading', 'linespread',
        'microtype', 'fontenc', 'inputenc', 'babel', 'polyglossia',
        'fontspec', 'unicode-math', 'xltxtra', 'xunicode',
        'csquotes', 'ellipsis', 'xspace', 'etoolbox', 'ifthen', 'xifthen',
        'calc', 'fp', 'pgfmath', 'expl3', 'l3keys2e',
        'tcolorbox', 'mdframed', 'framed', 'shaded',
        'wrapfig', 'picins', 'floatflt', 'sidecap',
        'rotating', 'lscape', 'pdflscape',
        'afterpage', 'everypage', 'atbegshi', 'atveryend',
        'zref', 'refcount', 'gettitlestring', 'nameref',
        'varioref', 'cleveref', 'autonum', 'autonum*',
    ]
    
    @classmethod
    def get_completions(cls, prefix: str) -> list:
        """Get completions for a given prefix."""
        prefix = prefix.lower()
        results = []
        
        for cmd in cls.COMMANDS:
            if cmd.startswith(prefix):
                results.append(f"\\{cmd}")
        
        for env in cls.ENVIRONMENTS:
            if env.startswith(prefix):
                results.append(f"\\begin{{{env}}}")
        
        for pkg in cls.PACKAGES:
            if pkg.startswith(prefix):
                results.append(f"\\usepackage{{{pkg}}}")
        
        return sorted(results)[:20]  # Limit results