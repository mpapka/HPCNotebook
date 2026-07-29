"""labHelpers.py - shared toolkit for the CS 455 HPC hands-on notebooks.

Every lab notebook imports this once near the top:

    from labHelpers import *

It provides five things:

1. Pretty output     - showFile / showScriptCard / showEnvCard / showNote and
                       rich tables for scheduler queues (qstatTable, sinfoTable).
2. Lab setup         - setupLab() records your cluster identity (host alias,
                       project account, scratch path, scheduler) and writes
                       labEnv.sh so terminal scripts and cells agree.
3. Preflight         - preflight() renders a pass/fail table of environment
                       checks before you start (ssh reachable, module system,
                       scheduler answering, scratch writable, ...).
4. Checkpoints       - checkpoint() verifies your work after each part of a
                       lab and gives targeted feedback: what passed, what
                       failed, how to fix it, and where to read more.
                       labSummary() shows everything you have passed so far.
5. Remote & jobs     - sshRun / sshPut / sshGet drive the cluster over your
                       existing ssh config. submitJob / waitJob / jobStatus
                       wrap qsub or sbatch behind ONE call so lab cells stay
                       identical whether the cluster is PBS (Polaris) or
                       Slurm. renderField / plotScaling are the shared
                       viz primitives every lab from 01 on uses.

The module is self-healing: it installs its own display dependencies (rich,
pygments) on first import if they are missing.
"""

# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------

def ensureDependencies(packageNames):
    """Import each package, pip-installing it quietly first if missing."""
    import importlib, subprocess, sys
    for packageName in packageNames:
        moduleName = packageName.split("==")[0]
        try:
            importlib.import_module(moduleName)
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", packageName],
                           check=True)


ensureDependencies(["rich", "pygments"])

import os
import re
import html as htmlLib
import json
import pathlib
import shutil
import socket
import subprocess
import time
from pathlib import Path

from IPython.display import HTML, display
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

richConsole = Console(force_jupyter=True)   # emit HTML inside Jupyter, always

fontStack = ("'Fira Code','JetBrains Mono',SFMono-Regular,Menlo,"
             "Consolas,'Liberation Mono',monospace")


# --------------------------------------------------------------------------
# Pretty output - cards and code display
# --------------------------------------------------------------------------

def styleBackground(styleName):
    return HtmlFormatter(style=styleName).style.background_color or "#272822"


def contrastForeground(backgroundColor):
    hexPart = backgroundColor.lstrip("#")
    red, green, blue = int(hexPart[0:2], 16), int(hexPart[2:4], 16), int(hexPart[4:6], 16)
    luminance = 0.299 * red + 0.587 * green + 0.114 * blue
    return "#1a1a1a" if luminance > 140 else "#f5f5f5"


def highlightScript(scriptText, language="bash", style="monokai"):
    formatter = HtmlFormatter(style=style, noclasses=True, nowrap=True)
    try:
        lexer = get_lexer_by_name(language)
    except Exception:
        lexer = get_lexer_by_name("text")
    return highlight(scriptText, lexer, formatter).rstrip("\n")


def showScriptCard(scriptText, title, language="bash", envVars=None, style="monokai"):
    envVars = envVars or {}
    backgroundColor = styleBackground(style)
    foregroundColor = contrastForeground(backgroundColor)
    highlightedBody = highlightScript(scriptText, language=language, style=style)

    def buildChip(chipKey, chipValue):
        return (
            f'<span style="background:#2d333b;color:#adbac7;padding:2px 9px;'
            f'border-radius:6px;font-size:12px;white-space:nowrap;">'
            f'{htmlLib.escape(str(chipKey))} '
            f'<b style="color:#6cb6ff;">{htmlLib.escape(str(chipValue))}</b></span>'
        )

    chipsHTML = "".join(buildChip(key, value) for key, value in envVars.items())
    codeHTML = (
        f'<pre style="margin:0;background:{backgroundColor};color:{foregroundColor};'
        f'font-family:{fontStack};font-size:13px;line-height:1.55;'
        f'white-space:pre;overflow-x:auto;">{highlightedBody}</pre>'
    )
    cardHTML = f"""
    <div style="max-width:820px;border-radius:10px;overflow:hidden;
                font-family:{fontStack};box-shadow:0 1px 8px rgba(0,0,0,.28);">
      <div style="background:#1f2430;color:#e6e6e6;padding:10px 14px;
                  display:flex;align-items:center;gap:10px;">
        <span style="font-weight:700;letter-spacing:.3px;">{htmlLib.escape(title)}</span>
        <span style="margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;">{chipsHTML}</span>
      </div>
      <div style="background:{backgroundColor};padding:10px 14px;overflow-x:auto;">{codeHTML}</div>
    </div>
    """
    display(HTML(cardHTML))


