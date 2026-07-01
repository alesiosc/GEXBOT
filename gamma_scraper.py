"""Scrape SPX Gamma from Discord every 2 min. Only posts changed rows."""
import asyncio, json, os, sys, urllib.request, requests, time
from datetime import datetime, timezone, timedelta

BROWSER_PORT = 9223
CHANNEL_ID = "1027647733219209227"
GUILD_ID = "921574741272317982"
CHANNEL_URL = f"https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}"
WEBHOOK_URL = "https://discord.com/api/webhooks/1520500109547274300/VsWwcaGAO5FHST6Z3QCFYPjZiQDk0hvIUyhnhtaRpW9SKdcQUGTwX-humqYDNx98VtKK"
STATE_FILE = os.path.join(os.path.dirname(__file__), "_zulu_state.json")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"D:\MyPythonProjects_2\browser_data"


def ensure_browser():
    """Check if Chrome debug port is open, launch if not."""
    import socket, subprocess
    try:
        s = socket.create_connection(("127.0.0.1", BROWSER_PORT), timeout=2)
        s.close()
        return True  # already running
    except:
        pass
    # Launch Chrome with remote debugging (matching open_trump_tabs.py)
    try:
        subprocess.Popen([
            CHROME_PATH,
            f"--remote-debugging-port={BROWSER_PORT}",
            f"--user-data-dir={USER_DATA_DIR}",
            "--restore-last-session",
        ], shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
        print(f"  Launched Chrome on port {BROWSER_PORT}", flush=True)
        # Wait for it to come up AND restore session
        for _ in range(30):
            time.sleep(1)
            try:
                s = socket.create_connection(("127.0.0.1", BROWSER_PORT), timeout=1)
                s.close()
                break
            except:
                continue
        # Extra time for tabs to fully restore
        time.sleep(5)

        # Re-open all startup tabs (Truth Social, Google Sheets, Apps Script, etc.)
        # after a crash, since --restore-last-session doesn't survive a hard kill.
        # Skips tabs already opened by daemons (Discord, TradingView).
        import os
        script_path = os.path.join(os.path.dirname(__file__), "..", "open_trump_tabs.py")
        subprocess.Popen([sys.executable.replace("python.exe", "pythonw.exe"), script_path], shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
        print(f"  Launched tab re-opener: {script_path}", flush=True)

        return True
    except Exception as e:
        print(f"  Failed to launch Chrome: {e}", flush=True)
        return False


def now_est():
    """Return datetime in US/Eastern."""
    try:
        import zoneinfo
        return datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    except ImportError:
        pass
    now_utc = datetime.now(timezone.utc)
    offset = 4 if 4 <= now_utc.month <= 10 else 5
    return now_utc - timedelta(hours=offset)


def today_str():
    return now_est().strftime("%Y-%m-%d")


def is_market_hours_est():
    now = now_est()
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return 570 <= m < 960  # 9:30 – 16:00 EST


def is_nine_thirty_or_later():
    """Return True if time is >= 9:30 AM ET."""
    now = now_est()
    m = now.hour * 60 + now.minute
    return m >= 570


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"spx_levels": {}, "last_full_post_date": None}


def save_state(spx_levels, last_full_post_date=None):
    state = {"spx_levels": spx_levels, "last_full_post_date": last_full_post_date}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def cdp_fetch(path):
    url = f"http://127.0.0.1:{BROWSER_PORT}{path}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            if attempt == 0:
                if not ensure_browser():
                    return None
            elif attempt == 1:
                time.sleep(3)
            else:
                return None
    return None


def get_prices():
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5ENDX?interval=1d&range=1d",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        nq = json.loads(resp.read())["chart"]["result"][0]["meta"]["regularMarketPrice"]
    req2 = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=1d",
        headers=headers,
    )
    with urllib.request.urlopen(req2, timeout=10) as resp:
        spx = json.loads(resp.read())["chart"]["result"][0]["meta"]["regularMarketPrice"]
    req3 = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/ES%3DF?interval=1d&range=1d",
        headers=headers,
    )
    with urllib.request.urlopen(req3, timeout=10) as resp:
        es = json.loads(resp.read())["chart"]["result"][0]["meta"]["regularMarketPrice"]
    return spx, nq, es


