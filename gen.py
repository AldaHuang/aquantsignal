"""Generate now.html — all content server-rendered, minimal JS for tab switching only."""
import json
from datetime import date

with open("reports/tracker.json") as f:
    D = json.load(f)

v = (D.get("_version") or "?")[:16]
picks = (D.get("records") or [{}])[-1].get("picks", [])
pp = D.get("paper", {})
weights = D.get("strategy_weights", {})
mr = D.get("market_regime", {})
bm = D.get("benchmark", {})
clog = D.get("changelog", "")

def esc(s):
    if not s: return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ── Build static HTML sections ──

# Recommend
rec_html = ""
for p in picks:
    vd = p.get("verdict", "观望")
    tc = "tg-b" if vd == "买入" else "tg-s"
    rs = " · ".join([r for r in p.get("reasons", []) if "止损" not in r][:2])
    rec_html += f'<div class=cd><div class=r><span class=nm>{esc(p["name"])} <span style=font-size:11px;color:#666>{p["symbol"]}</span></span><span style=font-size:15px;font-weight:600>¥{p["price"]:.2f}</span></div>'
    rec_html += f'<div class=r style=margin-top:4px><span style=font-size:12px;color:#666>评分 <b style=color:#d47800>{p["score"]}</b>/100</span><span class="tg {tc}">{esc(vd)}</span></div>'
    if rs: rec_html += f'<div style=font-size:12px;color:#666;margin-top:4px;padding-top:4px;border-top:1px solid rgba(255,255,255,.04)>{esc(rs)}</div>'
    if p.get("stop_loss"): rec_html += f'<div class=tp>止损 ¥{p["stop_loss"]:.2f} | 止盈 ¥{p.get("take_profit",0):.2f} | 仓位 {p.get("position_pct",0)}%</div>'
    rec_html += "</div>"
if not rec_html: rec_html = '<div class=emp>暂无推荐</div>'

# Plan
plan_html = ""
buys = [p for p in picks if p.get("verdict") in ("买入", "关注")]
if buys:
    plan_html = '<table style=width:100%;border-collapse:collapse;font-size:12px><tr style=font-size:10px;color:#666><th style=padding:6px 4px>股票</th><th style=padding:6px 4px>买入</th><th style=padding:6px 4px>止损</th><th style=padding:6px 4px>止盈</th><th style=padding:6px 4px>仓位</th><th style=padding:6px 4px>风险</th></tr>'
    for p in buys:
        plan_html += f'<tr><td style=padding:7px 4px;font-weight:600>{esc(p["name"])}</td><td style=padding:7px 4px>¥{p.get("entry",p.get("price",0)):.2f}</td><td style=padding:7px 4px;color:#c0392b>¥{p.get("stop_loss",0):.2f}</td><td style=padding:7px 4px;color:#27ae60>¥{p.get("take_profit",0):.2f}</td><td style=padding:7px 4px>{p.get("position_pct",0)}%</td><td style=padding:7px 4px>{p.get("risk_pct",0):.1f}%</td></tr>'
    plan_html += "</table>"
else:
    plan_html = '<div class=emp>暂无买入信号</div>'

# Paper
eq = pp.get("equity", 50000)
init = pp.get("initial_cash", 50000)
ret = (eq - init) / init * 100
c = "#c0392b" if ret >= 0 else "#27ae60"
paper_html = f'<div class=cd><div class=r><span style=color:#666>总资产</span><span style=font-size:36px;font-weight:700;color:{c}>¥{eq:,.0f}</span></div>'
paper_html += f'<div class=stats><span class=lb>收益率</span><span class=vl style=color:{c}>{ret:+.1f}%</span><span class=lb>可用现金</span><span class=vl>¥{pp.get("cash",0):,.0f}</span><span class=lb>持仓</span><span class=vl>{pp.get("positions",0)} 只</span><span class=lb>交易</span><span class=vl>{pp.get("total_trades",0)} 笔</span></div>'
if bm.get("return_pct") is not None:
    bmr = bm["return_pct"]
    cb = "#c0392b" if bmr >= 0 else "#27ae60"
    df = ret - bmr
    cd = "#c0392b" if df > 0 else "#27ae60"
    paper_html += f'<div style=display:flex;justify-content:space-between;padding:4px 8px;font-size:12px;background:rgba(255,255,255,.03);border-radius:4px><span style=color:#666>vs {esc(bm.get("name","CSI300"))}</span><span style=color:{cb}>{bmr:+.1f}%</span><span style=font-weight:600;color:{cd}>超额 {df:+.1f}%</span></div>'
