"""LaTeX compilation manager - based on Overleaf CLSI service mechanics.

Reference: ayakaleaf-pro-server-pro/services/clsi/app/js/
  - CompileManager.js
  - LatexRunner.js
  - LocalCommandRunner.js
  - OutputFileFinder.js
  - Errors.js
  - config/settings.defaults.cjs
"""

import subprocess
import os
import time
import shutil
import re
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Callable, Set
from dataclasses import dataclass, field
from enum import Enum

from PyQt6.QtCore import QThread, pyqtSignal, QObject


class CompilationStatus(Enum):
    """Compilation status codes matching CLSI service."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    VALIDATION_PASS = "validation-pass"
    VALIDATION_FAIL = "validation-fail"
    STOPPED_ON_FIRST_ERROR = "stopped-on-first-error"
    COMPILE_IN_PROGRESS = "compile-in-progress"
    CONFLICT = "conflict"
    MISSING_UPDATES = "missing-updates"
    UNAVAILABLE = "unavailable"


# LaTeX compiler to latexmk flag mapping (from LatexRunner.js:19-24)
COMPILER_FLAGS = {
    'latex': '-pdfdvi',
    'pdflatex': '-pdf',
    'xelatex': '-xelatex',
    'lualatex': '-lualatex',
}

# Rules that count as LaTeX passes (from CompileManager.js:47)
LATEX_PASSES_RULES = {'latex', 'lualatex', 'xelatex', 'pdflatex'}

# Known latexmk rules for metrics (from CompileManager.js:35-45)
KNOWN_LATEXMK_RULES = {
    'biber', 'bibtex', 'dvipdf', 'latex', 'lualatex',
    'makeindex', 'pdflatex', 'xdvipdfmx', 'xelatex'
}


@dataclass
class CompilationResult:
    """Result of a compilation run."""
    status: CompilationStatus
    log: str
    output_files: List[str]
    duration_ms: int
    error_message: str = ""
    stats: Dict = field(default_factory=dict)
    timings: Dict = field(default_factory=dict)
    build_id: str = ""
    base_history_version: Optional[int] = None


@dataclass
class CompileMetrics:
    """Metrics collected during compilation (from CompileManager.js:_emitMetrics)."""
    latex_runs: int = 0
    latex_runs_with_errors: int = 0
    latexmk_errors: int = 0
    passes: int = 0
    rule_times: Dict[str, float] = field(default_factory=dict)
    image_times: Dict[str, float] = field(default_factory=dict)
    sync_duration_ms: int = 0
    compile_duration_ms: int = 0
    output_duration_ms: int = 0
    e2e_duration_ms: int = 0


class CompilationError(Exception):
    """Base compilation error with CLSI-compatible attributes."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message)
        self.message = message
        for k, v in kwargs.items():
            setattr(self, k, v)


class AlreadyCompilingError(CompilationError):
    """Compilation already in progress (HTTP 423)."""
    def __init__(self, message="Already compiling"):
        super().__init__(message, code=423, status="compile-in-progress")


class FilesOutOfSyncError(CompilationError):
    """Project files out of sync (HTTP 409)."""
    def __init__(self, message="Files out of sync, please retry"):
        super().__init__(message, code=409, status="conflict")


class MissingUpdatesError(CompilationError):
    """Missing updates from history (HTTP 409)."""
    def __init__(self, message="Missing updates", base_history_version=None):
        super().__init__(message, code=409, status="missing-updates", base_history_version=base_history_version)


class TooManyCompileRequestsError(CompilationError):
    """Too many concurrent requests (HTTP 503)."""
    def __init__(self, message="Too many concurrent requests"):
        super().__init__(message, code=503, status="unavailable")


class TimedOutError(CompilationError):
    """Compilation timed out."""
    def __init__(self, message="Compilation timed out"):
        super().__init__(message, timedout=True, status="timedout")


class ValidationError(CompilationError):
    """Validation-only request result."""
    def __init__(self, validate: str, original_error: Optional[Exception] = None):
        super().__init__("validation", validate=validate)
        self.validate = validate
        if original_error:
            self.original_error = original_error


class NotFoundError(CompilationError):
    """Output directory/file not found (HTTP 404)."""
    def __init__(self, message="Not found"):
        super().__init__(message, code=404)