def showEnvCard(scriptText, title="labEnv.sh", envVars=None):
    showScriptCard(scriptText, title=title, language="bash", envVars=envVars)


extensionLanguage = {
    ".py": "python", ".sh": "bash", ".yaml": "yaml", ".yml": "yaml",
    ".txt": "text", ".json": "json", ".md": "markdown", ".conf": "text",
    ".csv": "text", ".jsonl": "json", ".html": "html",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cu": "cuda",
    ".f90": "fortran", ".F90": "fortran",
    "makefile": "makefile",
}


def showFile(filePath, language=None, title=None, style="monokai", maxLines=None):
    path = Path(filePath).expanduser()
    if not path.exists():
        showNote(f"File not found: {path}", kind="warn", title="showFile")
        return
    fileText = path.read_text()
    if maxLines is not None:
        lines = fileText.splitlines()
        if len(lines) > maxLines:
            fileText = "\n".join(lines[:maxLines] + [f"... ({len(lines) - maxLines} more lines)"])
    if language is None:
        key = "makefile" if path.name.lower() in ("makefile", "gnumakefile") else path.suffix.lower()
        language = extensionLanguage.get(key, "text")
    showScriptCard(fileText, title=title or path.name, language=language, style=style)


noteColors = {
    "info":    ("#0b3d91", "#e8f0fe", "#1a56db"),
    "ok":      ("#14532d", "#ecfdf5", "#059669"),
    "warn":    ("#7c2d12", "#fff7ed", "#d97706"),
    "error":   ("#7f1d1d", "#fef2f2", "#dc2626"),
    "tip":     ("#3b0764", "#faf5ff", "#7c3aed"),
}


def showNote(message, kind="info", title=None, link=None, linkText=None):
    textColor, backgroundColor, borderColor = noteColors.get(kind, noteColors["info"])
    icon = {"info": "&#9432;", "ok": "&#10003;", "warn": "&#9888;",
            "error": "&#10007;", "tip": "&#128161;"}.get(kind, "&#9432;")
    titleHTML = (f'<div style="font-weight:700;margin-bottom:4px;">{htmlLib.escape(title)}</div>'
                 if title else "")
    linkHTML = ""
    if link:
        linkHTML = (f'<div style="margin-top:6px;"><a href="{htmlLib.escape(link)}" '
                    f'target="_blank" style="color:{borderColor};font-weight:600;">'
                    f'{htmlLib.escape(linkText or "Read more")} &#8599;</a></div>')
    display(HTML(f"""
    <div style="max-width:820px;border-left:4px solid {borderColor};
                background:{backgroundColor};color:{textColor};
                padding:10px 14px;border-radius:6px;margin:4px 0;
                font-family:system-ui,-apple-system,sans-serif;font-size:14px;
                line-height:1.5;">
      <span style="font-weight:700;">{icon}</span> {titleHTML}{message}{linkHTML}
    </div>
    """))


# --------------------------------------------------------------------------
# Shell + SSH helpers
# --------------------------------------------------------------------------

def runShell(command, timeoutSeconds=60):
    """Run a local command; capture stdout+stderr and returncode. Never raises."""
    useShell = isinstance(command, str)
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                shell=useShell, timeout=timeoutSeconds)
        return result.stdout + result.stderr, result.returncode
    except FileNotFoundError:
        name = command if useShell else command[0]
        return f"{name}: not found on this machine", 127
    except subprocess.TimeoutExpired:
        return f"timed out after {timeoutSeconds}s", 124


def clusterHost():
    """The ssh alias (from ~/.ssh/config) that reaches the cluster.

    setupLab() sets HPC_HOST; every lab cell reads it here so 'the cluster'
    is a single knob and changing it does not touch any lab.
    """
    return os.environ.get("HPC_HOST", "polaris")


