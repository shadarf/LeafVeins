# LeafVeins - Mechanics & Design Document

## Overview
LeafVeins is a standalone Windows desktop application for LaTeX document writing and typesetting, replicating the core features of Ayakaleaf Pro (Overleaf Server Pro fork) without requiring Docker, WSL, or complex infrastructure.

**Source of Truth**: All mechanics below are derived from the original Overleaf Server Pro CLSI (Compile LaTeX Server Interface) service at:
- `ayakaleaf-pro-server-pro/services/clsi/app/js/CompileManager.js`
- `ayakaleaf-pro-server-pro/services/clsi/app/js/CompileController.js`
- `ayakaleaf-pro-server-pro/services/clsi/app/js/LatexRunner.js`
- `ayakaleaf-pro-server-pro/services/clsi/app/js/LocalCommandRunner.js`
- `ayakaleaf-pro-server-pro/services/clsi/app/js/DockerRunner.mjs`
- `ayakaleaf-pro-server-pro/services/clsi/app/js/CommandRunner.js`
- `ayakaleaf-pro-server-pro/services/clsi/app/js/OutputFileFinder.js`
- `ayakaleaf-pro-server-pro/services/clsi/app/js/Errors.js`
- `ayakaleaf-pro-server-pro/services/clsi/config/settings.defaults.cjs`

---

## Core Compilation Mechanics

### 1. LaTeX Compilation Engine (LatexRunner.js)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/LatexRunner.js`

#### Compiler Selection & Flags
| Compiler | latexmk Flag | Source |
|----------|--------------|--------|
| `latex` | `-pdfdvi` | LatexRunner.js:19-24 (COMPILER_FLAGS) |
| `pdflatex` | `-pdf` | LatexRunner.js:19-24 |
| `xelatex` | `-xelatex` | LatexRunner.js:19-24 |
| `lualatex` | `-lualatex` | LatexRunner.js:19-24 |

#### Base latexmk Command (LatexRunner.js:_buildLatexCommand:164-214)
```javascript
command = [
  'latexmk',
  '-cd',                          // Change to directory of main file
  '-jobname=output',              // Output file basename
  '-auxdir=$COMPILE_DIR',         // Auxiliary files directory
  '-outdir=$COMPILE_DIR',         // Output files directory
  '-synctex=1',                   // Generate SyncTeX data for forward/inverse search
  '-interaction=batchmode',       // Non-interactive mode
  '-time',                        // Show time statistics
  // Conditional:
  '-halt-on-error',               // When stopOnFirstError=true (line 188-189)
  '-f',                           // Force continue on error when stopOnFirstError=false (line 191-192)
  // Extra flags from request.flags (line 196-198)
  <compiler-specific-flag>,       // From COMPILER_FLAGS table above
  '$COMPILE_DIR/main.tex'         // Main file (with $COMPILE_DIR substitution)
]
```

#### Timeout Configuration
| Setting | Value | Unit | Source |
|---------|-------|------|--------|
| Default compilation timeout | 60000 | milliseconds | LatexRunner.js:39 |
| SyncTeX timeout | 60000 | milliseconds | CompileManager.js:599 |
| Wordcount timeout | 60000 | milliseconds | CompileManager.js:715 |
| Conversion timeout | 60 | seconds | settings.defaults.cjs:30-31 |
| Process lifespan limit | 172800000 | milliseconds (2 days) | settings.defaults.cjs:11-12 |

#### Compile Size Limit
- **Value**: `7mb` (default)
- **Source**: settings.defaults.cjs:9
- **Env Override**: `COMPILE_SIZE_LIMIT`

#### Error Handling Rules (LatexRunner.js:90-100)
```javascript
// Count LaTeX runs from latexmk output
runs = output.stdout.match(/^Run number \d+ of .*latex/gm)?.length 
    || output.stderr.match(/^Run number \d+ of .*latex/gm)?.length 
    || 0

// Detect compilation failure
failed = output.stdout.match(/^Latexmk: Errors/m) != null ? 1 : 0

stats['latexmk-errors'] = failed
stats['latex-runs'] = runs
stats['latex-runs-with-errors'] = failed ? runs : 0
```

---

### 2. Compile Manager Orchestration (CompileManager.js)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/CompileManager.js`