paper_html += "</div>"

for pos in pp.get("positions_list", []):
    pc = "#c0392b" if pos.get("pnl_pct", 0) >= 0 else "#27ae60"
    paper_html += f'<div class=cd><div class=r><span class=nm>{esc(pos["name"])}</span><span style=font-size:14px;font-weight:600;color:{pc}>{pos.get("pnl_pct",0):+.1f}%</span></div><div class=dt>{pos["shares"]}股 | 成本¥{pos.get("avg_cost",0):.2f} → 现¥{pos.get("current_price",0):.2f} | 市值¥{pos.get("market_value",0):,.0f}</div></div>'

hist = pp.get("history", [])
if hist:
    paper_html += '<h3>已平仓</h3>'
    for t in reversed(hist[-10:]):
        cc = "#c0392b" if t.get("pnl", 0) >= 0 else "#27ae60"
        paper_html += f'<div class=cd><div class=r><span class=nm>{esc(t.get("name",t.get("symbol","")))})</span><span style=font-size:16px;font-weight:700;color:{cc}>¥{t.get("pnl",0):+.0f}</span></div><div class=dt>{t.get("shares","")}股 | 买¥{t.get("entry_price",0):.2f} → 卖¥{t.get("exit_price",0):.2f} | {esc(t.get("reason",""))}</div></div>'

# Log
log_html = '<h3>策略权重</h3>'
for k in sorted(weights.keys()):
    w = weights[k]
    log_html += f'<div class=wr><span class=lb>{k}</span><span class=bar><span style=display:block;height:100%;border-radius:2px;background:#d47800;width:{min(100,w/1.5*100):.0f}%></span></span><span>{w:.2f}</span></div>'

if mr.get("regime"):
    rl = {"trending": "趋势", "ranging": "震荡", "mixed": "混合"}
    log_html += f'<h3>市场状态</h3><div class=cd style=padding:8px 12px;font-size:13px>{rl.get(mr["regime"], mr["regime"])} (强度 {mr.get("strength",50)})</div>'

if clog:
    log_html += '<h3>更新日志</h3>'
    sections = clog.split("\n## ")
    for sec in sections[:6]:
        if not sec.strip(): continue
        lines = sec.split("\n")
        d = lines[0][3:] if lines[0].startswith("## ") else lines[0]
        log_html += f'<div class=lg-day><div class=dt>📅 {esc(d)}</div>'
        for l in lines[1:]:
            if l.startswith("### "): log_html += f'<div style=font-size:11px;color:#ccc;margin:6px 0 2px>{esc(l[4:])}</div>'; continue
            if l.startswith("---"): continue
            if l.startswith("- "):
                t = l[2:].strip(); cls = "lg-item"
                if "新增" in t: cls += " lg-add"
                elif "移除" in t: cls += " lg-rm"
                elif "持续" in t: cls += " lg-st"
                log_html += f'<div class="{cls}">{esc(t)}</div>'
            elif l.strip():
                log_html += f'<div style=font-size:10px;color:#666;padding:1px 0>{esc(l)}</div>'
        log_html += "</div>"


