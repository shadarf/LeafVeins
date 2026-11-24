"""SQLite database layer for LeafVeins."""

import sqlite3
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from contextlib import contextmanager

from .config import get_config


class Database:
    """SQLite database for storing project metadata, history, and settings."""
    
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            config = get_config()
            db_dir = config.config_dir
            db_path = db_dir / 'leafveins.db'
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            # Check current schema version
            cursor = conn.execute("PRAGMA user_version")
            current_version = cursor.fetchone()[0]
            
            if current_version < self.SCHEMA_VERSION:
                self._migrate(conn, current_version)
                conn.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
                conn.commit()
    
    def _migrate(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Run database migrations."""
        if from_version == 0:
            self._create_initial_schema(conn)
    
    def _create_initial_schema(self, conn: sqlite3.Connection) -> None:
        """Create initial database schema."""
        conn.executescript("""
            -- Projects table
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                main_file TEXT DEFAULT 'main.tex',
                compiler TEXT DEFAULT 'pdflatex',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_opened_at TIMESTAMP,
                is_favorite BOOLEAN DEFAULT 0
            );
            
            -- Project settings (key-value store per project)
            CREATE TABLE project_settings (
                project_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (project_id, key),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            
            -- Compilation history
            CREATE TABLE compilation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                compiler TEXT NOT NULL,
                status TEXT NOT NULL,  -- 'success', 'error', 'timeout'
                log TEXT,
                output_files TEXT,  -- JSON array of output files
                duration_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            
            -- Recent files
            CREATE TABLE recent_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                line_number INTEGER DEFAULT 1,
                column_number INTEGER DEFAULT 1,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            
            -- User preferences (global settings not in config.json)
            CREATE TABLE user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Templates
            CREATE TABLE templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                category TEXT DEFAULT 'document',
                files TEXT NOT NULL,  -- JSON array of {path, content}
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Indexes
            CREATE INDEX idx_projects_path ON projects(path);
            CREATE INDEX idx_projects_last_opened ON projects(last_opened_at DESC);
            CREATE INDEX idx_compilation_history_project ON compilation_history(project_id, created_at DESC);
            CREATE INDEX idx_recent_files_project ON recent_files(project_id, accessed_at DESC);
        """)
        
        # Insert default templates
        self._insert_default_templates(conn)
    
    def _insert_default_templates(self, conn: sqlite3.Connection) -> None:
        """Insert built-in project templates."""
        templates = [
            {
                'name': 'Article',
                'description': 'Standard LaTeX article',
                'category': 'document',
                'files': json.dumps([
                    {'path': 'main.tex', 'content': self._get_article_template()}
                ])
            },
            {
                'name': 'Report',
                'description': 'LaTeX report with chapters',
                'category': 'document',
                'files': json.dumps([
                    {'path': 'main.tex', 'content': self._get_report_template()}
                ])
            },
            {
                'name': 'Beamer Presentation',
                'description': 'LaTeX beamer slides',
                'category': 'presentation',
                'files': json.dumps([
                    {'path': 'main.tex', 'content': self._get_beamer_template()}
                ])
            },
            {
                'name': 'Thesis',
                'description': 'Thesis template with front matter',
                'category': 'document',
                'files': json.dumps([
                    {'path': 'main.tex', 'content': self._get_thesis_template()},
                    {'path': 'chapters/introduction.tex', 'content': '% Introduction\n\\chapter{Introduction}\n\nYour introduction here.\n'},
                    {'path': 'chapters/conclusion.tex', 'content': '% Conclusion\n\\chapter{Conclusion}\n\nYour conclusion here.\n'},
                    {'path': 'references.bib', 'content': '% Bibliography\n@article{example,\n  author = {Author, A.},\n  title = {Title},\n  journal = {Journal},\n  year = {2024}\n}\n'},
                ])
            },
            {
                'name': 'CV/Resume',
                'description': 'Modern CV template',
                'category': 'document',
                'files': json.dumps([
                    {'path': 'main.tex', 'content': self._get_cv_template()}
                ])
            },
        ]
        
        for tmpl in templates:
            conn.execute(
                """INSERT OR IGNORE INTO templates (name, description, category, files)
                   VALUES (?, ?, ?, ?)""",
                (tmpl['name'], tmpl['description'], tmpl['category'], tmpl['files'])
            )
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()
    
    # Project operations
    def create_project(self, name: str, path: Path, main_file: str = 'main.tex',
                       compiler: str = 'pdflatex') -> int:
        """Create a new project entry."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO projects (name, path, main_file, compiler, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, str(path), main_file, compiler, 
                 datetime.now().isoformat(), datetime.now().isoformat())
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_project(self, project_id: int) -> Optional[Dict]:
        """Get project by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return dict(row) if row else None
    
    def get_project_by_path(self, path: Path) -> Optional[Dict]:
        """Get project by path."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM projects WHERE path = ?", (str(path),)).fetchone()
            return dict(row) if row else None
    
    def list_projects(self, favorites_only: bool = False) -> List[Dict]:
        """List all projects, ordered by last opened."""
        with self._get_connection() as conn:
            query = "SELECT * FROM projects"
            if favorites_only:
                query += " WHERE is_favorite = 1"
            query += " ORDER BY last_opened_at DESC NULLS LAST, updated_at DESC"
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]
    
    def update_project(self, project_id: int, **kwargs) -> bool:
        """Update project fields."""
        allowed = {'name', 'main_file', 'compiler', 'is_favorite'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        
        fields['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join(f"{k} = ?" for k in fields)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE projects SET {set_clause} WHERE id = ?",
                (*fields.values(), project_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def update_last_opened(self, project_id: int) -> None:
        """Update project's last opened timestamp."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE projects SET last_opened_at = ? WHERE id = ?",
                (datetime.now().isoformat(), project_id)
            )
            conn.commit()
    
    def delete_project(self, project_id: int) -> bool:
        """Delete a project (cascades to settings and history)."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # Project settings
    def set_project_setting(self, project_id: int, key: str, value: Any) -> None:
        """Set a project setting."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO project_settings (project_id, key, value)
                   VALUES (?, ?, ?)""",
                (project_id, key, json.dumps(value) if not isinstance(value, str) else value)
            )
            conn.commit()
    
    def get_project_setting(self, project_id: int, key: str, default: Any = None) -> Any:
        """Get a project setting."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM project_settings WHERE project_id = ? AND key = ?",
                (project_id, key)
            ).fetchone()
            if row:
                try:
                    return json.loads(row['value'])
                except json.JSONDecodeError:
                    return row['value']
            return default
    
    def get_all_project_settings(self, project_id: int) -> Dict[str, Any]:
        """Get all settings for a project."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM project_settings WHERE project_id = ?",
                (project_id,)
            ).fetchall()
            result = {}
            for row in rows:
                try:
                    result[row['key']] = json.loads(row['value'])
                except json.JSONDecodeError:
                    result[row['key']] = row['value']
            return result
    
    # Compilation history
    def add_compilation_record(self, project_id: int, compiler: str, status: str,
                               log: str, output_files: List[str], duration_ms: int) -> int:
        """Add a compilation history record."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO compilation_history (project_id, compiler, status, log, output_files, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project_id, compiler, status, log, json.dumps(output_files), duration_ms)
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_compilation_history(self, project_id: int, limit: int = 50) -> List[Dict]:
        """Get compilation history for a project."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM compilation_history 
                   WHERE project_id = ? ORDER BY created_at DESC LIMIT ?""",
                (project_id, limit)
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                try:
                    d['output_files'] = json.loads(d['output_files'])
                except (json.JSONDecodeError, KeyError):
                    d['output_files'] = []
                result.append(d)
            return result
    
    def get_latest_compilation(self, project_id: int) -> Optional[Dict]:
        """Get the most recent compilation record."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM compilation_history 
                   WHERE project_id = ? ORDER BY created_at DESC LIMIT 1""",
                (project_id,)
            ).fetchone()
            if row:
                d = dict(row)
                try:
                    d['output_files'] = json.loads(d['output_files'])
                except (json.JSONDecodeError, KeyError):
                    d['output_files'] = []
                return d
            return None
    
    # Recent files
    def add_recent_file(self, project_id: int, file_path: str, 
                        line: int = 1, column: int = 1) -> None:
        """Add/update recent file entry."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO recent_files (project_id, file_path, line_number, column_number, accessed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (project_id, file_path, line, column, datetime.now().isoformat())
            )
            conn.commit()
    
    def get_recent_files(self, project_id: int, limit: int = 10) -> List[Dict]:
        """Get recent files for a project."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM recent_files 
                   WHERE project_id = ? ORDER BY accessed_at DESC LIMIT ?""",
                (project_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]
    
    # User preferences
    def set_preference(self, key: str, value: Any) -> None:
        """Set a user preference."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO user_preferences (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                (key, json.dumps(value) if not isinstance(value, str) else value,
                 datetime.now().isoformat())
            )
            conn.commit()
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM user_preferences WHERE key = ?", (key,)
            ).fetchone()
            if row:
                try:
                    return json.loads(row['value'])
                except json.JSONDecodeError:
                    return row['value']
            return default
    
    # Templates
    def get_templates(self, category: Optional[str] = None) -> List[Dict]:
        """Get available templates."""
        with self._get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM templates WHERE category = ? ORDER BY name",
                    (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM templates ORDER BY category, name"
                ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                try:
                    d['files'] = json.loads(d['files'])
                except json.JSONDecodeError:
                    d['files'] = []
                result.append(d)
            return result
    
    def get_template(self, name: str) -> Optional[Dict]:
        """Get template by name."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM templates WHERE name = ?", (name,)).fetchone()
            if row:
                d = dict(row)
                try:
                    d['files'] = json.loads(d['files'])
                except json.JSONDecodeError:
                    d['files'] = []
                return d
            return None
    
    # Template content
    def _get_article_template(self) -> str:
        return r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}

