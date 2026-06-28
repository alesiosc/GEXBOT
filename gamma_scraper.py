"""Scrape SPX Gamma from Discord every 2 min. Only posts changed rows."""
import asyncio, json, os, sys, urllib.request, requests, time
from datetime import datetime, timezone, timedelta

BROWSER_PORT = 9223
CHANNEL_ID = "1027647733219209227"
GUILD_ID = "921574741272317982"
CHANNEL_URL = f"https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}"
WEBHOOK_URL = "https://discord.com/api/webhooks/1520500109547274300/VsWwcaGAO5FHST6Z3QCFYPjZiQDk0hvIUyhnhtaRpW9SKdcQUGTwX-humqYDNx98VtKK"
STATE_FILE = os.path.join(os.path.dirname(__file__), "_zulu_state.json")


def is_market_hours_est():
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        now = datetime.now(tz)
    except ImportError:
        now_utc = datetime.now(timezone.utc)
        if 4 <= now_utc.month <= 10:
            now = now_utc - timedelta(hours=4)
        else:
            now = now_utc - timedelta(hours=5)
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return 570 <= m < 960  # 9:30 – 16:00 EST


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def cdp_fetch(path):
    url = f"http://127.0.0.1:{BROWSER_PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
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


async def scrape_once(full=False):
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

        # Parse SPX Gamma table
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

        spx_price, nq_price, es_price = get_prices()
        nq_ratio = nq_price / spx_price
        es_ratio = es_price / spx_price

        # Build current levels dictionary (ticker + name -> price)
        key_map = [
            ("Major Negative by Volume", "Zulu Vol Lo"),
            ("Major Positive by Volume", "Zulu Vol Hi"),
            ("Major Negative by OI", "Zulu OI Lo"),
            ("Major Positive by OI", "Zulu OI Hi"),
        ]
        current = {}
        for spx_key, name in key_map:
            if spx_key in spx_levels:
                current[f"NQ|{name}"] = round(spx_levels[spx_key] * nq_ratio, 2)
                current[f"ES|{name}"] = round(spx_levels[spx_key] * es_ratio, 2)

        if not current:
            raise Exception("No major levels found")

        # Compare with previous state
        previous = load_state()
        changed = {}
        for key, val in current.items():
            prev = previous.get(key)
            if full or prev is None or abs(prev - val) > 0.001:
                changed[key] = val

        if not changed:
            print(f"  No changes at {datetime.now().strftime('%H:%M:%S')}", flush=True)
            return None

        # Extract ticker and name from key
        nq_rows, es_rows = [], []
        for key, val in changed.items():
            ticker, name = key.split("|", 1)
            row = f"{name} {val}"
            if ticker == "NQ":
                nq_rows.append(row)
            else:
                es_rows.append(row)

        result = []
        if nq_rows:
            result.append(("NQ", "NQ - " + "; ".join(nq_rows)))
        if es_rows:
            result.append(("ES", "ES - " + "; ".join(es_rows)))

        # Save new state
        save_state(current)
        return result


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

                async def evaluate(js):
                    return await cdp("Runtime.evaluate", {
                        "expression": js, "returnByValue": True,
                    })

                await cdp("Page.enable")
                await asyncio.sleep(1)

                # Click indicator in legend
                r = await evaluate("""
                    (() => {
                        const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                        for (const ind of indicators) {
                            if (ind.textContent.includes('v13.6') || ind.textContent.includes('Friday 13th')) {
                                ind.click();
                                return 'clicked';
                            }
                        }
                        return 'not found';
                    })()
                """)
                await asyncio.sleep(2)

                # Find and set ZULU Levels input
                escaped = combined.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
                js = (
                    "(() => {"
                    "const tas = document.querySelectorAll('textarea');"
                    "for (const ta of tas) {"
                    "const pt = (ta.closest('[class*=\"row\"]') || ta.parentElement)?.textContent || '';"
                    "if (pt.includes('ZULU') || pt.includes('Zulu')) {"
                    "const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;"
                    "ns.call(ta, '" + escaped + "');"
                    "ta.dispatchEvent(new Event('input', {bubbles: true}));"
                    "ta.dispatchEvent(new Event('change', {bubbles: true}));"
                    "return 'set';"
                    "}}"
                    "return 'not found';"
                    "})()"
                )
                await evaluate(js)
                await asyncio.sleep(1)

                # Click Apply
                await evaluate("""
                    (() => {
                        const btns = document.querySelectorAll('button');
                        for (const b of btns) {
                            const t = b.textContent.trim();
                            if (t === 'OK' || t === 'Apply') { b.click(); return 'ok'; }
                        }
                        return 'no ok';
                    })()
                """)
                print(f"  TV injected: {combined[:80]}...", flush=True)

        asyncio.run(_do_paste())
    except Exception as e:
        print(f"  TV paste error: {e}", flush=True)


def main():
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

    # First run of the day: full scrape with retry
    first_run = True

    while True:
        try:
            if not is_market_hours_est():
                # Sleep until next market open (9:30)
                now_utc = datetime.now(timezone.utc)
                est = now_utc - timedelta(hours=4 if 4 <= now_utc.month <= 10 else 5)
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

            # First run of the day: full scrape with retry
            if first_run:
                print("  First run — doing full scrape with retry...", flush=True)
                result = None
                while result is None:
                    try:
                        result = asyncio.run(scrape_once(full=True))
                        if result is None:
                            print("  No data yet — retrying in 10s...", flush=True)
                            time.sleep(10)
                    except Exception as e:
                        print(f"  Retry after error: {e}", flush=True)
                        time.sleep(10)

                post_to_webhook(result)
                paste_into_tv(result)
                first_run = False

            # Normal incremental runs
            result = asyncio.run(scrape_once(full=False))
            if result:
                post_to_webhook(result)
                paste_into_tv(result)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)

        # Sleep to next :13 second mark
        now = datetime.now()
        target_sec = 13
        current_sec = now.second + now.microsecond / 1_000_000
        if current_sec < target_sec:
            delay = target_sec - current_sec
        else:
            delay = 120 - (current_sec - target_sec) % 120
        time.sleep(delay)


if __name__ == "__main__":
    main()