class InvalidParameterError(CompilationError):
    """Invalid request parameter (HTTP 400)."""
    def __init__(self, message="Invalid parameter"):
        super().__init__(message, code=400)


# Default settings from settings.defaults.cjs
DEFAULT_COMPILE_TIMEOUT_MS = 60000  # 60 seconds (LatexRunner.js:39)
DEFAULT_SYNCTEX_TIMEOUT_MS = 60000  # 60 seconds (CompileManager.js:599)
DEFAULT_WORDCOUNT_TIMEOUT_MS = 60000  # 60 seconds (CompileManager.js:715)
DEFAULT_COMPILE_SIZE_LIMIT = "7mb"  # settings.defaults.cjs:9
MAX_FDB_FILE_SIZE = 1024 * 1024  # 1 MB (CompileManager.js:398)
PROCESS_LIFESPAN_LIMIT_MS = 2 * 24 * 60 * 60 * 1000  # 2 days (settings.defaults.cjs:11-12)
EXPIRE_PROJECT_AFTER_IDLE_MS = 24 * 60 * 60 * 1000  # 24 hours (settings.defaults.cjs:157)
CHECK_PROJECTS_INTERVAL_MS = 10 * 60 * 1000  # 10 minutes (settings.defaults.cjs:158)

# SyncTeX patterns (from CompileManager.js:508-521, 536-541)
SYNCTEX_VIEW_CMD = ['synctex', 'view', '-i', '{line}:{col}:{input}', '-o', '{output}']
SYNCTEX_EDIT_CMD = ['synctex', 'edit', '-o', '{page}:{h}:{v}:{output}']

# Wordcount command (from CompileManager.js:713)
WORDCOUNT_CMD = ['texcount', '-nocol', '-inc', '{file}']


class CompilerWorker(QThread):
    """Worker thread for running LaTeX compilation via latexmk."""
    
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # CompilationResult
    
    def __init__(self, compiler_manager, project_dir: Path, main_file: str,
                 compiler: str, options: Dict):
        super().__init__()
        self.compiler_manager = compiler_manager
        self.project_dir = project_dir
        self.main_file = main_file
        self.compiler = compiler
        self.options = options
        self._cancelled = False
        self._lock = threading.Lock()
    
    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
    
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled
    
    def run(self) -> None:
        start_time = time.time()
        
        try:
            result = self.compiler_manager._run_compilation(
                self.project_dir, self.main_file, self.compiler, self.options,
                self._emit_progress, self.is_cancelled
            )
            result.duration_ms = int((time.time() - start_time) * 1000)
            self.finished.emit(result)
        except Exception as e:
            result = CompilationResult(
                status=CompilationStatus.ERROR,
                log=str(e),
                output_files=[],
                duration_ms=int((time.time() - start_time) * 1000),
                error_message=str(e)
            )
            self.finished.emit(result)
    
    def _emit_progress(self, line: str) -> None:
        self.progress.emit(line)


