#!/usr/bin/env python3
"""Try to set Zulu levels via TV internal API."""
import asyncio, json, urllib.request
BROWSER_PORT = 9223

def cdp_fetch(path):
    with urllib.request.urlopen(f'http://127.0.0.1:{BROWSER_PORT}{path}', timeout=5) as resp:
        return json.loads(resp.read().decode())

tabs = cdp_fetch('/json')
tv_tab = None
for t in tabs:
    if 'tradingview.com' in t.get('url','') and 'chart' in t.get('url',''):
        tv_tab = t
        break

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

        async def safe_eval(js):
            r = await cdp("Runtime.evaluate", {"expression": js, "returnByValue": True})
            return r.get("result",{}).get("result",{}).get("value")

        await cdp("Page.enable")

        test_val = "NQ - Zulu Vol Lo 11111; Zulu Vol Hi 22222; Zulu OI Lo 33333; Zulu OI Hi 44444; ES - Zulu Vol Lo 5555; Zulu Vol Hi 6666; Zulu OI Lo 7777; Zulu OI Hi 8888"
        # Escape for JS string
        test_val_esc = test_val.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

        raw = await safe_eval(f"""
            (() => {{
                try {{
                    const widget = widgetbar.chartWidgetCollection.activeChartWidget.value();
                    const model = widget.model();
                    const ds = model.dataSources();
                    const source5 = ds[5];
                    const inputs = source5.inputs();
                    const result = {{}};

                    // Try _tryChangeInputs
                    try {{
                        if (typeof source5._tryChangeInputs === 'function') {{
                            source5._tryChangeInputs('in_52', '{test_val_esc}');
                            result.tryChange = 'OK';
                        }} else {{
                            result.tryChange = 'not a function';
                        }}
                    }} catch(e) {{
                        result.tryChange = 'error: ' + e.message;
                    }}

                    // Try _changeInputsImpl
                    try {{
                        if (typeof source5._changeInputsImpl === 'function') {{
                            source5._changeInputsImpl({{'in_52': '{test_val_esc}'}});
                            result.changeImpl = 'OK';
                        }} else {{
                            result.changeImpl = 'not a function';
                        }}
                    }} catch(e) {{
                        result.changeImpl = 'error: ' + e.message;
                    }}

                    // Check in_52 type
                    result.in_52_type = typeof inputs.in_52;
                    result.in_52_has_v = 'v' in (inputs.in_52 || {{}});

                    return JSON.stringify(result);
                }} catch(e) {{
                    return JSON.stringify({{error: e.message}});
                }}
            }})()
        """)
        print(f"Result: {raw[:1000]}")

        await asyncio.sleep(2)

        r2 = await safe_eval("""
            JSON.stringify((() => {
                try {
                    const widget = widgetbar.chartWidgetCollection.activeChartWidget.value();
                    const model = widget.model();
                    const ds = model.dataSources();
                    const source5 = ds[5];
                    const inp = source5.inputs();
                    const raw = inp.in_52;
                    return {in_52: typeof raw === 'string' ? raw.substring(0, 80) : JSON.stringify(raw).substring(0, 80)};
                } catch(e) {
                    return {error: e.message};
                }
            })())
        """)
        print(f"After: {r2[:500]}")

asyncio.run(main())