\title{Your Title Here}
\author{Your Name}
\date{\today}

\begin{document}

\maketitle

\begin{abstract}
Your abstract here.
\end{abstract}

\section{Introduction}
Your introduction here.

\section{Main Content}
Your content here.

\subsection{Subsection}
More content.

\section{Conclusion}
Your conclusion here.

\bibliographystyle{plain}
\bibliography{references}

\end{document}
"""
    
    def _get_report_template(self) -> str:
        return r"""\documentclass[11pt,a4paper]{report}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}

\title{Your Report Title}
\author{Your Name}
\date{\today}

\begin{document}

\maketitle

\tableofcontents
\clearpage

\chapter{Introduction}
Your introduction here.

\chapter{Background}
Background information.

\chapter{Methodology}
Your methodology.

\chapter{Results}
Your results.

\chapter{Discussion}
Discussion of results.

\chapter{Conclusion}
Your conclusion.

\bibliographystyle{plain}
\bibliography{references}

\end{document}
"""
    
    def _get_beamer_template(self) -> str:
        return r"""\documentclass[11pt,aspectratio=169]{beamer}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}

\usetheme{Madrid}
\usecolortheme{default}

\title{Presentation Title}
\subtitle{Subtitle}
\author{Your Name}
\institute{Your Institution}
\date{\today}

