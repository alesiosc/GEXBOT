#!/usr/bin/env python3
"""
GEXBOT Watchdog — monitors daemon processes and restarts them if crashed.
Runs every 60 seconds. Silent when everything is healthy.
"""
import os, sys, subprocess, time, json
from datetime import datetime

GEXBOT_DIR = os.path.dirname(os.path.abspath(__file__))
TV_CONNECT_DIR = os.path.join(os.path.dirname(GEXBOT_DIR), "tv-connect-watcher")
PYTHON = r"C:\Users\Cameron\AppData\Local\Programs\Python\Python313\python.exe"
LOG_FILE = os.path.join(GEXBOT_DIR, "_watchdog.log")

DAEMONS = [
    {
        "name": "Zulu",
        "script": os.path.join(GEXBOT_DIR, "gamma_scraper.py"),
        "cwd": GEXBOT_DIR,
        "match": "gamma_scraper.py",
    },
    {
        "name": "Zero Gamma",
        "script": os.path.join(GEXBOT_DIR, "Zero Gamma", "zero_gamma_scraper.py"),
        "cwd": os.path.join(GEXBOT_DIR, "Zero Gamma"),
        "match": "zero_gamma_scraper.py",
    },
    {
        "name": "Regimebot",
        "script": os.path.join(GEXBOT_DIR, "regimebot_screenshot.py"),
        "cwd": GEXBOT_DIR,
        "match": "regimebot_screenshot.py",
    },
    {
        "name": "TV Connect Watcher",
        "script": os.path.join(TV_CONNECT_DIR, "tv_connect_watcher.py"),
        "cwd": TV_CONNECT_DIR,
        "match": "tv_connect_watcher.py",
    },
]


def is_running(match_str):
    """Check if a process with the given name is running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        if match_str in result.stdout:
            return True
        # Also check pythonw.exe
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq pythonw.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        if match_str in result.stdout:
            return True
    except Exception:
        pass
    # Fallback: check via wmic
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe' or name='pythonw.exe'",
             "get", "commandline", "/format:csv"],
            capture_output=True, text=True, timeout=10,
        )
        if match_str in result.stdout:
            return True
    except Exception:
        pass
    return False


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def restart(damon):
    """Restart a daemon process."""
    script = damon["script"]
    cwd = damon["cwd"]
    try:
        subprocess.Popen(
            [PYTHON, script],
            cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log(f"RESTARTED {damon['name']}: {os.path.basename(script)}")
        return True
    except Exception as e:
        log(f"FAILED to restart {damon['name']}: {e}")
        return False


def main():
    any_restarted = False
    for damon in DAEMONS:
        if not is_running(damon["match"]):
            log(f"DOWN: {damon['name']} (no process matching '{damon['match']}')")
            if restart(damon):
                any_restarted = True
        else:
            # Healthy — silent
            pass

    if not any_restarted:
        # Nothing to report — exit silently
        pass


if __name__ == "__main__":
    main()