def sshRun(command, host=None, timeoutSeconds=120, quiet=False):
    """Run a command on the cluster over ssh. Returns (output, returncode).

    command   a string that will be executed by the remote login shell.
              Pass whatever you would type after 'ssh polaris'.
    host      ssh alias; defaults to $HPC_HOST (from setupLab()).
    quiet     when True, suppress the 'connection refused' style messages
              on failure (useful in preflight probes).
    """
    host = host or clusterHost()
    opts = ["-o", "BatchMode=yes",           # never prompt for a password
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10"]
    if quiet:
        opts += ["-q"]
    return runShell(["ssh", *opts, host, command], timeoutSeconds=timeoutSeconds)


def sshPut(localPath, remotePath, host=None, timeoutSeconds=120):
    """scp a local file (or dir with -r) to the cluster."""
    host = host or clusterHost()
    localPath = str(Path(localPath).expanduser())
    args = ["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    if Path(localPath).is_dir():
        args.append("-r")
    return runShell([*args, localPath, f"{host}:{remotePath}"], timeoutSeconds=timeoutSeconds)


def sshGet(remotePath, localPath, host=None, timeoutSeconds=120):
    """scp a remote file (or dir with -r) back to the Hub."""
    host = host or clusterHost()
    localPath = str(Path(localPath).expanduser())
    Path(localPath).parent.mkdir(parents=True, exist_ok=True)
    args = ["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-r"]
    return runShell([*args, f"{host}:{remotePath}", localPath], timeoutSeconds=timeoutSeconds)


def scheduler(host=None):
    """Probe the cluster for its batch scheduler: returns 'pbs' or 'slurm' (or '').

    Lab cells that submit jobs use this to pick qsub vs sbatch, so the SAME
    notebook cell works on Polaris (PBS Pro) and on Slurm sites.
    """
    out, code = sshRun("command -v qsub sbatch 2>/dev/null || true", host=host,
                       timeoutSeconds=15, quiet=True)
    if code != 0:
        return ""
    if "qsub" in out:
        return "pbs"
    if "sbatch" in out:
        return "slurm"
    return ""


# --------------------------------------------------------------------------
# Job submission - one call, two schedulers
# --------------------------------------------------------------------------

def submitJob(scriptPath, host=None, extraArgs=None, timeoutSeconds=30):
    """Submit a batch script that already lives on the cluster.

    scriptPath   remote path (e.g. '~/lab00/hello.pbs').
    Returns the job id string on success, or '' on failure.
    """
    kind = scheduler(host)
    extraArgs = extraArgs or []
    if kind == "pbs":
        cmd = "qsub " + " ".join(extraArgs) + " " + scriptPath
    elif kind == "slurm":
        cmd = "sbatch " + " ".join(extraArgs) + " " + scriptPath
    else:
        return ""
    out, code = sshRun(cmd, host=host, timeoutSeconds=timeoutSeconds)
    if code != 0:
        return ""
    # PBS prints the full jobid ("1234567.polaris-pbs-01"); Slurm prints
    # "Submitted batch job 1234567". Grab the numeric id in both cases.
    match = re.search(r"(\d+)", out)
    return match.group(1) if match else out.strip()


def jobStatus(jobId, host=None):
    """Return one of: 'queued', 'running', 'done', 'unknown'."""
    kind = scheduler(host)
    if kind == "pbs":
        out, code = sshRun(f"qstat -x {jobId} 2>/dev/null | tail -n +3",
                           host=host, timeoutSeconds=15, quiet=True)
        if code != 0 or not out.strip():
            return "unknown"
        parts = out.split()
        state = parts[4] if len(parts) >= 5 else ""
        return {"Q": "queued", "H": "queued", "R": "running",
                "E": "running", "F": "done", "C": "done"}.get(state, "unknown")
    if kind == "slurm":
        out, code = sshRun(f"squeue -h -j {jobId} -o %T 2>/dev/null",
                           host=host, timeoutSeconds=15, quiet=True)
        if code != 0:
            return "unknown"
        state = out.strip()
        if not state:
            return "done"           # gone from the queue
        return {"PENDING": "queued", "CONFIGURING": "queued",
                "RUNNING": "running", "COMPLETING": "running"}.get(state, "unknown")
    return "unknown"


def waitJob(jobId, host=None, pollSeconds=10, maxSeconds=1800):
    """Block (politely) until a job leaves the queue, or timeout. Returns final status."""
    start = time.time()
    lastState = ""
    while time.time() - start < maxSeconds:
        state = jobStatus(jobId, host=host)
        if state != lastState:
            showNote(f"job {jobId}: <b>{state}</b>", kind="info")
            lastState = state
        if state == "done":
            return state
        time.sleep(pollSeconds)
    showNote(f"job {jobId} still not done after {maxSeconds}s; last state: {lastState}",
             kind="warn")
    return lastState or "unknown"


# --------------------------------------------------------------------------
# Queue display helpers
# --------------------------------------------------------------------------

def qstatTable(user=None, host=None):
    """Render your queued/running jobs as a rich table (PBS or Slurm)."""
    user = user or os.environ.get("HPC_USER") or os.environ.get("USER", "")
    kind = scheduler(host)
    if kind == "pbs":
        out, _ = sshRun(f"qstat -u {user}", host=host, timeoutSeconds=20, quiet=True)
    elif kind == "slurm":
        out, _ = sshRun(f"squeue -u {user}", host=host, timeoutSeconds=20, quiet=True)
    else:
        richConsole.print(Panel("no scheduler detected on the cluster",
                                title="queue", box=box.ROUNDED))
        return
    richConsole.print(Panel(out.strip() or "no jobs in queue",
                            title=f"queue - {kind} - {user}", box=box.ROUNDED))


# --------------------------------------------------------------------------
# Lab setup - identity, cluster host, labEnv.sh
# --------------------------------------------------------------------------

def setupLab(labName, host="polaris", remoteUser=None, project=None,
             queue=None, scratch=None, extraEnv=None):
    """Set up this lab's identity and write labEnv.sh.

    labName      folder under ~/ on the Hub (e.g. "lab00") AND under $SCRATCH
                 on the cluster. Both are created if missing.
    host         ssh alias for the cluster (must resolve via ~/.ssh/config).
    remoteUser   your login on the cluster; defaults to $HPC_USER, then $USER.
    project      allocation / account to charge (Polaris: '-A', Slurm: '--account=').
    queue        queue/partition name.
    scratch      remote scratch dir; each lab creates <scratch>/<labName>/.
    extraEnv     dict of any additional env values to export.

    Everything is exported to os.environ (so `!` cells and sshRun see it) and
    written to ~/<labName>/labEnv.sh (so terminal scripts can `source` it too).
    Returns the resolved dict.
    """
    extraEnv = extraEnv or {}
    if not os.environ.get("USER"):
        try:
            import pwd as _pwd
            os.environ["USER"] = _pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            os.environ["USER"] = "student"
    remoteUser = remoteUser or os.environ.get("HPC_USER") or os.environ["USER"]

    resolved = {
        "USER":       os.environ["USER"],
        "HPC_HOST":   host,
        "HPC_USER":   remoteUser,
        "HPC_LAB":    labName,
    }
    if project:
        resolved["HPC_PROJECT"] = project
    if queue:
        resolved["HPC_QUEUE"] = queue
    if scratch:
        resolved["HPC_SCRATCH"] = scratch
        resolved["HPC_LAB_DIR"] = f"{scratch.rstrip('/')}/{labName}"
    for k, v in extraEnv.items():
        resolved[k] = v

    for k, v in resolved.items():
        os.environ[k] = str(v)

    labDir = Path.home() / labName
    labDir.mkdir(parents=True, exist_ok=True)
    envPath = labDir / "labEnv.sh"
    lines = [
        f"# {labName} shared environment - source before running any helper script.",
        f"export USER={resolved['USER']}",
    ]
    lines += [f"export {k}={v}" for k, v in resolved.items()
              if k not in ("USER",)]
    envPath.write_text("\n".join(lines) + "\n")
    resolved["labDir"] = str(labDir)
    resolved["labEnv"] = str(envPath)

    chips = {k: v for k, v in resolved.items() if k not in ("labDir", "labEnv")}
    showEnvCard(envPath.read_text(), title=f"{labName}/labEnv.sh", envVars=chips)
    return resolved


# --------------------------------------------------------------------------
# Check predicates
# --------------------------------------------------------------------------

def fileExists(filePath):
    def probe():
        path = Path(filePath).expanduser()
        return path.is_file(), str(path) if path.is_file() else f"missing: {path}"
    return probe


def dirExists(dirPath):
    def probe():
        path = Path(dirPath).expanduser()
        return path.is_dir(), str(path) if path.is_dir() else f"missing: {path}"
    return probe


def fileContains(filePath, text):
    def probe():
        path = Path(filePath).expanduser()
        if not path.is_file():
            return False, f"missing: {path}"
        found = text in path.read_text(errors="replace")
        return found, f"'{text}' {'found' if found else 'not found'} in {path.name}"
    return probe


def fileNonEmpty(filePath, minLines=1):
    def probe():
        path = Path(filePath).expanduser()
        if not path.is_file():
            return False, f"missing: {path}"
        lineCount = sum(1 for _ in path.open(errors="replace"))
        return lineCount >= minLines, f"{path.name}: {lineCount} line(s)"
    return probe


def commandSucceeds(command, timeoutSeconds=30):
    def probe():
        out, code = runShell(command, timeoutSeconds=timeoutSeconds)
        display_ = command if isinstance(command, str) else " ".join(command)
        return code == 0, (out.strip().splitlines() or [display_])[0][:120]
    return probe


def commandOnPath(commandName):
    def probe():
        location = shutil.which(commandName)
        return bool(location), location or f"{commandName} not on PATH"
    return probe


def pythonImportable(moduleName):
    def probe():
        import importlib
        try:
            importlib.import_module(moduleName)
            return True, f"import {moduleName} ok"
        except ImportError as importError:
            return False, str(importError)[:120]
    return probe


def envVarSet(envName):
    def probe():
        value = os.environ.get(envName, "")
        return bool(value), f"{envName}={value}" if value else f"{envName} is not set"
    return probe


# HPC-flavored predicates ---------------------------------------------------

def sshReachable(host=None, timeoutSeconds=15):
    """Probe: passwordless ssh to the cluster works."""
    def probe():
        out, code = sshRun("echo ok", host=host, timeoutSeconds=timeoutSeconds, quiet=True)
        if code == 0 and "ok" in out:
            return True, f"ssh {host or clusterHost()} responded"
        return False, out.strip().splitlines()[0][:120] if out.strip() else \
            f"ssh {host or clusterHost()} failed (rc={code})"
    return probe


def remoteFileExists(remotePath, host=None):
    """Probe: a file exists on the cluster."""
    def probe():
        out, code = sshRun(f"test -e {remotePath} && echo YES || echo NO",
                           host=host, timeoutSeconds=15, quiet=True)
        ok = "YES" in out
        return ok, f"{remotePath} {'exists' if ok else 'missing'} on {host or clusterHost()}"
    return probe


def moduleAvailable(moduleName, host=None):
    """Probe: `module avail <name>` finds a match on the cluster."""
    def probe():
        out, code = sshRun(f"bash -lc 'module avail {moduleName} 2>&1 | grep -i {moduleName} | head -1'",
                           host=host, timeoutSeconds=30, quiet=True)
        ok = code == 0 and moduleName.lower() in out.lower()
        return ok, out.strip().splitlines()[0][:120] if out.strip() else f"no match for {moduleName}"
    return probe


def schedulerAnswers(host=None):
    """Probe: qstat or sinfo responds."""
    def probe():
        kind = scheduler(host)
        if not kind:
            return False, "neither qsub nor sbatch on remote PATH"
        return True, f"scheduler is {kind}"
    return probe


# --------------------------------------------------------------------------
# Preflight and checkpoint rendering
# --------------------------------------------------------------------------

def check(label, probe, hint=None, link=None, linkText=None):
    return {"label": label, "probe": probe, "hint": hint,
            "link": link, "linkText": linkText}


def runProbe(probe):
    try:
        result = probe()
    except Exception as probeError:
        return False, f"check crashed: {str(probeError)[:100]}"
    if isinstance(result, tuple):
        return bool(result[0]), str(result[1])
    return bool(result), ""


checkpointResults = {}


def renderCheckTable(title, checks, infoRows=None):
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("check", style="cyan", overflow="fold")
    table.add_column("result")
    table.add_column("detail", overflow="fold")
    from rich.markup import escape
    failures = []
    for item in checks:
        ok, detail = runProbe(item["probe"])
        mark = "[green]✓ ok[/]" if ok else "[red]✗ failed[/]"
        table.add_row(escape(str(item["label"])), mark, escape(str(detail)))
        if not ok:
            failures.append(item)
    for infoLabel, infoValue in (infoRows or []):
        table.add_row(escape(str(infoLabel)), "[cyan]info[/]", escape(str(infoValue)))
    richConsole.print(table)
    return failures


def preflight(checks, infoRows=None, title="preflight - environment"):
    failures = renderCheckTable(title, checks, infoRows=infoRows)
    if failures:
        for failed in failures:
            showNote(failed.get("hint") or "This must be fixed before continuing.",
                     kind="error", title=f"Fix first: {failed['label']}",
                     link=failed.get("link"), linkText=failed.get("linkText"))
    else:
        showNote("Environment looks good - continue with the lab.", kind="ok")
    return len(failures) == 0


def checkpoint(title, checks, successNote=None, docLink=None, docLinkText=None):
    failures = renderCheckTable(f"checkpoint - {title}", checks)
    passedCount = len(checks) - len(failures)
    checkpointResults[title] = {"passed": passedCount, "total": len(checks)}
    if failures:
        for failed in failures:
            showNote(failed.get("hint") or "Re-run the cells above for this part.",
                     kind="warn", title=f"How to fix: {failed['label']}",
                     link=failed.get("link"), linkText=failed.get("linkText"))
        showNote(f"{passedCount}/{len(checks)} checks passed. Fix the items above, "
                 "then re-run this checkpoint cell - it is safe to run any number of times.",
                 kind="info")
    else:
        showNote(successNote or "All checks passed - move on to the next part.",
                 kind="ok", title=f"{title}: complete",
                 link=docLink, linkText=docLinkText)
    return len(failures) == 0


def labSummary(labTitle="Lab progress"):
    if not checkpointResults:
        showNote("No checkpoints have been run yet in this session.", kind="info")
        return
    table = Table(title=labTitle, box=box.SIMPLE_HEAVY)
    table.add_column("checkpoint", style="cyan", overflow="fold")
    table.add_column("score")
    table.add_column("status")
    allPassed = True
    for title, result in checkpointResults.items():
        passed, total = result["passed"], result["total"]
        ok = passed == total
        allPassed = allPassed and ok
        table.add_row(title, f"{passed}/{total}",
                      "[green]✓ complete[/]" if ok else "[yellow]⚠ incomplete[/]")
    richConsole.print(table)
    if allPassed:
        showNote("Every checkpoint passed. Nice work - you are done with this lab.",
                 kind="ok")
    else:
        showNote("Some checkpoints are incomplete. Scroll up, fix the failing parts, "
                 "and re-run their checkpoint cells.", kind="warn")


# --------------------------------------------------------------------------
# End-of-lab feedback (star rating + comment)
# --------------------------------------------------------------------------

def feedbackIdentity():
    netid = os.environ.get("USER") or ""
    fullName = ""
    try:
        import pwd
        entry = pwd.getpwuid(os.getuid())
        netid = netid or entry.pw_name
        fullName = (entry.pw_gecos or "").split(",")[0].strip()
    except Exception:
        pass
    return netid or "unknown", (fullName or netid or "unknown")


def writeFeedback(notebook, answers):
    import datetime, secrets
    netid, fullName = feedbackIdentity()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    slug = re.sub(r"[^a-z0-9]+", "-", str(notebook).lower()).strip("-") or "lab"
    outDir = Path.home() / ".feedback"
    outDir.mkdir(parents=True, exist_ok=True)
    destPath = outDir / f"{slug}-{netid}-{secrets.token_hex(4)}.jsonl"
    with destPath.open("w") as handle:
        for question, answer in answers:
            handle.write(json.dumps({
                "ts": timestamp, "netid": netid, "name": fullName,
                "notebook": str(notebook), "question": str(question),
                "answer": "" if answer is None else str(answer),
            }) + "\n")
    return destPath


def starRatingWidget(maxStars=5):
    import ipywidgets as widgets
    state = {"value": 0}
    stars = [widgets.Button(description="☆", layout=widgets.Layout(width="42px"))
             for _ in range(maxStars)]

    def paint(count):
        for index, button in enumerate(stars):
            filled = index < count
            button.description = "★" if filled else "☆"
            button.button_style = "warning" if filled else ""

    def makeHandler(index):
        def handler(_):
            state["value"] = index + 1
            paint(index + 1)
        return handler

    for index, button in enumerate(stars):
        button.on_click(makeHandler(index))
    return __import__("ipywidgets").HBox(stars), state


def feedback(notebook, questions=None, maxStars=5):
    ratingLabel = f"How would you rate this lab? (1-{maxStars} stars)"
    commentLabel = "Anything confusing, broken, or worth improving? (optional)"
    extraQuestions = list(questions or [])

    try:
        ensureDependencies(["ipywidgets"])
        import ipywidgets as widgets

        starBox, starState = starRatingWidget(maxStars)
        wideBox = widgets.Layout(width="98%", max_width="760px", height="90px")
        commentBox = widgets.Textarea(placeholder="Type your feedback here...", layout=wideBox)
        extraBoxes = [(q, widgets.Textarea(placeholder="(optional)",
                                           layout=widgets.Layout(width="98%",
                                                                 max_width="760px",
                                                                 height="60px")))
                      for q in extraQuestions]
        submitButton = widgets.Button(description="Submit feedback",
                                      button_style="success", icon="paper-plane")
        outputArea = widgets.Output()

        def onSubmit(_):
            with outputArea:
                if not starState["value"] and not commentBox.value.strip():
                    showNote("Pick a star rating or add a comment before submitting.", kind="warn")
                    return
                answers = [(ratingLabel, starState["value"] or ""),
                           (commentLabel, commentBox.value.strip())]
                answers += [(q, box_.value.strip()) for q, box_ in extraBoxes]
                writeFeedback(notebook, answers)
                submitButton.disabled = True
                submitButton.description = "Submitted - thank you!"
                showNote("Thanks. Your feedback was recorded for the instructor.", kind="ok")

        submitButton.on_click(onSubmit)

        def labelHTML(text):
            return widgets.HTML(f'<b style="font-family:system-ui;font-size:14px">'
                                f'{htmlLib.escape(text)}</b>')

        rows = [labelHTML(ratingLabel), starBox, labelHTML(commentLabel), commentBox]
        for q, box_ in extraBoxes:
            rows += [labelHTML(q), box_]
        rows += [submitButton, outputArea]
        display(widgets.VBox(rows))
        return
    except Exception:
        pass

    def ask(prompt):
        try:
            return input(prompt).strip()
        except EOFError:
            return ""

    answers = [(ratingLabel, ask(f"{ratingLabel}\n  stars (1-{maxStars}, Enter to skip): ")),
               (commentLabel, ask(f"{commentLabel}\n  > "))]
    for question in extraQuestions:
        answers.append((question, ask(f"{question}\n  > ")))
    writeFeedback(notebook, answers)
    print("Thanks. Your feedback was recorded for the instructor.")


# --------------------------------------------------------------------------
# Publication-quality figures - house style + save helper (labDD + every lab)
# --------------------------------------------------------------------------

# Okabe-Ito palette: colorblind-safe, grayscale-safe qualitative colors.
OKABE_ITO = ["#0072B2", "#D55E00", "#009E73", "#CC79A7",
             "#E69F00", "#56B4E9", "#F0E442", "#000000"]
FIGURE_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
FIGURE_LINESTYLES = ["-", "--", "-.", ":"]


def applyHouseStyle():
    """Set matplotlib rcParams for report/paper-quality figures. Returns palette."""
    ensureDependencies(["matplotlib"])
    import matplotlib as mpl
    from cycler import cycler
    mpl.rcParams.update({
        "figure.figsize": (6.0, 3.7),
        "figure.dpi": 110,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": cycler(color=OKABE_ITO),
        "legend.frameon": False,
        "lines.linewidth": 1.8,
        "lines.markersize": 5,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    return list(OKABE_ITO)


def saveFigure(fig, name, figuresDir="figures", formats=("pdf", "png")):
    """Save a figure as PDF (vector, for papers) + PNG (raster, for slides)."""
    outDir = pathlib.Path(figuresDir)
    outDir.mkdir(parents=True, exist_ok=True)
    written = []
    for extension in formats:
        target = outDir / f"{name}.{extension}"
        fig.savefig(target, bbox_inches="tight")
        written.append(target)
    showNote("Saved " + ", ".join(f"<code>{p}</code>" for p in written), kind="ok")
    return written


# --------------------------------------------------------------------------
# Visualization primitives - solution field and performance plots
# --------------------------------------------------------------------------

# Rendering has two modes, chosen automatically by size:
#   * Hub-side  - small runs (<= RENDER_INLINE_MB per frame). matplotlib runs
#                 in the notebook kernel; students see the code and the frame.
#   * Node-side - big runs. The compute job renders frames alongside the CSV
#                 and we sshGet the ready-made PNGs/MP4 back.
# The moment `renderField(mode='auto')` sees a dump above the threshold, it
# switches modes and prints one line explaining why - that IS the in-situ
# visualization lesson lab11 or lab12 leans on.

RENDER_INLINE_MB = 10.0


def renderField(source, outPath, title=None, cmap="viridis", vmin=None, vmax=None, mode="auto"):
    """Render a 2D scalar field to an image.

    source    a numpy array, a path to a .npy/.npz/.csv file, or a directory
              of frame files (in which case an MP4 is assembled).
    outPath   where to write the image (.png) or animation (.mp4/.gif).
    mode      'auto' | 'hub' | 'node'. 'auto' switches to node-side above
              RENDER_INLINE_MB and prints why.
    """
    ensureDependencies(["matplotlib", "numpy"])
    import numpy as np, matplotlib.pyplot as plt

    outPath = Path(outPath).expanduser()
    outPath.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(source, (str, Path)):
        src = Path(source).expanduser()
        sizeMB = src.stat().st_size / 1e6 if src.exists() else 0.0
        if mode == "auto" and sizeMB > RENDER_INLINE_MB:
            showNote(f"Field is {sizeMB:.1f} MB > {RENDER_INLINE_MB} MB threshold - "
                     "render on the compute node (in-situ) instead of the Hub. "
                     "See lab11 for the in-situ pattern.",
                     kind="tip", title="renderField: switched to node-side")
            return None
        if src.suffix == ".npy":
            data = np.load(src)
        elif src.suffix == ".npz":
            with np.load(src) as z:
                data = z[list(z.keys())[0]]
        elif src.suffix == ".csv":
            data = np.loadtxt(src, delimiter=",")
        else:
            raise ValueError(f"unsupported field source: {src}")
    else:
        data = source

    fig, ax = plt.subplots()
    im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax, origin="lower", aspect="equal")
    if title:
        ax.set_title(title)
    ax.set_xlabel("x"); ax.set_ylabel("y")
    fig.colorbar(im, ax=ax, shrink=0.85, label="u")
    fig.savefig(outPath, bbox_inches="tight", dpi=150)
    plt.close(fig)
    showNote(f"wrote <code>{outPath}</code>", kind="ok")
    return outPath


def plotScaling(csvPath, kind="strong", outPath=None, baselineCol="threads",
                timeCol="wall_s", ideal=True, title=None):
    """One-line publication-safe HPC plot from a timings CSV.

    kind        'strong' (speedup vs N) | 'weak' (efficiency vs N) |
                'roofline' (needs 'flops' and 'bytes' columns) |
                'timeline' (rank timeline; needs 'rank','start','end').
    csvPath     e.g. lab03/outputs/perf/timings.csv with columns
                <baselineCol>, <timeCol> (and optional 'variant' to group lines).
    outPath     defaults to <csvPath dir>/../figures/<kind>.pdf.
    Returns the paths saveFigure() wrote.
    """
    ensureDependencies(["matplotlib", "pandas"])
    import pandas as pd, matplotlib.pyplot as plt
    applyHouseStyle()

    csvPath = Path(csvPath).expanduser()
    df = pd.read_csv(csvPath)
    outPath = Path(outPath).expanduser() if outPath else (csvPath.parent.parent / "figures" / f"{kind}")

    fig, ax = plt.subplots()

    if kind == "strong":
        groups = df.groupby("variant") if "variant" in df.columns else [("run", df)]
        for i, (name, g) in enumerate(groups):
            g = g.sort_values(baselineCol)
            base = g[timeCol].iloc[0]
            g = g.assign(speedup=base / g[timeCol])
            ax.plot(g[baselineCol], g["speedup"], marker=FIGURE_MARKERS[i % 8],
                    linestyle=FIGURE_LINESTYLES[i % 4], label=str(name))
        if ideal:
            xs = sorted(df[baselineCol].unique())
            ax.plot(xs, xs, color="black", linestyle=":", linewidth=1, label="ideal")
        ax.set_xscale("log", base=2); ax.set_yscale("log", base=2)
        ax.set_xlabel(baselineCol); ax.set_ylabel("speedup")
        ax.set_title(title or f"Strong scaling ({csvPath.stem})")
        ax.legend()

    elif kind == "weak":
        groups = df.groupby("variant") if "variant" in df.columns else [("run", df)]
        for i, (name, g) in enumerate(groups):
            g = g.sort_values(baselineCol)
            base = g[timeCol].iloc[0]
            g = g.assign(efficiency=base / g[timeCol])
            ax.plot(g[baselineCol], g["efficiency"], marker=FIGURE_MARKERS[i % 8],
                    linestyle=FIGURE_LINESTYLES[i % 4], label=str(name))
        if ideal:
            ax.axhline(1.0, color="black", linestyle=":", linewidth=1, label="ideal (=1)")
        ax.set_xlabel(baselineCol); ax.set_ylabel("parallel efficiency")
        ax.set_ylim(0, 1.15)
        ax.set_title(title or f"Weak scaling ({csvPath.stem})")
        ax.legend()

    elif kind == "roofline":
        # df needs: flops (per run), bytes (per run), wall_s, plus optional 'peak_gflops', 'peak_bw_gbs'
        df = df.copy()
        df["intensity"]   = df["flops"] / df["bytes"]        # FLOP/byte
        df["performance"] = df["flops"] / df["wall_s"] / 1e9 # GFLOP/s
        peakGF = df["peak_gflops"].max()  if "peak_gflops" in df.columns else df["performance"].max() * 4
        peakBW = df["peak_bw_gbs"].max()  if "peak_bw_gbs" in df.columns else df["performance"].max() * 4
        ax.scatter(df["intensity"], df["performance"], zorder=3)
        import numpy as np
        xs = np.logspace(-2, 3, 200)
        ax.plot(xs, xs * peakBW, color="black", linestyle="--", label=f"memory roof ({peakBW:.0f} GB/s)")
        ax.axhline(peakGF, color="black", linestyle=":", label=f"compute roof ({peakGF:.0f} GFLOP/s)")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("arithmetic intensity (FLOP/byte)")
        ax.set_ylabel("performance (GFLOP/s)")
        ax.set_title(title or "Roofline")
        ax.legend()

    elif kind == "timeline":
        # df needs: rank, start, end, phase (optional)
        phases = sorted(df["phase"].unique()) if "phase" in df.columns else ["run"]
        colorFor = {p: OKABE_ITO[i % 8] for i, p in enumerate(phases)}
        for _, row in df.iterrows():
            phase = row.get("phase", "run") if hasattr(row, "get") else "run"
            ax.barh(row["rank"], row["end"] - row["start"], left=row["start"],
                    color=colorFor[phase], edgecolor="none")
        ax.set_xlabel("time (s)"); ax.set_ylabel("rank")
        ax.set_title(title or "Rank timeline")
        # legend by phase
        from matplotlib.patches import Patch
        ax.legend(handles=[Patch(color=c, label=p) for p, c in colorFor.items()])
    else:
        raise ValueError(f"unknown kind: {kind}")

    return saveFigure(fig, outPath.name, figuresDir=str(outPath.parent))


print("labHelpers ready - setupLab, preflight, checkpoint, labSummary, feedback, "
      "sshRun, sshPut, sshGet, submitJob, waitJob, jobStatus, qstatTable, "
      "renderField, plotScaling, applyHouseStyle, saveFigure, showFile, showNote "
      "+ check predicates (fileExists, sshReachable, moduleAvailable, schedulerAnswers, ...)")