#### Compilation Flow
1. **Lock Acquisition** (line 65-76): Prevent simultaneous compiles per project
2. **Cache Restoration** (line 84-99): Download from CLSI cache if initial compile
3. **Resource Sync** (line 104-161): Write project files to compile directory
4. **Draft Mode Injection** (line 130-134): Apply draft mode modifications
5. **TikZ Management** (line 136-146): Inject output file for TikZ externalization
6. **Environment Setup** (line 173-196): Set `OVERLEAF_PROJECT_ID`, `openout_any`, `max_print_line`, `CHKTEX_*` vars
7. **Image Variant Selection** (line 198-202): Checkpointing variant if `enableCheckpoint` requested
8. **LaTeX Execution** (line 219-231): Run via LatexRunner with timeout
9. **Validation Handling** (line 235-252): Special handling for `check=validate|error` modes
10. **Output File Collection** (line 315-321): Save output files via OutputCacheManager
11. **Metrics Emission** (line 325, 332-366): Record performance metrics

#### Lock Manager (CompileManager.js:65-75, 410-423)
- Uses `LockManager.acquire(compileDir)` for compile directory locking
- `stopCompile` waits for lock release then kills LaTeX process

#### Expired Project Cleanup (CompileManager.js:457-475)
```javascript
// Clear projects older than maxCacheAgeMs
age = now - stats.mtime
hasExpired = age > maxCacheAgeMs  // default: 24 hours (settings.defaults.cjs:157)
```

#### Compile Concurrency Limits
| Instance Type | Concurrent Compiles | Source |
|---------------|---------------------|--------|
| Standard | 64 | settings.defaults.cjs:116 |
| Spot/Preemptible | 32 | settings.defaults.cjs:116 |

#### Metrics Tracking (CompileManager.js:_emitMetrics:877-996)
Tracks per-compile:
- `latexmkRuleDurationSeconds` per rule (latex, pdflatex, biber, bibtex, makeindex, xelatex, lualatex, xdvipdfmx, dvipdf, other, overhead)
- `imageProcessingDurationSeconds` by type
- `compilesTotal` with labels: status, engine, image tag, compile type, group, draft, stop_on_first_error, passes, sync type, png2pdf
- `syncResourcesDurationSeconds`
- `compileDurationSeconds` by passes (none/single/multiple)
- `processOutputFilesDurationSeconds`
- `e2eCompileDurationSeconds`

---

### 3. Command Runners

#### Local Command Runner (LocalCommandRunner.js)
**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/LocalCommandRunner.js`

- **Execution**: Node.js `spawn` with detached process group (line 64-69)
- **Working Directory**: `$COMPILE_DIR` substitution in command args (line 43-45)
- **Environment**: Inherits process.env + request environment (line 53-61)
- **Timeout/Sandboxing**: NOT enabled (line 50) - "timeouts and sandboxing are not enabled with CommandRunner"
- **Output Limit**: Unlimited (stdout accumulated in memory)
- **Kill Method**: `process.kill(-pid)` kills entire process group (line 110)
- **SyncTeX Support**: `canRunSyncTeXInOutputDir()` returns `true` (line 118-120)

#### Docker Runner (DockerRunner.mjs)
**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/DockerRunner.mjs`

- **Memory Limit**: 1 GB (line 277)
- **CPU Ulimits**: 
  - Soft: `timeoutInSeconds + 5`
  - Hard: `timeoutInSeconds + 10` (line 282-287)
- **Capabilities**: `CapDrop: ['ALL']` (line 289)
- **Security**: `SecurityOpt: ['no-new-privileges']` + seccomp + apparmor (line 290-304)
- **User**: `tex` (configurable via `TEXLIVE_IMAGE_USER`) (line 273, 154)
- **Network**: Disabled (`NetworkDisabled: true`) (line 272)
- **Read-only RootFS**: Optional (`Settings.clsi.docker.Readonly`) (line 310-314)
- **PATH Construction**: Based on TeX Live year from image tag (line 263-267)
  ```javascript
  env.PATH = `/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/texlive/${year}/bin/x86_64-linux/`
  ```
- **Volume Mounts**: Host compile dir → `/compile` (rw), synctex/wordcount → ro (line 81-88)
- **Container Auto-Remove**: For wordcount, synctex, png2pdf, conversions (settings.defaults.cjs:171-182)
- **Container Expiry**: 1 hour default (line 550), cleaned hourly (line 566-597)

#### Command Runner Selection (CommandRunner.js:12-18)
```javascript
if (Settings.clsi?.dockerRunner === true) {
  commandRunnerPath = './DockerRunner.mjs'
} else {
  commandRunnerPath = './LocalCommandRunner.js'
}
```

---