\begin{document}

\frame{\titlepage}

\begin{frame}{Outline}
\tableofcontents
\end{frame}

\section{Introduction}
\begin{frame}{Introduction}
\begin{itemize}
    \item Point 1
    \item Point 2
    \item Point 3
\end{itemize}
\end{frame}

\section{Main Content}
\begin{frame}{Slide Title}
Content here.
\end{frame}

\begin{frame}{Another Slide}
More content.
\end{frame}

\section{Conclusion}
\begin{frame}{Conclusion}
\begin{itemize}
    \item Summary point 1
    \item Summary point 2
\end{itemize}
\end{frame}

\begin{frame}{Thank You}
\centering
\Large Thank you for your attention!
\end{frame}

\end{document}
"""
    
    def _get_thesis_template(self) -> str:
        return r"""\documentclass[11pt,a4paper,oneside]{book}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{tocloft}

\title{Thesis Title}
\author{Your Name}
\date{\today}

\begin{document}

\frontmatter
\maketitle

\begin{abstract}
Your abstract here.
\end{abstract}

\tableofcontents
\listoffigures
\listoftables

\mainmatter
\include{chapters/introduction}
\include{chapters/background}
\include{chapters/methodology}
\include{chapters/results}
\include{chapters/discussion}
\include{chapters/conclusion}

\backmatter
\bibliographystyle{plain}
\bibliography{references}

\end{document}
"""
    
    def _get_cv_template(self) -> str:
        return r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=0.75in]{geometry}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{titlesec}

\pagestyle{empty}
\setlist{nosep}

\titleformat{\section}{\large\bfseries\uppercase}{}{0em}{}[\titlerule]
\titlespacing{\section}{0pt}{12pt}{6pt}

\begin{document}

\begin{center}
    {\LARGE \textbf{Your Name}} \\[4pt]
    \href{mailto:email@example.com}{email@example.com} $|$
    \href{tel:+1234567890}{+1 234 567 890} $|$
    \href{https://linkedin.com/in/yourprofile}{LinkedIn} $|$
    \href{https://github.com/yourprofile}{GitHub}
\end{center}

\section{Summary}
Your professional summary here. Keep it concise and impactful.

\section{Experience}
\textbf{Job Title} \hfill \textit{Company Name} \hfill \textit{Date Range} \\
Location \\
\begin{itemize}
    \item Achievement 1 with metrics
    \item Achievement 2 with metrics
    \item Achievement 3 with metrics
\end{itemize}

\textbf{Previous Job Title} \hfill \textit{Previous Company} \hfill \textit{Date Range} \\
Location \\
\begin{itemize}
    \item Achievement 1
    \item Achievement 2
\end{itemize}

\section{Education}
\textbf{Degree} \hfill \textit{University Name} \hfill \textit{Graduation Year} \\
Field of Study

\section{Skills}
\textbf{Technical:} Skill 1, Skill 2, Skill 3 \\
\textbf{Languages:} Language 1, Language 2 \\
\textbf{Tools:} Tool 1, Tool 2, Tool 3

\section{Projects}
\textbf{Project Name} \hfill \textit{Technologies} \\
Description of project and your role.

\end{document}
"""


# Global database instance
_database: Optional[Database] = None


def get_database(db_path: Optional[Path] = None) -> Database:
    """Get global database instance."""
    global _database
    if _database is None:
        _database = Database(db_path)
    return _database