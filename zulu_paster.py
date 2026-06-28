"""Watch zulu_levels.txt for changes and auto-paste into TradingView indicator settings."""
import asyncio, json, os, time, hashlib
from datetime import datetime
import urllib.request, websockets

BROWSER_PORT = 9223
LEVELS_FILE = os.path.join(os.path.dirname(__file__), "zulu_levels.txt")
STATE_HASH_FILE = os.path.join(os.path.dirname(__file__), "_zulu_paste_hash.txt")


def file_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return ""


def cdp_fetch(path):
    url = "http://127.0.0.1:{}{}".format(BROWSER_PORT, path)
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except:
        return None


async def paste_via_dialog(new_text):
    tabs = cdp_fetch("/json")
    if not tabs:
        raise Exception("No browser tabs")

    tv_tab = None
    for t in tabs:
        url = t.get("url", "")
        if "tradingview.com" in url and "chart" in url:
            tv_tab = t
            break
    if not tv_tab:
        raise Exception("No TradingView chart tab found")

    ws_url = tv_tab["webSocketDebuggerUrl"]
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
        await asyncio.sleep(1)

        # Click indicator name in legend
        r = await evaluate("""
            (() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    if (ind.textContent.includes('v13.6') || ind.textContent.includes('Friday 13th')) {
                        ind.click();
                        return 'clicked legend';
                    }
                }
                const gearButtons = document.querySelectorAll('[class*="gear"], [class*="settings"], [class*="configure"]');
                for (const g of gearButtons) {
                    if (g.offsetParent !== null) {
                        g.click();
                        return 'clicked gear';
                    }
                }
                return 'no target found';
            })()
        """)
        print("  " + r.get("result", {}).get("result", {}).get("value", ""), flush=True)
        await asyncio.sleep(2)

        # Build the JS to find and update the ZULU Levels input
        escaped = new_text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

        find_and_set_js = (
            "(() => {"
            "const textareas = document.querySelectorAll('textarea');"
            "for (const ta of textareas) {"
            "const parentText = (ta.closest('[class*=\"row\"]') || ta.parentElement)?.textContent || '';"
            "if (parentText.includes('ZULU') || parentText.includes('Zulu')) {"
            "const ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;"
            "ns.call(ta, '" + escaped + "');"
            "ta.dispatchEvent(new Event('input', { bubbles: true }));"
            "ta.dispatchEvent(new Event('change', { bubbles: true }));"
            "return 'found textarea and set';"
            "}}"
            "const inputs = document.querySelectorAll('input:not([type=\"hidden\"])');"
            "for (const inp of inputs) {"
            "const parentText = (inp.closest('[class*=\"row\"]') || inp.parentElement)?.textContent || '';"
            "if (parentText.includes('ZULU') || parentText.includes('Zulu')) {"
            "const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
            "ns.call(inp, '" + escaped + "');"
            "inp.dispatchEvent(new Event('input', { bubbles: true }));"
            "inp.dispatchEvent(new Event('change', { bubbles: true }));"
            "return 'found input and set';"
            "}}"
            "return 'no ZULU field found';"
            "})()"
        )

        r = await evaluate(find_and_set_js)
        print("  " + r.get("result", {}).get("result", {}).get("value", ""), flush=True)
        await asyncio.sleep(1)

        # Click Apply/OK
        r = await evaluate("""
            (() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const t = b.textContent.trim();
                    if (t === 'OK' || t === 'Apply') {
                        b.click();
                        return 'clicked ' + t;
                    }
                }
                return 'no OK/Apply';
            })()
        """)
        print("  " + r.get("result", {}).get("result", {}).get("value", ""), flush=True)


def main():
    print("Zulu paster started at {}".format(datetime.now()), flush=True)
    print("  Watching: {}".format(LEVELS_FILE), flush=True)
    print("  Save changes to zulu_levels.txt -- auto-injected into TV indicator.", flush=True)

    last_hash = ""
    if os.path.exists(STATE_HASH_FILE):
        with open(STATE_HASH_FILE) as f:
            last_hash = f.read().strip()

    if not os.path.exists(LEVELS_FILE):
        with open(LEVELS_FILE, "w") as f:
            f.write("")
        print("  Created empty " + LEVELS_FILE, flush=True)

    while True:
        try:
            current_hash = file_hash(LEVELS_FILE)
            if current_hash and current_hash != last_hash:
                with open(LEVELS_FILE) as f:
                    content = f.read().strip()
                if content:
                    print("  Change at " + datetime.now().strftime('%H:%M:%S'), flush=True)
                    print("  Content: " + content[:80] + "...", flush=True)
                    try:
                        asyncio.run(paste_via_dialog(content))
                        last_hash = current_hash
                        with open(STATE_HASH_FILE, "w") as f:
                            f.write(current_hash)
                    except Exception as e:
                        print("  PASTE ERROR: " + str(e), flush=True)
        except Exception as e:
            print("  ERROR: " + str(e), flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