class CompilerManager(QObject):
    """Manages LaTeX compilation process using latexmk (matching CLSI service)."""
    
    compilation_started = pyqtSignal()
    compilation_finished = pyqtSignal(object)  # CompilationResult
    compilation_progress = pyqtSignal(str)
    
    def __init__(self, config=None):
        super().__init__()
        self.config = config
        self.worker = None
        self._cancelled = False
        self._compile_locks: Dict[str, threading.Lock] = {}
        self._running_compiles: Dict[str, subprocess.Popen] = {}
    
    def compile(self, project_dir: Path, main_file: str, compiler: str,
                options: Dict = None, callback: Callable = None) -> None:
        """Start compilation in background thread."""
        if self.worker and self.worker.isRunning():
            # Match CLSI: return 423 Locked (AlreadyCompilingError)
            result = CompilationResult(
                status=CompilationStatus.COMPILE_IN_PROGRESS,
                log="Compilation already in progress",
                output_files=[],
                duration_ms=0,
                error_message="Already compiling"
            )
            if callback:
                callback(result)
            return
        
        if options is None:
            options = {}
        
        self.compilation_started.emit()
        
        self.worker = CompilerWorker(self, project_dir, main_file, compiler, options)
        self.worker.progress.connect(self.compilation_progress.emit)
        self.worker.finished.connect(self._on_compilation_finished)
        if callback:
            self.worker.finished.connect(callback)
        self.worker.start()
    
    def cancel(self) -> None:
        """Cancel current compilation (matching CLSI stopCompile)."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self._cancelled = True
            # Also kill any running subprocess
            self._kill_running_processes()
    
    def _kill_running_processes(self) -> None:
        """Kill all running compilation processes."""
        for proc in self._running_compiles.values():
            try:
                proc.terminate()
                time.sleep(0.1)
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        self._running_compiles.clear()
    
    def _get_compile_lock(self, project_dir: Path, user_id: Optional[str] = None) -> threading.Lock:
        """Get or create a lock for a project (matching LockManager)."""
        compile_name = f"{project_dir.name}-{user_id}" if user_id else project_dir.name
        if compile_name not in self._compile_locks:
            self._compile_locks[compile_name] = threading.Lock()
        return self._compile_locks[compile_name]
    
    def _on_compilation_finished(self, result: CompilationResult) -> None:
        self.compilation_finished.emit(result)
        self.worker = None
        self._cancelled = False
    
    def _run_compilation(self, project_dir: Path, main_file: str, compiler: str,
                         options: Dict, progress_callback: Callable,
                         cancelled_check: Callable) -> CompilationResult:
        """Run the actual compilation process using latexmk."""
        
        # Verify latexmk is available
        latexmk_cmd = shutil.which('latexmk')
        if not latexmk_cmd:
            return CompilationResult(
                status=CompilationStatus.ERROR,
                log="latexmk not found in PATH",
                output_files=[],
                duration_ms=0,
                error_message="latexmk not found. Install TeX Live or MiKTeX."
            )
        
        # Get compiler-specific flag
        compiler_flag = COMPILER_FLAGS.get(compiler)
        if not compiler_flag:
            return CompilationResult(
                status=CompilationStatus.ERROR,
                log=f"Unknown compiler: {compiler}",
                output_files=[],
                duration_ms=0,
                error_message=f"Unknown compiler: {compiler}"
            )
        
        # Build output directory
        output_dir = options.get('output_dir', 'build')
        output_path = project_dir / output_dir
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Track if this is initial compile (matching CompileManager.js:67-68)
        is_initial_compile = not output_path.exists()
        
        # Acquire lock (matching CompileManager.js:70)
        compile_lock = self._get_compile_lock(project_dir, options.get('user_id'))
        acquired = compile_lock.acquire(blocking=False)
        if not acquired:
            raise AlreadyCompilingError()
        
        try:
            return self._do_compile(
                project_dir, main_file, compiler, compiler_flag, output_dir,
                options, progress_callback, cancelled_check, is_initial_compile
            )
        finally:
            compile_lock.release()
    
    def _do_compile(self, project_dir: Path, main_file: str, compiler: str,
                    compiler_flag: str, output_dir: str, options: Dict,
                    progress_callback: Callable, cancelled_check: Callable,
                    is_initial_compile: bool) -> CompilationResult:
        """Execute the compilation (matching CompileManager.js:doCompile)."""
        
        e2e_start = time.time()
        stats = {}
        timings = {}
        
        # Record compile type for metrics
        if is_initial_compile:
            stats['isInitialCompile'] = 1
            options['metrics_compile'] = 'initial'
        else:
            options['metrics_compile'] = 'recompile'
        
        # Sync resources (write project files) - matching CompileManager.js:104-161
        sync_start = time.time()
        progress_callback("Syncing resources to disk...\n")
        
        # In standalone mode, files are already on disk
        # Just verify main file exists
        main_path = project_dir / main_file
        if not main_path.exists():
            raise FileNotFoundError(f"Main file not found: {main_file}")
        
        timings['sync'] = int((time.time() - sync_start) * 1000)
        
        # Set up environment (matching CompileManager.js:173-196)
        env = os.environ.copy()
        env['OVERLEAF_PROJECT_ID'] = str(project_dir.name)
        
        if self.config:
            texlive_openout = self.config.get('texlive.openout_any')
            if texlive_openout:
                env['openout_any'] = texlive_openout
            
            texlive_max_print = self.config.get('texlive.max_print_line')
            if texlive_max_print:
                env['max_print_line'] = str(texlive_max_print)
        
        # chktex options for LaTeX files (CompileManager.js:186-196)
        is_latex_file = main_file.lower().endswith('.tex')
        if options.get('check') and is_latex_file:
            env['CHKTEX_OPTIONS'] = '-nall -e9 -e10 -w15 -w16'
            env['CHKTEX_ULIMIT_OPTIONS'] = '-t 5 -v 64000'
            if options['check'] == 'error':
                env['CHKTEX_EXIT_ON_ERROR'] = '1'
            if options['check'] == 'validate':
                env['CHKTEX_VALIDATE'] = '1'
        
        # Handle image variants (CompileManager.js:_getImageVariantSettings:851-875)
        image_name = options.get('image')
        if options.get('enable_checkpoint'):
            checkpoint_image = f"{image_name}.checkpointing" if image_name else None
            # In standalone, we don't have image allowlist, so just note it
            if checkpoint_image:
                env['ENABLE_CHECKPOINT'] = '1'
        
        # Build latexmk command (matching LatexRunner.js:_buildLatexCommand:164-214)
        command = self._build_latexmk_command(
            main_file, compiler, compiler_flag, output_dir, options
        )
        
        compile_start = time.time()
        project_id = project_dir.name
        
        # Run latexmk (matching LatexRunner.js:runLatex:26-118)
        try:
            result = self._run_latexmk(
                project_id, command, project_dir, env,
                options.get('timeout', DEFAULT_COMPILE_TIMEOUT_MS / 1000),
                options.get('compile_group', 'compile'),
                stats, timings, progress_callback, cancelled_check
            )
            
            # Handle validation-only requests (CompileManager.js:235-252)
            if options.get('check') == 'validate':
                if result.status == CompilationStatus.SUCCESS:
                    raise ValidationError('pass')
                else:
                    raise ValidationError('fail', original_error=Exception(result.error_message))
            
            if options.get('check') == 'error' and result.status == CompilationStatus.ERROR:
                raise ValidationError('fail')
            
        except ValidationError as ve:
            # Validation request completed
            output_files = self._collect_output_files(project_dir, main_file, output_dir)
            ve.output_files = output_files
            raise
        except Exception as e:
            # Compilation error - collect output files for debugging
            output_files = self._collect_output_files(project_dir, main_file, output_dir)
            compile_duration = int((time.time() - compile_start) * 1000)
            timings['compile'] = compile_duration
            
            # Determine status
            if isinstance(e, TimedOutError) or getattr(e, 'timedout', False):
                status = CompilationStatus.TIMEOUT
            elif getattr(e, 'terminated', False):
                status = CompilationStatus.CANCELLED
            else:
                status = CompilationStatus.ERROR
            
            # Emit metrics for failure (CompileManager.js:272-280)
            self._emit_metrics(options, status, stats, timings)
            
            # Clear project if terminated/timed out (CompileManager.js:263-270)
            if getattr(e, 'terminated', False) or getattr(e, 'timedout', False):
                self._clear_project(project_dir)
            
            raise CompilationError(
                str(e),
                status=status,
                output_files=output_files,
                timings=timings,
                stats=stats
            )
        
        timings['compile'] = int((time.time() - compile_start) * 1000)
        
        # Save output files (CompileManager.js:315-321)
        save_start = time.time()
        output_files = self._collect_output_files(project_dir, main_file, output_dir)
        timings['output'] = int((time.time() - save_start) * 1000)
        
        timings['compileE2E'] = int((time.time() - e2e_start) * 1000)
        
        # Determine final status (CompileController.js:120-135)
        has_pdf = any(f.endswith('.pdf') and os.path.getsize(f) > 0 for f in output_files)
        
        if has_pdf:
            status = CompilationStatus.SUCCESS
        elif options.get('stop_on_first_error', False):
            status = CompilationStatus.STOPPED_ON_FIRST_ERROR
        else:
            status = CompilationStatus.ERROR
            progress_callback("Project failed to compile successfully, no output.pdf generated\n")
        
        # Emit success metrics
        self._emit_metrics(options, status, stats, timings)
        
        # Record performance for sampled requests (CompileManager.js:332-366)
        self._record_performance_metrics(project_dir, options, stats, timings)
        
        return CompilationResult(
            status=status,
            log="\n".join(stats.get('log_lines', [])),
            output_files=output_files,
            duration_ms=timings.get('compileE2E', 0),
            stats=stats,
            timings=timings
        )
    
    def _build_latexmk_command(self, main_file: str, compiler: str,
                               compiler_flag: str, output_dir: str,
                               options: Dict) -> List[str]:
        """Build latexmk command array (matching LatexRunner.js:_buildLatexCommand)."""
        command = ['latexmk']
        
        # Basic flags (LatexRunner.js:176-185)
        command.extend([
            '-cd',                          # Change to main file directory
            '-jobname=output',              # Output basename
            f'-auxdir={output_dir}',        # Auxiliary files directory
            f'-outdir={output_dir}',        # Output files directory
            '-synctex=1',                   # Generate SyncTeX data
            '-interaction=batchmode',       # Non-interactive
            '-time',                        # Show time statistics
        ])
        
        # Stop on first error (LatexRunner.js:187-193)
        if options.get('stop_on_first_error', False):
            command.append('-halt-on-error')
        else:
            command.append('-f')  # Force continue on error
        
        # Extra flags from request (LatexRunner.js:196-198)
        if options.get('flags'):
            command.extend(options['flags'])
        
        # Compiler flag (LatexRunner.js:200-206)
        command.append(compiler_flag)
        
        # Main file (LatexRunner.js:208-211)
        # Convert Rtex/Rmd/md to .tex for latexmk
        main_file_for_latexmk = re.sub(r'\.(Rtex|md|Rmd|Rnw)$', '.tex', main_file)
        command.append(main_file_for_latexmk)
        
        return command
    
    def _run_latexmk(self, project_id: str, command: List[str], cwd: Path,
                     env: Dict, timeout: int, compile_group: str,
                     stats: Dict, timings: Dict,
                     progress_callback: Callable, cancelled_check: Callable) -> CompilationResult:
        """Run latexmk process and collect output (matching LatexRunner.js:68-117)."""
        
        progress_callback(f"Running: {' '.join(command)}\n")
        
        # Track running process for cancellation
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        self._running_compiles[project_id] = proc
        
        log_lines = []
        start_time = time.time()
        
        try:
            while True:
                if cancelled_check():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise TimedOutError() from None
                
                # Check timeout
                if time.time() - start_time > timeout:
                    proc.kill()
                    raise TimedOutError()
                
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                
                if line:
                    line = line.rstrip('\n')
                    log_lines.append(line)
                    progress_callback(line + '\n')
            
            return_code = proc.wait()
            
            # Parse latexmk output for metrics (LatexRunner.js:90-111, CompileManager.js:897-924)
            stdout = '\n'.join(log_lines)
            self._parse_latexmk_output(stdout, stats, timings)
            
            if return_code == 0:
                return CompilationResult(
                    status=CompilationStatus.SUCCESS,
                    log=stdout,
                    output_files=[],
                    duration_ms=0
                )
            else:
                # Check if it's a chktex exit (code 1) - benign lint exit
                if return_code == 1 and compile_group != 'conversions':
                    return CompilationResult(
                        status=CompilationStatus.ERROR,
                        log=stdout,
                        output_files=[],
                        duration_ms=0,
                        error_message=f"Exit code: {return_code}"
                    )
                return CompilationResult(
                    status=CompilationStatus.ERROR,
                    log=stdout,
                    output_files=[],
                    duration_ms=0,
                    error_message=f"Exit code: {return_code}"
                )
                
        finally:
            self._running_compiles.pop(project_id, None)
    
    def _parse_latexmk_output(self, stdout: str, stats: Dict, timings: Dict) -> None:
        """Parse latexmk output for metrics (LatexRunner.js:90-111, CompileManager.js:897-924)."""
        stats['log_lines'] = stdout.split('\n')
        
        # Count LaTeX runs (LatexRunner.js:90-98)
        # TeXLive 2022+: "Run number X of ...latex"
        # TeXLive 2021 and earlier: same pattern in stderr
        runs = len(re.findall(r'^Run number \d+ of .*latex', stdout, re.MULTILINE))
        if runs == 0:
            # Check stderr pattern would be here if we captured stderr separately
            pass
        
        # Match "Latexmk: Errors: N" - check if N > 0
        errors_match = re.search(r'^Latexmk: Errors:\s*(\d+)', stdout, re.MULTILINE)
        if errors_match:
            failed = 1 if int(errors_match.group(1)) > 0 else 0
        else:
            # Fallback: check if "Latexmk: Errors" line exists (legacy)
            failed = 1 if re.search(r'^Latexmk: Errors', stdout, re.MULTILINE) else 0
        
        stats['latexmk-errors'] = failed
        stats['latex-runs'] = runs
        stats['latex-runs-with-errors'] = failed * runs
        stats[f'latex-runs-{runs}'] = 1
        if failed:
            stats[f'latex-runs-with-errors-{runs}'] = 1
        
        # Count passes (CompileManager.js:897-924)
        # A "pass" is a run of latex/pdflatex/xelatex/lualatex
        passes = 0
        rule_times = {}  # Store as list of times per rule
        
        # Parse rule times from latexmk -time output
        # Pattern: "Rule 'rule': ... time_ms: X"
        for match in re.finditer(r"Rule\s+'(\w+)':.*?time_ms:\s*(\d+)", stdout):
            rule = match.group(1)
            time_ms = int(match.group(2))
            if rule not in rule_times:
                rule_times[rule] = []
            rule_times[rule].append(time_ms / 1000.0)
            
            if rule in LATEX_PASSES_RULES:
                passes += 1
        
        stats['passes'] = passes
        # For metrics, use the last (or average) time per rule
        stats['latexmk-rule-times'] = {k: v[-1] for k, v in rule_times.items()}
        
        # Parse /usr/bin/time -v output if present (LatexRunner.js:102-111)
        TIME_V_METRICS = [
            ('cpu-percent', r'Percent of CPU this job got: (\d+)'),
            ('cpu-time', r'User time.*: (\d+\.\d+)'),
            ('sys-time', r'System time.*: (\d+\.\d+)'),
        ]
        for timing_name, pattern in TIME_V_METRICS:
            match = re.search(pattern, stdout)
            if match:
                timings[timing_name] = float(match.group(1))
        
        # Image processing times (if available)
        # Pattern would be from latexmk-img-times
        img_timings = []
        stats['latexmk-img-times'] = img_timings
    
    def _collect_output_files(self, project_dir: Path, main_file: str,
                              output_dir: str) -> List[str]:
        """Collect output files matching OutputFileFinder.js logic."""
        output_path = project_dir / output_dir
        if not output_path.exists():
            return []
        
        output_files = []
        base_name = Path(main_file).stem
        
        # Walk output directory (OutputFileFinder.js:walkFolder)
        for root, dirs, files in os.walk(output_path):
            for file in files:
                if file == '.project-sync-state':
                    continue
                
                rel_root = Path(root).relative_to(output_path)
                if str(rel_root) == '.':
                    rel_path = file
                else:
                    rel_path = rel_root / file
                
                file_path = output_path / rel_path
                if file_path.exists() and file_path.stat().st_size > 0:
                    output_files.append(str(file_path))
        
        return output_files
    
    def _clear_project(self, project_dir: Path) -> None:
        """Clear project compile directory (CompileManager.js:425-428)."""
        # In standalone, we clear the build directory
        build_dir = project_dir / 'build'
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)
    
    def _emit_metrics(self, options: Dict, status: CompilationStatus,
                      stats: Dict, timings: Dict) -> None:
        """Emit compilation metrics (CompileManager.js:_emitMetrics:877-996)."""
        # This would integrate with a metrics system
        # For now, store in stats for potential external collection
        stats['metrics'] = {
            'status': status.value,
            'engine': options.get('compiler', 'pdflatex'),
            'compile_type': options.get('metrics_compile', 'initial'),
            'group': options.get('compile_group', 'compile'),
            'draft': options.get('draft', False),
            'stop_on_first_error': options.get('stop_on_first_error', False),
            'passes': stats.get('passes', 0),
            'sync_duration_ms': timings.get('sync', 0),
            'compile_duration_ms': timings.get('compile', 0),
            'output_duration_ms': timings.get('output', 0),
            'e2e_duration_ms': timings.get('compileE2E', 0),
        }
    
    def _record_performance_metrics(self, project_dir: Path, options: Dict,
                                    stats: Dict, timings: Dict) -> None:
        """Record detailed performance metrics for sampled requests (CompileManager.js:332-366)."""
        # Read fdb file if available (CompileManager.js:395-408)
        fdb_file = project_dir / 'build' / 'output.fdb_latexmk'
        if fdb_file.exists() and fdb_file.stat().st_size <= MAX_FDB_FILE_SIZE:
            try:
                fdb_content = fdb_file.read_text(encoding='utf-8')
                # Could parse fdb for file dependencies
                stats['fdb_size'] = len(fdb_content)
            except Exception:
                pass
    
    def sync_from_code(self, project_dir: Path, main_file: str,
                       line: int, column: int, options: Dict = None) -> Dict:
        """Forward SyncTeX: editor position -> PDF position (CompileManager.js:500-530)."""
        if options is None:
            options = {}
        
        synctex_file = project_dir / 'build' / 'output.synctex.gz'
        pdf_file = project_dir / 'build' / 'output.pdf'
        
        if not synctex_file.exists() or not pdf_file.exists():
            raise NotFoundError("SyncTeX or PDF file not found")
        
        # SyncTeX matches input files by absolute path, so normalise it here.
        main_path = Path(main_file)
        if not main_path.is_absolute():
            main_path = project_dir / main_path

        # Build synctex view command (CompileManager.js:508-515)
        cmd = [
            'synctex', 'view',
            '-i', f'{line}:{column}:{main_path}',
            '-o', str(pdf_file)
        ]
        
        try:
            result = subprocess.run(
                cmd, cwd=str(project_dir), capture_output=True, text=True,
                timeout=DEFAULT_SYNCTEX_TIMEOUT_MS / 1000
            )
            
            if result.returncode != 0:
                raise CompilationError(f"synctex failed: {result.stderr}")
            
            # Parse output (SynctexOutputParser.parseViewOutput)
            positions = self._parse_synctex_view(result.stdout)
            
            return {
                'code_positions': positions,
                'downloaded_from_cache': False
            }
        except subprocess.TimeoutExpired:
            raise TimedOutError("SyncTeX timed out")
    
    def sync_from_pdf(self, project_dir: Path, page: int, h: float, v: float) -> Dict:
        """Inverse SyncTeX: PDF position -> editor position (CompileManager.js:532-553)."""
        synctex_file = project_dir / 'build' / 'output.synctex.gz'
        pdf_file = project_dir / 'build' / 'output.pdf'
        
        if not synctex_file.exists() or not pdf_file.exists():
            raise NotFoundError("SyncTeX or PDF file not found")
        
        cmd = [
            'synctex', 'edit',
            '-o', f'{page}:{h}:{v}:{pdf_file}'
        ]
        
        try:
            result = subprocess.run(
                cmd, cwd=str(project_dir), capture_output=True, text=True,
                timeout=DEFAULT_SYNCTEX_TIMEOUT_MS / 1000
            )
            
            if result.returncode != 0:
                raise CompilationError(f"synctex failed: {result.stderr}")
            
            positions = self._parse_synctex_edit(result.stdout, str(project_dir / 'build'))
            
            return {
                'pdf_positions': positions,
                'downloaded_from_cache': False
            }
        except subprocess.TimeoutExpired:
            raise TimedOutError("SyncTeX timed out")
    
    def _parse_synctex_view(self, output: str) -> List[Dict]:
        """Parse real ``synctex view`` block output into position dictionaries."""
        positions = []
        current = {}
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if line.startswith('Page:'):
                current = {'page': int(re.search(r'\d+', line).group())}
            elif line.startswith('x:'):
                current['x'] = float(line.split(':', 1)[1])
            elif line.startswith('y:'):
                current['y'] = float(line.split(':', 1)[1])
            elif line.startswith('h:'):
                current['h'] = float(line.split(':', 1)[1])
            elif line.startswith('v:'):
                current['v'] = float(line.split(':', 1)[1])
            elif line.startswith('W:'):
                current['W'] = float(line.split(':', 1)[1])
            elif line.startswith('H:'):
                current['H'] = float(line.split(':', 1)[1])
            elif line.startswith('SyncTeX result end'):
                if 'page' in current and ('v' in current or 'y' in current):
                    positions.append(current)
                current = {}

        # Backwards compatibility with older single-line output.
        if not positions:
            for line in output.split('\n'):
                match = re.search(r'Page:\s*(\d+).*?H:\s*([\d.]+).*?V:\s*([\d.]+)', line)
                if match:
                    positions.append({
                        'page': int(match.group(1)),
                        'h': float(match.group(2)),
                        'v': float(match.group(3)),
                    })
        return positions
    
    def _parse_synctex_edit(self, output: str, base_dir: str) -> List[Dict]:
        """Parse real ``synctex edit`` block output into position dictionaries."""
        positions = []
        current = {}
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if line.startswith('Input:'):
                current = {'file': line.split(':', 1)[1].strip()}
            elif line.startswith('Line:'):
                value = line.split(':', 1)[1].strip()
                if value.isdigit():
                    current['line'] = int(value)
            elif line.startswith('Column:'):
                value = line.split(':', 1)[1].strip()
                try:
                    current['column'] = int(float(value))
                except ValueError:
                    current['column'] = 1
            elif line.startswith('SyncTeX result end'):
                if current.get('file') and current.get('line'):
                    current.setdefault('column', 1)
                    positions.append(current)
                current = {}

        # Backwards compatibility with older single-line output.
        if not positions:
            for line in output.split('\n'):
                match = re.search(r'Input:([^:]+):(\d+):(\d+)', line)
                if match:
                    positions.append({
                        'file': match.group(1),
                        'line': int(match.group(2)),
                        'column': int(match.group(3)),
                    })
        return positions
    
    def wordcount(self, project_dir: Path, main_file: str,
                  filename: str = 'main.tex') -> Dict:
        """Count words using texcount (CompileManager.js:710-834)."""
        texcount_cmd = shutil.which('texcount')
        if not texcount_cmd:
            return {'error': 'texcount not found'}
        
        file_path = project_dir / filename
        if not file_path.exists():
            file_path = project_dir / main_file
        
        cmd = ['texcount', '-nocol', '-inc', str(file_path)]
        
        try:
            result = subprocess.run(
                cmd, cwd=str(project_dir), capture_output=True, text=True,
                timeout=DEFAULT_WORDCOUNT_TIMEOUT_MS / 1000
            )
            
            return self._parse_wordcount_output(result.stdout)
        except subprocess.TimeoutExpired:
            return {'error': 'wordcount timed out'}
        except Exception as e:
            return {'error': str(e)}
    
    def _parse_wordcount_output(self, output: str) -> Dict:
        """Parse texcount output (CompileManager.js:_parseWordcountFromOutput:785-834)."""
        results = {
            'encode': '',
            'text_words': 0,
            'head_words': 0,
            'outside': 0,
            'headers': 0,
            'elements': 0,
            'math_inline': 0,
            'math_display': 0,
            'errors': 0,
            'messages': '',
        }
        
        for line in output.split('\n'):
            if ':' not in line:
                continue
            data, info = line.split(':', 1)
            data = data.strip()
            info = info.strip()
            
            if 'Encoding' in data:
                results['encode'] = info
            elif 'in text' in data:
                results['text_words'] = int(info) if info.isdigit() else 0
            elif 'in head' in data:
                results['head_words'] = int(info) if info.isdigit() else 0
            elif 'outside' in data:
                results['outside'] = int(info) if info.isdigit() else 0
            elif 'of head' in data:
                results['headers'] = int(info) if info.isdigit() else 0
            elif 'Number of floats/tables/figures' in data:
                results['elements'] = int(info) if info.isdigit() else 0
            elif 'Number of math inlines' in data:
                results['math_inline'] = int(info) if info.isdigit() else 0
            elif 'Number of math displayed' in data:
                results['math_display'] = int(info) if info.isdigit() else 0
            elif data == '(errors':
                results['errors'] = int(info) if info.isdigit() else 0
            elif '!!!' in line:
                results['messages'] += line + '\n'
        
        return results
    
    def is_compiling(self) -> bool:
        """Check if compilation is in progress."""
        return self.worker is not None and self.worker.isRunning()
    
    def clear_expired_projects(self, max_age_ms: int = EXPIRE_PROJECT_AFTER_IDLE_MS) -> None:
        """Clear expired project compile directories (CompileManager.js:457-475)."""
        # In standalone, we check build directories
        # This would need a projects index - simplified for now
        pass


# Standalone function for synchronous compilation
def compile_latex(project_dir: Path, main_file: str, compiler: str = 'pdflatex',
                  options: Dict = None, progress_callback: Callable = None) -> CompilationResult:
    """Synchronous compilation (for testing or simple use)."""
    manager = CompilerManager()
    return manager._run_compilation(
        project_dir, main_file, compiler, options or {},
        progress_callback or (lambda x: None),
        lambda: False
    )