async def scrape_once(force_full=False):
    """Scrape Discord SPX Gamma table. Returns (delta_messages, full_messages, spx_levels) where
    delta_messages = only the specific lines that changed (for webhook)
    full_messages  = all current values (for TV paste)
    Returns (None, None, spx_levels) if nothing changed (delta case)."""
    import websockets

    tabs = cdp_fetch("/json")
    if not tabs:
        raise Exception("No tab list — is Chrome on 9223?")

    tab = None
    for t in tabs:
        if CHANNEL_ID in t.get("url", ""):
            tab = t
            break
    if not tab:
        for t in tabs:
            if "discord.com/channels" in t.get("url", ""):
                tab = t
                break
    if not tab:
        req = urllib.request.Request(
            f"http://127.0.0.1:{BROWSER_PORT}/json/new", method="PUT"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            tab = json.loads(resp.read().decode())

    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise Exception("No WS URL")

    async with websockets.connect(ws_url) as ws:
        async def cdp(method, params=None, rid=1):
            cmd = {"id": rid, "method": method}
            if params:
                cmd["params"] = params
            await ws.send(json.dumps(cmd))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == rid:
                    return r

        async def evaluate(js):
            return await cdp("Runtime.evaluate", {
                "expression": js, "returnByValue": True,
            })

        await cdp("Page.enable")
        nav = await evaluate("window.location.href")
        current = nav.get("result", {}).get("result", {}).get("value", "")

        if CHANNEL_URL not in current:
            await cdp("Page.navigate", {"url": CHANNEL_URL})
            print("  Navigated to #gex-stream", flush=True)
            await asyncio.sleep(5)

        for _ in range(15):
            r = await evaluate(
                """document.querySelectorAll('[class*="messageListItem"]').length"""
            )
            if r.get("result", {}).get("result", {}).get("value", 0) > 0:
                break
            await asyncio.sleep(2)

        await evaluate("""
            const scrollers = document.querySelectorAll('[class*="scroller"]');
            for (const s of scrollers) s.scrollTop = s.scrollHeight;
        """)
        await asyncio.sleep(2)

        r = await evaluate("""
            (() => {
                const wrappers = document.querySelectorAll('[class*="messageListItem"]');
                const last = wrappers[wrappers.length - 1];
                if (!last) return '';
                const c = last.querySelector('[class*="messageContent"]');
                return c ? c.innerText : '';
            })()
        """)
        text = r.get("result", {}).get("result", {}).get("value", "")
        if not text:
            raise Exception("No message content found")

        # Parse SPX Gamma table — these are the SOURCE values
        spx_levels = {}
        for line in text.split("\n"):
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4:
                    key, val = parts[1], parts[2]
                    if val and key and not key.startswith("-") and key != "SPX Gamma":
                        try:
                            spx_levels[key] = float(val)
                        except:
                            pass

        if not spx_levels:
            raise Exception("No SPX Gamma levels found")

        # Only extract the Zulu-relevant SPX keys
        zulu_spx_keys = [
            "Major Negative by Volume",
            "Major Positive by Volume",
            "Major Negative by OI",
            "Major Positive by OI",
        ]
        zulu_spx = {k: spx_levels[k] for k in zulu_spx_keys if k in spx_levels}
        if not zulu_spx:
            raise Exception("No Zulu SPX levels found")

        # --- Fetch current prices for conversion ---
        spx_price, nq_price, es_price = get_prices()
        nq_ratio = nq_price / spx_price
        es_ratio = es_price / spx_price

        spx_display_map = [
            ("Major Negative by Volume", "Zulu Vol Lo"),
            ("Major Positive by Volume", "Zulu Vol Hi"),
            ("Major Negative by OI", "Zulu OI Lo"),
            ("Major Positive by OI", "Zulu OI Hi"),
        ]

        # Build FULL set (always — used for TV paste)
        full_nq, full_es = [], []
        for key_name, display_name in spx_display_map:
            if key_name in zulu_spx:
                nq_val = round(zulu_spx[key_name] * nq_ratio, 2)
                es_val = round(zulu_spx[key_name] * es_ratio, 2)
                full_nq.append(f"{display_name} {nq_val}")
                full_es.append(f"{display_name} {es_val}")

        full_messages = []
        if full_nq:
            full_messages.append(("NQ", "NQ - " + "; ".join(full_nq)))
        if full_es:
            full_messages.append(("ES", "ES - " + "; ".join(full_es)))

        # --- Change detection: compare RAW SPX levels only ---
        state = load_state()
        previous = state.get("spx_levels", {})

        if force_full:
            # Return full set for both webhook and TV
            save_state(zulu_spx, state.get("last_full_post_date"))
            return full_messages, full_messages, zulu_spx

        # Delta-only: check which raw SPX keys actually changed
        changed_keys = set()
        for k, v in zulu_spx.items():
            prev = previous.get(k)
            if prev is None or abs(prev - v) > 0.001:
                changed_keys.add(k)

        if not changed_keys:
            print(f"  No SPX level changes at {datetime.now().strftime('%H:%M:%S')}", flush=True)
            return None, full_messages, zulu_spx

        # Build DELTA messages (only changed lines) for webhook
        delta_nq, delta_es = [], []
        for key_name, display_name in spx_display_map:
            if key_name in zulu_spx and key_name in changed_keys:
                nq_val = round(zulu_spx[key_name] * nq_ratio, 2)
                es_val = round(zulu_spx[key_name] * es_ratio, 2)
                delta_nq.append(f"{display_name} {nq_val}")
                delta_es.append(f"{display_name} {es_val}")

        delta_messages = []
        if delta_nq:
            delta_messages.append(("NQ", "NQ - " + "; ".join(delta_nq)))
        if delta_es:
            delta_messages.append(("ES", "ES - " + "; ".join(delta_es)))

        # Save new SPX state
        save_state(zulu_spx, state.get("last_full_post_date"))
        return delta_messages, full_messages, zulu_spx


def post_to_webhook(changes):
    for label, text in changes:
        r = requests.post(WEBHOOK_URL, json={"content": f"```\n{text}\n```"}, timeout=15)
        if r.status_code in [200, 204]:
            print(f"  Posted {label}: {text}", flush=True)
        else:
            print(f"  {label} failed: {r.status_code}", flush=True)


def paste_into_tv(changes):
    """Inject changed levels into TV indicator's ZULU Levels input via CDP."""
    import websockets

    # Build combined text for TV: NQ - ...; ES - ...
    combined = "; ".join(text for _, text in changes)

    tabs = cdp_fetch("/json")
    if not tabs:
        print("  TV paste: no browser tabs", flush=True)
        return

    tv_tab = None
    for t in tabs:
        url = t.get("url", "")
        if "tradingview.com" in url and "chart" in url:
            tv_tab = t
            break
    if not tv_tab:
        print("  TV paste: no TradingView tab", flush=True)
        return

    try:
        async def _do_paste():
            ws_url = tv_tab["webSocketDebuggerUrl"]
            async with websockets.connect(ws_url) as ws:
                async def cdp(method, params=None, rid=1):
                    cmd = {"id": rid, "method": method}
                    if params: cmd["params"] = params
                    await ws.send(json.dumps(cmd))
                    while True:
                        r = json.loads(await ws.recv())
                        if r.get("id") == rid:
                            return r

                async def eval_obj(js):
                    """Evaluate JS and return the parsed object (not string)."""
                    r = await cdp("Runtime.evaluate", {
                        "expression": js, "returnByValue": True,
                    })
                    return r.get("result", {}).get("result", {}).get("value")

                await cdp("Page.enable")
                await asyncio.sleep(1)

                # Check if settings dialog is already open
                already_open = await eval_obj("""
                    (() => {
                        const w = document.querySelector('[class*="wrapper-b8SxMnzX"]');
                        return w && w.offsetParent !== null;
                    })()
                """)
                if not already_open:
                    # Retry gear click up to 3 times with different methods
                    for attempt in range(3):
                        gear = await eval_obj("""
                            (() => {
                                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                                for (const ind of indicators) {
                                    const txt = ind.textContent;
                                    if (txt.includes('v13.9') || txt.includes('v13.7') || txt.includes('v13.6') || txt.includes('Friday 13th')) {
                                        let el = ind;
                                        while (el && !el.className.includes('item') && !el.className.includes('study')) {
                                            el = el.parentElement;
                                        }
                                        if (el) {
                                            const btns = el.querySelectorAll('button');
                                            for (const b of btns) {
                                                if (b.getAttribute('aria-label') === 'Settings') {
                                                    const r = b.getBoundingClientRect();
                                                    return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                                                }
                                            }
                                        }
                                    }
                                }
                                return null;
                            })()
                        """)
                        if not gear:
                            print(f"  TV gear: not found (attempt {attempt+1})", flush=True)
                            break
                        # Click via CDP Input (browser-level)
                        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
                        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
                        await asyncio.sleep(2)
                        # Also try JS click as backup
                        await eval_obj("""
                            (() => {
                                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                                for (const ind of indicators) {
                                    if (ind.textContent.includes('v13.9') || ind.textContent.includes('v13.7') || ind.textContent.includes('v13.6') || ind.textContent.includes('Friday 13th')) {
                                        let el = ind;
                                        while (el && !el.className.includes('item') && !el.className.includes('study')) { el = el.parentElement; }
                                        if (el) {
                                            const btns = el.querySelectorAll('button');
                                            for (const b of btns) {
                                                if (b.getAttribute('aria-label') === 'Settings') {
                                                    b.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                                                    return;
                                                }
                                            }
                                        }
                                    }
                                }
                            })()
                        """)
                        await asyncio.sleep(2)
                        # Check if dialog opened
                        opened = await eval_obj("""
                            (() => {
                                const w = document.querySelector('[class*="wrapper-b8SxMnzX"]');
                                return w && w.offsetParent !== null;
                            })()
                        """)
                        if opened:
                            print(f"  TV settings opened (attempt {attempt+1})", flush=True)
                            break
                        else:
                            print(f"  TV gear click retry {attempt+1}/3", flush=True)
                else:
                    print("  TV settings already open", flush=True)

                # Find ZULU Levels input cell and click inner-slot via CDP to activate text input
                slot_rect = await eval_obj("""
                    (() => {
                        const all = document.querySelectorAll('*');
                        for (const el of all) {
                            if ((el.textContent || '').trim() === 'ZULU Levels' && el.children.length === 0) {
                                let cell = el.parentElement;
                                while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) {
                                    cell = cell.parentElement;
                                }
                                if (cell) {
                                    const next = cell.nextElementSibling;
                                    if (next) {
                                        const slot = next.querySelector('[class*="inner-slot"]');
                                        if (slot) {
                                            const r = slot.getBoundingClientRect();
                                            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                                        }
                                    }
                                }
                                return null;
                            }
                        }
                        return null;
                    })()
                """)
                if slot_rect:
                    await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": slot_rect["x"], "y": slot_rect["y"], "button": "left", "clickCount": 1})
                    await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": slot_rect["x"], "y": slot_rect["y"], "button": "left", "clickCount": 1})
                    await asyncio.sleep(2)

                # Now set the value on the visible text INPUT
                await eval_obj(f"""
                    (() => {{
                        const targetVal = {json.dumps(combined)};
                        const all = document.querySelectorAll('*');
                        for (const el of all) {{
                            if ((el.textContent || '').trim() === 'ZULU Levels' && el.children.length === 0) {{
                                let cell = el.parentElement;
                                while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) {{
                                    cell = cell.parentElement;
                                }}
                                if (cell) {{
                                    const next = cell.nextElementSibling;
                                    if (next) {{
                                        const inp = next.querySelector('input');
                                        if (inp) {{
                                            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                            ns.call(inp, targetVal);
                                            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        }}
                                    }}
                                }}
                                return;
                            }}
                        }}
                    }})()
                """)
                await asyncio.sleep(1)

                # Click OK/Apply (retry with flexible matching)
                ok_clicked = False
                for ok_attempt in range(3):
                    ok_result = await eval_obj("""
                        (() => {
                            const btns = document.querySelectorAll('button, [role="button"], [class*="button"]');
                            for (const b of btns) {
                                const t = (b.textContent || '').trim();
                                if (t.toLowerCase() === 'ok' || t.toLowerCase() === 'apply') {
                                    b.click();
                                    return 'clicked: ' + t;
                                }
                            }
                            return 'no ok';
                        })()
                    """)
                    if ok_result and ok_result.startswith('clicked'):
                        ok_clicked = True
                        print(f"  TV OK: {ok_result}", flush=True)
                        break
                    await asyncio.sleep(1)
                if not ok_clicked:
                    print("  TV OK: button not found", flush=True)
                print(f"  TV injected: {combined[:80]}...", flush=True)

        asyncio.run(_do_paste())
    except Exception as e:
        print(f"  TV paste error: {e}", flush=True)


def main():
    # Prevent duplicate instances
    try:
        from pid_lock import PIDLock
        lock = PIDLock("gamma_scraper")
        if not lock.acquire():
            return
    except ImportError:
        pass

    print(f"Zulu watcher started at {datetime.now()}", flush=True)

    # Align first run to next :13 second mark
    now = datetime.now()
    target_sec = 13
    current_sec = now.second + now.microsecond / 1_000_000
    if current_sec < target_sec:
        delay = target_sec - current_sec
    else:
        delay = (120 - (current_sec - target_sec) % 120) % 120
    print(f"  First check in {delay:.1f}s (aligning to :13)", flush=True)
    time.sleep(delay)

    while True:
        try:
            if not is_market_hours_est():
                # Sleep until next market open (9:30)
                est = now_est()
                tomorrow = est + timedelta(days=1)
                next_open = tomorrow.replace(hour=9, minute=30, second=13, microsecond=0)
                # If still before 9:30 today, use today
                today_open = est.replace(hour=9, minute=30, second=13, microsecond=0)
                if est < today_open:
                    next_open = today_open
                sleep_s = (next_open - est).total_seconds()
                print(f"  Outside hours — next check at {next_open.strftime('%a %H:%M:%S')}", flush=True)
                time.sleep(min(sleep_s, 600))
                continue

            # Determine if today's full post has been done
            state = load_state()
            today = today_str()
            full_post_today = state.get("last_full_post_date") == today
            needs_full = (not full_post_today) and is_nine_thirty_or_later()

            if needs_full:
                print(f"  9:30am full post for {today} — scraping all Zulu levels...", flush=True)
                delta_msgs = None
                full_msgs = None
                spx = None
                while delta_msgs is None:
                    try:
                        delta_msgs, full_msgs, spx = asyncio.run(scrape_once(force_full=True))
                        if delta_msgs is None:
                            print("  No data yet — retrying in 10s...", flush=True)
                            time.sleep(10)
                    except Exception as e:
                        print(f"  Retry after error: {e}", flush=True)
                        time.sleep(10)

                post_to_webhook(delta_msgs)
                paste_into_tv(full_msgs)
                save_state(spx, last_full_post_date=today)
                print(f"  Full post complete for {today}", flush=True)

            else:
                # Delta-only run — only post changed lines to webhook
                delta_msgs, full_msgs, _ = asyncio.run(scrape_once(force_full=False))
                if delta_msgs:
                    post_to_webhook(delta_msgs)
                    paste_into_tv(full_msgs)

        except Exception as e:
            print(f"  ERROR: {e}", flush=True)

        # Sleep to next :13 or :43 second mark (30s cycle)
        now = datetime.now()
        target_sec = 13
        current_sec = now.second + now.microsecond / 1_000_000
        if current_sec < target_sec:
            delay = target_sec - current_sec
        else:
            delay = 30 - (current_sec - target_sec) % 30
        time.sleep(delay)


if __name__ == "__main__":
    main()
