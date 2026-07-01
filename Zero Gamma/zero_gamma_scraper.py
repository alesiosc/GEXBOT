"""Grab the latest Zero Gamma chart image from Discord and post to webhook every 10 min."""
import asyncio, json, os, sys, urllib.request, requests, time
from datetime import datetime, timezone, timedelta

BROWSER_PORT = 9223
CHANNEL_ID = "1346859946511171695"
GUILD_ID = "921574741272317982"
CHANNEL_URL = f"https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}"
WEBHOOK_URL = "https://discord.com/api/webhooks/1520747286899200131/yIW5Z1hEhgQAYSULfyFWO637puh7XWRn8troSTI-yzUFvJzEC8_m0zEoW5XTsWhs70QM"
STATE_FILE = os.path.join(os.path.dirname(__file__), "_last_zero_gamma.txt")
DOWNLOAD_PATH = os.path.join(os.path.dirname(__file__), "_zero_gamma.png")


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


def cdp_fetch(path):
    url = f"http://127.0.0.1:{BROWSER_PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


async def scrape_once():
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
            print("  Navigated to Zero Gamma channel", flush=True)
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

        # Get the best image URL from the last message
        r = await evaluate("""
            (() => {
                const wrappers = document.querySelectorAll('[class*="messageListItem"]');
                const last = wrappers[wrappers.length - 1];
                if (!last) return '';

                const cdnLinks = last.querySelectorAll('a[href*="cdn.discordapp.com/attachments"]');
                for (const a of cdnLinks) return a.href;

                const mediaLinks = last.querySelectorAll('a[href*="media.discordapp.net"]');
                for (const a of mediaLinks) return a.href;

                const imgs = last.querySelectorAll('img[src*="discordapp"]');
                for (const img of imgs) return img.src;

                return '';
            })()
        """)
        img_url = r.get("result", {}).get("result", {}).get("value", "")
        if not img_url:
            raise Exception("No image found in last message")

        print(f"  Image: {img_url[:80]}...", flush=True)

        # Dedup
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                if f.read().strip() == img_url:
                    print("  No new image — skipping", flush=True)
                    return None

        with open(STATE_FILE, "w") as f:
            f.write(img_url)

        # Download
        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(DOWNLOAD_PATH, "wb") as f:
                f.write(resp.read())
        print(f"  Downloaded ({os.path.getsize(DOWNLOAD_PATH)}b)", flush=True)

        return DOWNLOAD_PATH


def post_to_discord(path):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "rb") as f:
        r = requests.post(
            WEBHOOK_URL,
            files={"file": ("zero_gamma.png", f, "image/png")},
            data={"content": f"**Zero Gamma** — {ts} EST"},
            timeout=30,
        )

    if r.status_code in [200, 204]:
        print(f"  Posted: {ts}", flush=True)
    else:
        print(f"  Failed: {r.status_code} {r.text[:200]}", flush=True)
        sys.exit(1)


def main():
    # Prevent duplicate instances
    try:
        from pid_lock import PIDLock
        lock = PIDLock("zero_gamma_scraper")
        if not lock.acquire():
            return
    except ImportError:
        pass

    print(f"Zero Gamma watcher started at {datetime.now()}", flush=True)

    # Align first run to next :13 second mark
    now = datetime.now()
    target_sec = 13
    current_sec = now.second + now.microsecond / 1_000_000
    if current_sec < target_sec:
        delay = target_sec - current_sec
    else:
        delay = (300 - (current_sec - target_sec) % 300) % 300
    print(f"  First check in {delay:.1f}s (aligning to :13)", flush=True)
    time.sleep(delay)

    first_run = True

    while True:
        try:
            if not is_market_hours_est():
                now_utc = datetime.now(timezone.utc)
                est = now_utc - timedelta(hours=4 if 4 <= now_utc.month <= 10 else 5)
                tomorrow = est + timedelta(days=1)
                next_open = tomorrow.replace(hour=9, minute=30, second=13, microsecond=0)
                today_open = est.replace(hour=9, minute=30, second=13, microsecond=0)
                if est < today_open:
                    next_open = today_open
                sleep_s = (next_open - est).total_seconds()
                print(f"  Outside hours — next at {next_open.strftime('%a %H:%M:%S')}", flush=True)
                time.sleep(min(sleep_s, 600))
                continue

            if first_run:
                print("  First run — retrying until image arrives...", flush=True)
                result = None
                while result is None:
                    try:
                        result = asyncio.run(scrape_once())
                        if result is None:
                            print("  No image yet — retry in 10s...", flush=True)
                            time.sleep(10)
                    except Exception as e:
                        print(f"  Retry after: {e}", flush=True)
                        time.sleep(10)

                post_to_discord(result)
                first_run = False

            # Normal 10-min checks
            result = asyncio.run(scrape_once())
            if result:
                post_to_discord(result)

        except Exception as e:
            print(f"  ERROR: {e}", flush=True)

        # Sleep to next :13 mark (5 min cycle)
        now = datetime.now()
        target_sec = 13
        current_sec = now.second + now.microsecond / 1_000_000
        if current_sec < target_sec:
            delay = target_sec - current_sec
        else:
            delay = 300 - (current_sec - target_sec) % 300
        time.sleep(delay)


if __name__ == "__main__":
    main()