HTML = f'''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>aquant</title>
<style>
:root{{--bg:#0a0a0a;--s1:#141414;--s2:#1c1c1c;--bd:#2a2a2a;--tx:#c8c8c8;--dim:#666;--up:#c0392b;--dn:#27ae60;--ac:#d47800}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--tx);max-width:480px;margin:0 auto;padding:0 12px 40px;min-height:100vh}}
h3{{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;font-weight:500;margin:16px 0 6px}}
.hd{{display:flex;justify-content:space-between;align-items:flex-end;padding:16px 0 8px;border-bottom:1px solid var(--bd);margin-bottom:12px}}
.hd .logo{{font-size:18px;font-weight:700;color:#fff}}.hd .logo em{{font-style:normal;color:var(--ac)}}
.hd .ts{{font-size:11px;color:var(--dim);font-family:monospace}}
.nv{{display:flex;gap:4px;margin:10px 0 14px}}
.nv span{{flex:1;text-align:center;padding:9px 0;border-radius:6px;font-size:13px;color:var(--dim);cursor:pointer}}
.nv span.on{{background:var(--s2);color:#fff;font-weight:600}}
.cd{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:12px;margin:6px 0}}
.cd .r{{display:flex;justify-content:space-between;align-items:center}}
.cd .nm{{font-size:15px;font-weight:600;color:#fff}}
.tg{{display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600}}
.tg-b{{background:rgba(192,57,43,.15);color:var(--up)}}.tg-s{{background:rgba(39,174,96,.12);color:var(--dn)}}
.tp{{font-family:monospace;font-size:11px;color:var(--ac);padding:4px 6px;background:rgba(212,120,0,.06);border-radius:4px;border-left:2px solid var(--ac);margin-top:4px}}
.stats{{display:grid;grid-template-columns:1fr 1fr;gap:2px 20px;margin:8px 0;font-size:13px}}
.stats .lb{{color:var(--dim)}}.stats .vl{{font-family:monospace;text-align:right}}
.dt{{font-size:11px;color:var(--dim);font-family:monospace}}
.wr{{display:flex;align-items:center;padding:6px 0;font-size:13px}}
.wr .lb{{flex:1;font-family:monospace}}.wr .bar{{flex:2;margin:0 10px;height:4px;background:var(--s2);border-radius:2px;overflow:hidden}}
.lg-day{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:10px 12px;margin:8px 0}}
.lg-day .dt{{font-size:13px;font-weight:600;color:var(--ac);margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--bd)}}
.lg-item{{font-size:11px;color:var(--dim);padding:2px 0 2px 8px;margin:1px 0;border-left:2px solid var(--bd);line-height:1.6}}
.lg-add{{border-left-color:var(--up)}}.lg-rm{{border-left-color:var(--dn)}}.lg-st{{border-left-color:var(--ac)}}
.tab{{display:none}}.tab.on{{display:block}}
.emp{{text-align:center;color:var(--dim);padding:30px;font-size:13px}}
.ft{{text-align:center;color:#444;font-size:10px;padding:20px 0;font-family:monospace}}
</style></head><body>
<div class=hd><div><span class=logo><em>◆</em> aquant</span></div><div class=ts>{v}</div></div>
<div class=nv><span class=on data-t=r>推荐</span><span data-t=p>交易指令</span><span data-t=a>模拟盘</span><span data-t=l>日志</span></div>
<div id=tr class="tab on">{rec_html}</div>
<div id=tp class=tab>{plan_html}</div>
<div id=ta class=tab>{paper_html}</div>
<div id=tl class=tab>{log_html}</div>
<div class=ft>数据更新: {v}</div>
<script>
(function(){{
var tabs=["r","p","a","l"];
document.querySelectorAll(".nv span").forEach(function(s){{
s.onclick=function(){{
var t=this.dataset.t;
document.querySelectorAll(".tab").forEach(function(x){{x.classList.remove("on")}});
document.getElementById("t"+t).classList.add("on");
document.querySelectorAll(".nv span").forEach(function(x){{x.classList.remove("on")}});
this.classList.add("on");
}};
}});
}})();
</script></body></html>'''

with open("now.html", "w") as f:
    f.write(HTML)

print(f"Generated now.html: {len(HTML)} bytes, {len(picks)} picks")