### 4. Output File Handling (OutputFileFinder.js)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/OutputFileFinder.js`

#### Output File Discovery Algorithm
```javascript
async function findOutputFiles(resources, directory) {
  // 1. Walk entire compile directory recursively
  // 2. Filter out incoming resources (source files)
  // 3. Filter out .project-sync-state
  // 4. Return remaining files as output files
  
  for (const path of files) {
    if (incomingResources.has(path)) continue      // Skip source files
    if (path === '.project-sync-state') continue   // Skip internal state
    outputFiles.push({
      path,
      type: Path.extname(path).replace(/^\./, '') || undefined
    })
  }
}
```

#### Special Output Files
| File | Purpose |
|------|---------|
| `output.pdf` | Main PDF output |
| `output.log` | LaTeX compilation log |
| `output.synctex.gz` | SyncTeX data for forward/inverse search |
| `output.fdb_latexmk` | File dependency database (max 1MB read) |
| `output.stdout` / `output.stderr` | Process stdout/stderr |

#### FDB File Reading (CompileManager.js:395-408)
```javascript
const MAX_FDB_FILE_SIZE = 1024 * 1024  // 1 MB
// Only read if file exists and < 1MB
```

---

### 5. SyncTeX Integration (CompileManager.js:500-672)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/CompileManager.js`

#### Forward Search (Editor → PDF)
```javascript
command = [
  'synctex', 'view',
  '-i', `${line}:${column}:${inputFilePath}`,
  '-o', outputFilePath
]
```
- **Timeout**: 60 seconds (line 599)
- **Compile Group**: `synctex` or `synctex-output`

#### Inverse Search (PDF → Editor)
```javascript
command = [
  'synctex', 'edit',
  '-o', `${page}:${h}:${v}:${outputFilePath}`
]
```

#### Cache Integration
- Can download `output.synctex.gz` from CLSI cache if not present locally
- Supports `compileFromClsiCache` mode for cached SyncTeX

---

### 6. Word Count (CompileManager.js:710-834)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/CompileManager.js`

#### texcount Command
```javascript
command = ['texcount', '-nocol', '-inc', filePath]
// -nocol: Don't count columns
// -inc: Include files in \input, \include
```

#### Parsed Output Fields (CompileManager.js:_parseWordcountFromOutput:785-834)
| Field | texcount Output Pattern |
|-------|------------------------|
| `encode` | `Encoding: <value>` |
| `textWords` | `in text: <number>` |
| `headWords` | `in head: <number>` |
| `outside` | `outside: <number>` |
| `headers` | `of head: <number>` |
| `elements` | `Number of floats/tables/figures: <number>` |
| `mathInline` | `Number of math inlines: <number>` |
| `mathDisplay` | `Number of math displayed: <number>` |
| `errors` | `(errors: <number>)` |
| `messages` | Lines containing `!!! ` |

---

### 7. Draft Mode & TikZ (CompileManager.js:130-146)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/CompileManager.js`

#### Draft Mode
- Injected via `DraftModeManager.promises.injectDraftMode(compileDir/mainFile)` (line 131-133)
- Modifies main file for draft compilation (faster, no images)

#### TikZ Externalization
- Checked via `TikzManager.promises.checkMainFile()` (line 136-140)
- Injects output file via `TikzManager.promises.injectOutputFile()` (line 142-145)

---

### 8. PNG to PDF Conversion (Png2Pdf)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/Png2Pdf.js` (referenced in CompileManager.js:289-302)

- **Enabled**: `Png2Pdf.isEnabled()` (line 289)
- **Slow PNG Detection**: Records PNGs flagged as "slow" by latexmk (line 291)
- **Conversion Image**: `quay.io/sharelatex/png2pdf:2026-06-24` (settings.defaults.cjs:37-38)
- **Min File Size**: 1 MB (settings.defaults.cjs:40-41)
- **Docker User**: Same UID/GID as CLSI process (settings.defaults.cjs:179-182)

---

### 9. Settings & Configuration (settings.defaults.cjs)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/config/settings.defaults.cjs`

