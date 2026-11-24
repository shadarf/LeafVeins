"""Project management for LeafVeins."""

import os
import shutil
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from core.database import get_database
from core.config import get_config


@dataclass
class ProjectInfo:
    """Project metadata."""
    id: int = 0
    name: str = ""
    path: str = ""
    main_file: str = "main.tex"
    compiler: str = "pdflatex"
    created_at: str = ""
    updated_at: str = ""
    last_opened_at: str = ""
    is_favorite: bool = False
    settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.settings is None:
            self.settings = {}


class ProjectManager:
    """Manages LaTeX projects."""
    
    def __init__(self):
        self.db = get_database()
        self.config = get_config()
        self.current_project: Optional[ProjectInfo] = None
        self._project_cache: Dict[int, ProjectInfo] = {}
    
    def create_project(self, name: str, path: Path, 
                       template: str = "Article",
                       main_file: str = "main.tex",
                       compiler: str = "pdflatex") -> Optional[ProjectInfo]:
        """Create a new project from template."""
        path = Path(path).resolve()
        
        # Create directory
        path.mkdir(parents=True, exist_ok=True)
        
        # Get template
        template_data = self.db.get_template(template)
        if not template_data:
            template_data = self.db.get_template("Article")
        
        # Create files from template
        if template_data and 'files' in template_data:
            for file_info in template_data['files']:
                file_path = path / file_info['path']
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(file_info['content'])
        
        # Create project in database
        project_id = self.db.create_project(name, path, main_file, compiler)
        
        # Create .leafveins directory for project metadata
        meta_dir = path / '.leafveins'
        meta_dir.mkdir(exist_ok=True)
        
        config = {
            'name': name,
            'main_file': main_file,
            'compiler': compiler,
            'created_at': datetime.now().isoformat(),
        }
        with open(meta_dir / 'config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        # Return project info
        project = ProjectInfo(
            id=project_id,
            name=name,
            path=str(path),
            main_file=main_file,
            compiler=compiler,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        
        self._project_cache[project_id] = project
        return project
    
    def open_project(self, path: Path) -> Optional[ProjectInfo]:
        """Open an existing project."""
        path = Path(path).resolve()
        
        # Check database
        db_project = self.db.get_project_by_path(path)
        if db_project:
            project = self._db_to_project(db_project)
            self.current_project = project
            self.db.update_last_opened(project.id)
            return project
        
        # Try to read from .leafveins/config.json
        meta_file = path / '.leafveins' / 'config.json'
        if meta_file.exists():
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                name = meta.get('name', path.name)
                main_file = meta.get('main_file', 'main.tex')
                compiler = meta.get('compiler', 'pdflatex')
                
                project_id = self.db.create_project(name, path, main_file, compiler)
                
                project = ProjectInfo(
                    id=project_id,
                    name=name,
                    path=str(path),
                    main_file=main_file,
                    compiler=compiler,
                )
                
                self.current_project = project
                self.db.update_last_opened(project_id)
                return project
            except Exception:
                pass
        
        # Create new entry
        name = path.name
        project_id = self.db.create_project(name, path)
        
        project = ProjectInfo(
            id=project_id,
            name=name,
            path=str(path),
        )
        
        self.current_project = project
        self.db.update_last_opened(project_id)
        return project
    
    def close_project(self) -> None:
        """Close current project."""
        self.current_project = None
    
    def get_current_project(self) -> Optional[ProjectInfo]:
        """Get current project."""
        return self.current_project
    
    def list_projects(self) -> List[ProjectInfo]:
        """List all projects."""
        db_projects = self.db.list_projects()
        return [self._db_to_project(p) for p in db_projects]
    
    def list_recent_projects(self, limit: int = 10) -> List[ProjectInfo]:
        """List recent projects."""
        db_projects = self.db.list_projects()
        return [self._db_to_project(p) for p in db_projects[:limit]]
    
    def delete_project(self, project_id: int, delete_files: bool = False) -> bool:
        """Delete a project."""
        project = self.get_project(project_id)
        if not project:
            return False
        
        if delete_files:
            try:
                shutil.rmtree(project.path)
            except Exception:
                pass
        
        result = self.db.delete_project(project_id)
        if project_id in self._project_cache:
            del self._project_cache[project_id]
        
        if self.current_project and self.current_project.id == project_id:
            self.current_project = None
        
        return result
    
    def get_project(self, project_id: int) -> Optional[ProjectInfo]:
        """Get project by ID."""
        if project_id in self._project_cache:
            return self._project_cache[project_id]
        
        db_project = self.db.get_project(project_id)
        if db_project:
            project = self._db_to_project(db_project)
            self._project_cache[project_id] = project
            return project
        return None
    
    def update_project(self, project_id: int, **kwargs) -> bool:
        """Update project metadata."""
        result = self.db.update_project(project_id, **kwargs)
        
        if project_id in self._project_cache:
            project = self._project_cache[project_id]
            for key, value in kwargs.items():
                if hasattr(project, key):
                    setattr(project, key, value)
            project.updated_at = datetime.now().isoformat()
        
        return result
    
    def set_main_file(self, project_id: int, main_file: str) -> bool:
        """Set the main LaTeX file for a project."""
        result = self.db.update_project(project_id, main_file=main_file)
        
        if project_id in self._project_cache:
            self._project_cache[project_id].main_file = main_file
        
        # Update .leafveins/config.json
        project = self.get_project(project_id)
        if project:
            meta_file = Path(project.path) / '.leafveins' / 'config.json'
            if meta_file.exists():
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    meta['main_file'] = main_file
                    with open(meta_file, 'w', encoding='utf-8') as f:
                        json.dump(meta, f, indent=2)
                except Exception:
                    pass
        
        return result
    
    def set_compiler(self, project_id: int, compiler: str) -> bool:
        """Set the compiler for a project."""
        result = self.db.update_project(project_id, compiler=compiler)
        
        if project_id in self._project_cache:
            self._project_cache[project_id].compiler = compiler
        
        return result
    
    def toggle_favorite(self, project_id: int) -> bool:
        """Toggle project favorite status."""
        project = self.get_project(project_id)
        if not project:
            return False
        
        new_status = not project.is_favorite
        result = self.db.update_project(project_id, is_favorite=new_status)
        
        if project_id in self._project_cache:
            self._project_cache[project_id].is_favorite = new_status
        
        return result
    
    def get_project_files(self, project_id: int) -> List[Dict[str, Any]]:
        """Get list of files in a project."""
        project = self.get_project(project_id)
        if not project:
            return []
        
        path = Path(project.path)
        files = []
        
        for file_path in path.rglob('*'):
            if file_path.is_file() and not self._is_hidden(file_path):
                rel_path = file_path.relative_to(path)
                stat = file_path.stat()
                files.append({
                    'path': str(rel_path),
                    'absolute_path': str(file_path),
                    'name': file_path.name,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'is_main': str(rel_path) == project.main_file,
                })
        
        return sorted(files, key=lambda x: (not x['is_main'], x['path']))
    
    def _is_hidden(self, path: Path) -> bool:
        """Check if file should be hidden."""
        hidden_patterns = [
            '.leafveins', '.git', '__pycache__', '.vscode', '.idea',
            '*.aux', '*.log', '*.out', '*.toc', '*.lof', '*.lot',
            '*.bbl', '*.blg', '*.synctex.gz', '*.fls', '*.fdb_latexmk',
            '*.pdf', '*.dvi', '*.ps', '*.nav', '*.snm', '*.vrb',
        ]
        
        import fnmatch
        for pattern in hidden_patterns:
            if fnmatch.fnmatch(path.name.lower(), pattern.lower()):
                return True
            # Check parent directories
            for parent in path.parents:
                if fnmatch.fnmatch(parent.name.lower(), pattern.lower()):
                    return True
        return False
    
    def _db_to_project(self, db_project: Dict) -> ProjectInfo:
        """Convert database row to ProjectInfo."""
        settings = self.db.get_all_project_settings(db_project['id'])
        return ProjectInfo(
            id=db_project['id'],
            name=db_project['name'],
            path=db_project['path'],
            main_file=db_project['main_file'],
            compiler=db_project['compiler'],
            created_at=db_project['created_at'],
            updated_at=db_project['updated_at'],
            last_opened_at=db_project['last_opened_at'],
            is_favorite=bool(db_project['is_favorite']),
            settings=settings,
        )
    
    def get_templates(self) -> List[Dict]:
        """Get available project templates."""
        return self.db.get_templates()
    
    def get_compilation_history(self, project_id: int, limit: int = 50) -> List[Dict]:
        """Get compilation history for a project."""
        return self.db.get_compilation_history(project_id, limit)
    
    def add_compilation_record(self, project_id: int, compiler: str, status: str,
                               log: str, output_files: List[str], duration_ms: int) -> int:
        """Add a compilation record."""
        return self.db.add_compilation_record(project_id, compiler, status, log, output_files, duration_ms)
    
    def export_project(self, project_id: int, export_path: Path) -> bool:
        """Export project as zip archive."""
        import zipfile
        project = self.get_project(project_id)
        if not project:
            return False
        
        try:
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                project_path = Path(project.path)
                for file_path in project_path.rglob('*'):
                    if file_path.is_file() and not self._is_hidden(file_path):
                        arcname = file_path.relative_to(project_path)
                        zf.write(file_path, arcname)
            return True
        except Exception:
            return False
    
    def import_project(self, zip_path: Path, dest_dir: Path) -> Optional[ProjectInfo]:
        """Import project from zip archive."""
        import zipfile
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(dest_dir)
            
            # Try to open as project
            return self.open_project(dest_dir)
        except Exception:
            return None


# Global project manager instance
_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """Get global project manager instance."""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager