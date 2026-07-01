#!/usr/bin/env python3
"""Full test: open settings, click ZULU field, set value, click OK."""
import asyncio, json, urllib.request
BROWSER_PORT = 9223

def cdp_fetch(path):
    with urllib.request.urlopen(f'http://127.0.0.1:{BROWSER_PORT}{path}', timeout=5) as resp:
        return json.loads(resp.read().decode())

tabs = cdp_fetch('/json')
tv_tab = None
for t in tabs:
    if 'tradingview.com' in t.get('url','') and 'chart' in t.get('url',''):
        tv_tab = t; break

import websockets

async def main():
    ws_url = tv_tab['webSocketDebuggerUrl']
    async with websockets.connect(ws_url) as ws:
        async def cdp(method, params=None, rid=1):
            cmd = {"id": rid, "method": method}
            if params: cmd["params"] = params
            await ws.send(json.dumps(cmd))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == rid: return r

        async def eval_obj(js):
            r = await cdp("Runtime.evaluate", {"expression": js, "returnByValue": True})
            return r.get("result",{}).get("result",{}).get("value")

        await cdp("Page.enable")

        # 1. Open settings
        gear = await eval_obj("""
            (() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    const txt = ind.textContent;
                    if (txt.includes('v13.8') || txt.includes('v13.7') || txt.includes('v13.6') || txt.includes('Friday 13th')) {
                        let el = ind;
                        while (el && !el.className.includes('item') && !el.className.includes('study')) { el = el.parentElement; }
                        if (el) {
                            const btns = el.querySelectorAll('button');
                            for (const b of btns) {
                                if (b.getAttribute('aria-label') === 'Settings') {
                                    const r = b.getBoundingClientRect();
                                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                                }
                            }
                        }
                    }
                }
                return null;
            })()
        """)
        if not gear:
            print("FAIL: gear not found"); return
        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(3)
        print("1. Settings opened OK")

        # 2. Click inner-slot via CDP
        slot = await eval_obj("""
            (() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if ((el.textContent || '').trim() === 'ZULU Levels' && el.children.length === 0) {
                        let cell = el.parentElement;
                        while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) { cell = cell.parentElement; }
                        if (cell) {
                            const next = cell.nextElementSibling;
                            if (next) {
                                const s = next.querySelector('[class*="inner-slot"]');
                                if (s) { const r = s.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; }
                            }
                        }
                        break;
                    }
                }
                return null;
            })()
        """)
        if not slot:
            print("FAIL: ZULU slot not found"); return
        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": slot["x"], "y": slot["y"], "button": "left", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": slot["x"], "y": slot["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(2)
        print("2. ZULU field clicked OK")

        # 3. Find the visible INPUT and check it
        check = await eval_obj("""
            (() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if ((el.textContent || '').trim() === 'ZULU Levels' && el.children.length === 0) {
                        let cell = el.parentElement;
                        while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) { cell = cell.parentElement; }
                        if (cell) {
                            const next = cell.nextElementSibling;
                            if (next) {
                                const inp = next.querySelector('input[type=text]');
                                if (inp) {
                                    return {found: true, visible: inp.offsetParent !== null, value: inp.value.substring(0, 40), tag: inp.tagName};
                                }
                                // Also look for any input
                                const anyInput = next.querySelector('input');
                                return {found: false, hasAnyInput: !!anyInput, innerHTML: next.innerHTML.substring(0, 200)};
                            }
                        }
                        break;
                    }
                }
                return null;
            })()
        """)
        print(f"3. Check: {json.dumps(check, indent=2)}")

        if check and check.get("found") and check.get("visible"):
            # 4. Set value
            test_val = "NQ - Zulu Vol Lo 29941.82; Zulu Vol Hi 30203.58; Zulu OI Lo 29398.15; Zulu OI Hi 29999.99; ES - Zulu Vol Lo 7497.94; Zulu Vol Hi 7543.46; Zulu OI Lo 7352.52; Zulu OI Hi 7500.00"
            set_result = await eval_obj(f"""
                (() => {{
                    const val = {json.dumps(test_val)};
                    const all = document.querySelectorAll('*');
                    for (const el of all) {{
                        if ((el.textContent || '').trim() === 'ZULU Levels' && el.children.length === 0) {{
                            let cell = el.parentElement;
                            while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) {{ cell = cell.parentElement; }}
                            if (cell) {{
                                const next = cell.nextElementSibling;
                                if (next) {{
                                    const inp = next.querySelector('input[type=text]');
                                    if (inp) {{
                                        const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                        ns.call(inp, val);
                                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                        inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        return 'set, now=' + inp.value.substring(0, 60);
                                    }}
                                }}
                            }}
                            break;
                        }}
                    }}
                    return 'input not found';
                }})()
            """)
            print(f"4. Set result: {set_result}")

            await asyncio.sleep(1)

            # 5. Click OK
            ok = await eval_obj("""
                (() => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        const t = b.textContent.trim();
                        if (t === 'OK' || t === 'Apply') { b.click(); return 'clicked ' + t; }
                    }
                    return 'no ok';
                })()
            """)
            print(f"5. OK: {ok}")
        else:
            print("3. FAIL: no visible input found")

asyncio.run(main())