#### Key Default Values
| Setting | Default | Unit | Env Override |
|---------|---------|------|--------------|
| `compileSizeLimit` | `7mb` | - | `COMPILE_SIZE_LIMIT` |
| `processLifespanLimitMs` | 172800000 | ms (2 days) | `PROCESS_LIFE_SPAN_LIMIT_MS` |
| `conversionTimeoutSeconds` | 60 | seconds | `CLSI_CONVERSION_TIMEOUT_SECONDS` |
| `maxUploadSize` | 52428800 | bytes (50 MB) | - |
| `compileConcurrencyLimit` | 64 (32 spot) | - | - |
| `pdfCachingMinChunkSize` | 1024 | bytes | `PDF_CACHING_MIN_CHUNK_SIZE` |
| `pdfCachingMaxProcessingTime` | 10000 | ms | `PDF_CACHING_MAX_PROCESSING_TIME` |
| `pdfCachingWorkerPoolSize` | 4 | - | `PDF_CACHING_WORKER_POOL_SIZE` |
| `pdfCachingWorkerPoolBackLogLimit` | 40 | - | `PDF_CACHING_WORKER_POOL_BACK_LOG_LIMIT` |
| `expireProjectAfterIdleMs` | 86400000 | ms (24h) | - |
| `checkProjectsIntervalMs` | 600000 | ms (10min) | - |
| `DOCKER_RUNNER` | false | - | `DOCKER_RUNNER` |
| `TEXLIVE_IMAGE` | `quay.io/sharelatex/texlive-full:2017.1` | - | `TEXLIVE_IMAGE` / `TEX_LIVE_DOCKER_IMAGE` |

---

### 10. Error Types (Errors.js)

**Function Address**: `ayakaleaf-pro-server-pro/services/clsi/app/js/Errors.js`

| Error Type | HTTP Code | Description |
|------------|-----------|-------------|
| `AlreadyCompilingError` | 423 (Locked) | Compile already in progress |
| `FilesOutOfSyncError` | 409 (Conflict) | Project files out of sync, retry needed |
| `MissingUpdatesError` | 409 (Conflict) | Missing updates from history |
| `TooManyCompileRequestsError` | 503 (Unavailable) | Rate limited |
| `TimedOutError` | - | Compilation timed out |
| `ConversionError` | 422/500 | Document conversion failed (pandoc, etc.) |
| `NotFoundError` | 404 | Output directory/file not found |
| `InvalidParameter` | 400 | Invalid request parameter |
| `QueueLimitReachedError` | - | Compile queue full |
| `NoXrefTableError` | - | No cross-reference table (SyncTeX) |

#### ConversionError User-Facing Exit Codes (Errors.js:39-54)
```
1, 23, 24, 25, 44, 63, 64, 91, 92, 94, 95, 97, 98, 99
```

---

## Key Formulas & Rules

### LaTeX Pass Counting (CompileManager.js:897-924)
```javascript
// LATEX_PASSES_RULES = {latex, lualatex, xelatex, pdflatex}
passes = 0
for (run of latexmkRuns) {
  if (LATEX_PASSES_RULES.has(run.rule)) {
    passes += 1
  }
}
// Metrics bucketed: passes === 0 ? 'none' : passes === 1 ? 'single' : 'multiple'
```

### Compile Status Determination (CompileController.js:120-135)
```javascript
if (outputFiles.has(output.pdf with size > 0)) {
  status = 'success'
} else if (request.stopOnFirstError) {
  status = 'stopped-on-first-error'
} else {
  status = 'failure'
}
```

### Image Variant Selection (CompileManager.js:851-875)
```javascript
// Checkpointing variant
if (request.enableCheckpoint) {
  checkpointingImageName = `${imageName}.checkpointing`
  if (allowedImages.includes(checkpointingImageName)) {
    return { imageName: checkpointingImageName, env: { ENABLE_CHECKPOINT: '1' } }
  }
}
```

### Project Expiry (CompileManager.js:469-473)
```javascript
age = Date.now() - stats.mtime
hasExpired = age > maxCacheAgeMs  // 24 hours default
```

### Container Fingerprinting (DockerRunner.mjs:330-334)
```javascript
// MD5 hash of container options JSON for container name
fingerprint = crypto.createHash('md5').update(JSON.stringify(containerOptions)).digest('hex')
containerName = `project-${projectId}-${fingerprint}`
```

---

## PDF Caching Mechanics

### Chunk Processing (settings.defaults.cjs:106-115)
- **Min Chunk Size**: 1024 bytes
- **Max Processing Time**: 10 seconds per chunk
- **Worker Pool**: 4 workers, 40 backlog limit
- **Dark Mode**: Separate cache (`enablePdfCachingDark`)

---

## Build System Integration

### Build ID Format (OutputCacheManager - referenced)
- Generated by `OutputCacheManager.promises.saveOutputFiles()`
- Used for output file URLs: `/project/{projectId}/user/{userId}/build/{buildId}/output/{file}`

