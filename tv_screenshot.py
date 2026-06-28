"""
Screenshots JUST the last message in #regimebot Discord channel
in the Trump browser, expands any chart/embed, crops to message area, posts to webhook.
"""
import asyncio, json, os, sys, urllib.request, websockets, requests, base64, time
from datetime import datetime, timezone, timedelta

BROWSER_PORT = 9223
CHANNEL_URL = "https://discord.com/channels/921574741272317982/1299110315673387060"
WEBHOOK_URL = "https://discord.com/api/webhooks/1520138589747282010/X2buNs1fAZ9bTrfC2BAPd2gYoKzvfVY2G4jG2DMvXowYrw853-H9W7BWdLoK2hqKBF2M"
SCREENSHOT_PATH = os.path.join(os.path.dirname(__file__), "_screenshot.png")
STATE_FILE = os.path.join(os.path.dirname(__file__), "_last_image.txt")


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
    return 571 <= m < 960  # 9:31 = 571, 16:00 = 960


def cdp_fetch(path):
    url = f"http://127.0.0.1:{BROWSER_PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


async def run():
    tabs = cdp_fetch("/json")
    if not tabs:
        raise Exception("No tab list")

    # Find existing Discord tab or create one
    tab = None
    for t in tabs:
        url = t.get("url", "")
        if "921574741272317982" in url:
            tab = t
            break
    if not tab:
        for t in tabs:
            if "discord.com/channels" in t.get("url", ""):
                tab = t
                break
    if not tab:
        req = urllib.request.Request(f"http://127.0.0.1:{BROWSER_PORT}/json/new", method="PUT")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tab = json.loads(resp.read().decode())

    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise Exception("No WS URL")

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
                "expression": js,
                "returnByValue": True,
            })

        await cdp("Page.enable")
        current_url_result = await evaluate("window.location.href")
        current_url = current_url_result.get("result",{}).get("result",{}).get("value","")

        if CHANNEL_URL not in current_url:
            await cdp("Page.navigate", {"url": CHANNEL_URL})
            print("  Navigated to channel", flush=True)
            await asyncio.sleep(5)
        else:
            print("  Already on channel", flush=True)

        # Wait for messages to actually appear
        for _ in range(15):
            r = await evaluate("""
                document.querySelectorAll('[class*="message"]').length
            """)
            count = r.get("result",{}).get("result",{}).get("value", 0)
            print(f"  Messages: {count}", flush=True)
            if count > 1:
                break
            await asyncio.sleep(2)

        # Find the last VISIBLE message — scroll to bottom
        r = await evaluate("""
            (() => {
                // Scroll chat scroller to bottom
                const scroller = document.querySelector('[class*="scroller__36d07"]');
                if (scroller) {
                    scroller.scrollTop = scroller.scrollHeight;
                }

                // Click any show-more/expand buttons on visible messages
                document.querySelectorAll('[class*="showMore"], [class*="spoiler"], [aria-label*="Show"]')
                    .forEach(b => b.click());

                // Click embed images on the last visible message
                const allMsgs = document.querySelectorAll('[class*="message"]');
                const visibleMsgs = Array.from(allMsgs).filter(m => window.getComputedStyle(m).display !== 'none');
                const last = visibleMsgs[visibleMsgs.length - 1];
                if (last) {
                    last.querySelectorAll('img[class*="embed"], [class*="media"] img, [class*="imageWrapper"] img, [class*="embed"] img')
                        .forEach(e => e.click());
                    return JSON.stringify({id: last.id, tag: last.tagName});
                }
                return JSON.stringify({error: 'no visible messages'});
            })()
        """)
        info = json.loads(r.get("result",{}).get("result",{}).get("value","{}"))
        print(f"  Last visible: {info}", flush=True)
        if info.get("error"):
            raise Exception(info["error"])

        await asyncio.sleep(3)

        # Get the direct image URL from the last message's attachment
        r2 = await evaluate("""
            (() => {
                const allMsgs = document.querySelectorAll('[class*="message"]');
                const visible = Array.from(allMsgs).filter(m => window.getComputedStyle(m).display !== 'none');
                const last = visible[visible.length - 1];
                if (!last) return '';

                // Find the full-size image link (attachments or media)
                const img = last.querySelector('a[href*="cdn.discordapp.com/attachments"]');
                if (img) return img.href;

                const img2 = last.querySelector('a[href*="media.discordapp.net"]');
                if (img2) return img2.href;

                const img3 = last.querySelector('img[src*="cdn.discordapp"]');
                if (img3) return img3.src;

                return '';
            })()
        """)
        img_url = r2.get("result",{}).get("result",{}).get("value","")
        print(f"  Image URL: {img_url[:80] if img_url else 'none'}", flush=True)

        if not img_url:
            raise Exception("No image URL found in last message")

        # Dedup: skip if same URL as last run
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                last_url = f.read().strip()
            if last_url == img_url:
                print(f"  No new image — skipping (same as last run)", flush=True)
                return

        with open(STATE_FILE, "w") as f:
            f.write(img_url)

        # Download the full-resolution image directly
        import urllib.request
        req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(SCREENSHOT_PATH, "wb") as f:
                f.write(resp.read())
        print(f"  Downloaded image ({os.path.getsize(SCREENSHOT_PATH)}b)", flush=True)

        # Blackout "gex bot" text and logo area (above 1st chart column)
        try:
            from PIL import Image, ImageDraw
            import numpy as np
            img = Image.open(SCREENSHOT_PATH).convert("RGB")
            arr = np.array(img)
            w = arr.shape[1]
            # Find bright text pixels in top-left area (gex bot branding)
            left_top = arr[:300, :w//2, :]
            bright_mask = left_top.max(axis=2) > 100
            # Find rows with significant text content (>= 20 bright pixels)
            text_rows = bright_mask.sum(axis=1) >= 20
            if text_rows.any():
                y_start = int(np.where(text_rows)[0][0])
                y_end = int(np.where(text_rows)[0][-1])
                # Find x bounds of this text
                bright_cols = bright_mask[text_rows].any(axis=0)
                col_indices = np.where(bright_cols)[0]
                x_start = int(col_indices[0])
                x_end = int(col_indices[-1])
                # Sample background color from just outside the text area
                sample_y = min(y_start + 5, arr.shape[0] - 1)
                sample_x_left = max(0, x_start - 50)
                sample_x_right = min(arr.shape[1] - 1, x_end + 50)
                # Sample from both sides of the text to get background color
                left_sample = arr[sample_y, sample_x_left:x_start, :]
                right_sample = arr[sample_y, x_end:sample_x_right, :]
                if len(left_sample) > 0 and len(right_sample) > 0:
                    bg_color = tuple(int(c) for c in np.concatenate([left_sample, right_sample]).mean(axis=0))
                elif len(left_sample) > 0:
                    bg_color = tuple(int(c) for c in left_sample.mean(axis=0))
                elif len(right_sample) > 0:
                    bg_color = tuple(int(c) for c in right_sample.mean(axis=0))
                else:
                    bg_color = (28, 28, 28)
                # Black out the region with padding
                pad_x = max(20, (x_end - x_start) // 4)
                pad_y = max(5, (y_end - y_start) // 2) + 70
                draw = ImageDraw.Draw(img)
                draw.rectangle(
                    [x_start - pad_x, y_start - pad_y, x_end + pad_x, y_end + pad_y],
                    fill=bg_color
                )
                img.save(SCREENSHOT_PATH)
                print(f"  Blacked out gexbot text at x={x_start}-{x_end}, y={y_start}-{y_end}", flush=True)
            else:
                print("  No text found to blackout", flush=True)
        except Exception as e:
            print(f"  Blackout skipped: {e}", flush=True)

        return SCREENSHOT_PATH


def post_to_discord(path):
    if not os.path.exists(path):
        raise Exception("No file")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "rb") as f:
        r = requests.post(
            WEBHOOK_URL,
            files={"file": ("regimebot.png", f, "image/png")},
            data={"content": f"**#regimebot** — {ts} EST"},
            timeout=30,
        )

    if r.status_code in [200, 204]:
        print(f"  Posted: {ts}", flush=True)
    else:
        print(f"  Failed: {r.status_code} {r.text[:200]}", flush=True)
        sys.exit(1)


def main():
    if not is_market_hours_est():
        print("Outside hours — skip", flush=True)
        return

    print(f"Start: {datetime.now()}", flush=True)

    # Retry loop: keep trying until image arrives (up to ~2 min)
    max_retries = 12
    for attempt in range(1, max_retries + 1):
        try:
            p = asyncio.run(run())
            if p:
                post_to_discord(p)
                return  # success — done
            else:
                print(f"  No new image (attempt {attempt}/{max_retries})", flush=True)
        except Exception as e:
            print(f"  Attempt {attempt}/{max_retries} failed: {e}", flush=True)

        if attempt < max_retries:
            time.sleep(10)

    print("  Max retries reached — will try again next cycle", flush=True)


if __name__ == "__main__":
    main()
