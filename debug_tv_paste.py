"""Debug TV paste - step by step."""
import sys, os, json, urllib.request, asyncio
sys.path.insert(0, os.path.dirname(__file__))

BROWSER_PORT = 9223

def cdp_fetch(path):
    url = f"http://127.0.0.1:{BROWSER_PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"CDP fetch error: {e}")
        return None

# Find TV tab
tabs = cdp_fetch("/json")
if not tabs:
    print("No tabs")
    sys.exit(1)

tv_tab = None
for t in tabs:
    url = t.get("url", "")
    if "tradingview.com" in url and "chart" in url:
        tv_tab = t
        print(f"Found TV tab: {t.get('title','')[:60]}")
        break

if not tv_tab:
    print("No TV tab found")
    # Show all tabs
    for t in tabs:
        print(f"  {t.get('url','')[:80]}")
    sys.exit(1)

# Connect via CDP
import websockets

async def debug_paste():
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

        # Step 1: Find indicator in legend
        r = await evaluate("""
            (() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                const results = [];
                for (const ind of indicators) {
                    results.push(ind.textContent.trim().substring(0, 50));
                }
                return results.length ? results : 'no indicators found';
            })()
        """)
        result_val = r.get("result", {}).get("result", {}).get("value", "N/A")
        print(f"Step 1 - Indicators in legend: {result_val}")

        # Step 2: Try clicking v13.8
        r = await evaluate("""
            (() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    const txt = ind.textContent;
                    if (txt.includes('v13.8') || txt.includes('v13.7') || txt.includes('v13.6') || txt.includes('Friday 13th')) {
                        ind.click();
                        return 'CLICKED: ' + txt.trim().substring(0, 60);
                    }
                }
                return 'not found';
            })()
        """)
        result_val = r.get("result", {}).get("result", {}).get("value", "N/A")
        print(f"Step 2 - Indicator click: {result_val}")

        await asyncio.sleep(2)

        # Step 3: Look for ZULU textarea
        r = await evaluate("""
            (() => {
                const tas = document.querySelectorAll('textarea');
                const results = [];
                for (const ta of tas) {
                    const pt = (ta.closest('[class*="row"]') || ta.parentElement)?.textContent || '';
                    results.push({hasZulu: pt.includes('ZULU') || pt.includes('Zulu'), parentText: pt.trim().substring(0, 80), taValue: ta.value.substring(0, 50)});
                }
                return results;
            })()
        """)
        result_val = r.get("result", {}).get("result", {}).get("value", "N/A")
        print(f"Step 3 - Textareas on page: {json.dumps(result_val, indent=2)[:500]}")

        # Step 4: Look for OK/Apply buttons
        r = await evaluate("""
            (() => {
                const btns = document.querySelectorAll('button');
                const results = [];
                for (const b of btns) {
                    results.push(b.textContent.trim().substring(0, 30));
                }
                return results;
            })()
        """)
        result_val = r.get("result", {}).get("result", {}).get("value", "N/A")
        print(f"Step 4 - Buttons on page: {result_val}")

asyncio.run(debug_paste())