### Compile Request Body (schemas.js - referenced in CompileController.js:12)
Validated via `@overleaf/validation-tools` with zod schemas including:
- `compiler`, `timeout`, `flags`, `draft`, `stopOnFirstError`
- `rootResourcePath`, `compileGroup`, `imageName`
- `enableCheckpoint`, `png2pdf`, `compileFromClsiCache`
- `check` (none/validate/error), `syncType`

---

## Environment Variables Reference

| Variable | Purpose | Default |
|----------|---------|---------|
| `COMPILE_SIZE_LIMIT` | Max project size for compilation | `7mb` |
| `PROCESS_LIFE_SPAN_LIMIT_MS` | Process max lifetime | 2 days |
| `CLSI_CONVERSION_TIMEOUT_SECONDS` | Document conversion timeout | 60 |
| `TEXLIVE_OPENOUT_ANY` | TeX openout_any setting | - |
| `TEXLIVE_MAX_PRINT_LINE` | TeX max_print_line setting | - |
| `DOCKER_RUNNER` | Enable Docker sandboxing | false |
| `TEXLIVE_IMAGE` / `TEX_LIVE_DOCKER_IMAGE` | TeX Live Docker image | `quay.io/sharelatex/texlive-full:2017.1` |
| `SECCOMP_PROFILE` | Custom seccomp profile | Built-in |
| `APPARMOR_PROFILE` | AppArmor profile | - |
| `CLSI_PERFORMANCE_LOG_SAMPLING` | Metrics sampling % | 0 |

---

## Implementation Notes for LeafVeins

### Current LeafVeins Implementation (app/compiler/compiler_manager.py)
The current implementation uses:
- Direct subprocess calls to local LaTeX installation
- Single-pass compilation (no latexmk orchestration)
- No Docker sandboxing
- No SyncTeX integration
- No cache management
- Simplified timeout handling

### Required Changes to Match Original Mechanics
1. **Use latexmk** as the compilation driver (not direct pdflatex/xelatex/lualatex calls)
2. **Implement proper timeout handling** (60s default, configurable)
3. **Add SyncTeX support** with `-synctex=1` flag and synctex binary
4. **Implement multi-pass compilation** tracking (latex-runs metric)
5. **Add stopOnFirstError** flag mapping to `-halt-on-error` / `-f`
6. **Implement output file discovery** (filter source files, find output.pdf, .log, .synctex.gz)
7. **Add compilation metrics** (passes, duration, status)
8. **Implement project locking** to prevent concurrent compiles
9. **Add draft mode** and TikZ externalization support
10. **Implement word count** via texcount
11. **Add cache management** for compile directories (24h expiry)
12. **Support compiler selection** via latexmk flags (-pdf, -xelatex, -lualatex, -pdfdvi)

### Configuration Mapping
| Original Setting | LeafVeins Config |
|------------------|------------------|
| `timeout` (60000ms) | `compiler.timeout` (60s) |
| `compiler` flags | `project.compiler` → latexmk flag |
| `stopOnFirstError` | `compiler.stop_on_first_error` |
| `compileSizeLimit` | Not implemented |
| `expireProjectAfterIdleMs` | Not implemented |

---

## Function Address Reference Table

| Function | File | Lines |
|----------|------|-------|
| `runLatex` | LatexRunner.js | 26-118 |
| `_buildLatexCommand` | LatexRunner.js | 164-214 |
| `doCompileWithLock` | CompileManager.js | 65-76 |
| `doCompile` | CompileManager.js | 78-368 |
| `_saveOutputFiles` | CompileManager.js | 370-393 |
| `stopCompile` | CompileManager.js | 410-423 |
| `clearExpiredProjects` | CompileManager.js | 457-475 |
| `syncFromCode` | CompileManager.js | 500-530 |
| `syncFromPdf` | CompileManager.js | 532-553 |
| `wordcount` | CompileManager.js | 710-783 |
| `compile` | CompileController.js | 48-210 |
| `run` (LocalCommandRunner) | LocalCommandRunner.js | 29-102 |
| `run` (DockerRunner) | DockerRunner.mjs | 21-137 |
| `_getContainerOptions` | DockerRunner.mjs | 236-328 |
| `findOutputFiles` | OutputFileFinder.js | 23-43 |
| `_parseWordcountFromOutput` | CompileManager.js | 785-834 |
| `_getImageVariantSettings` | CompileManager.js | 851-875 |
| `_emitMetrics` | CompileManager.js | 877-996 |