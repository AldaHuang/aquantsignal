import json
with open("reports/tracker.json") as f:
    data = json.load(f)
json_str = json.dumps(data, ensure_ascii=False)

html = """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>aquant</title>
<style>
body{background:#0a0a0a;color:#c8c8c8;font-family:-apple-system,sans-serif;max-width:480px;margin:0 auto;padding:12px}
h3{color:#666;font-size:11px;margin:16px 0 6px}
.nv{display:flex;gap:4px;margin:10px 0}
.nv span{flex:1;text-align:center;padding:8px 0;border-radius:4px;font-size:13px;color:#666;cursor:pointer;background:#141414}
.nv span.on{background:#1c1c1c;color:#fff;font-weight:600}
.cd{background:#141414;border:1px solid #2a2a2a;border-radius:8px;padding:12px;margin:6px 0}
.cd .r{display:flex;justify-content:space-between;align-items:center}
.cd .nm{font-size:15px;font-weight:600;color:#fff}
.tg{display:inline-block;padding:2px 6px;border-radius:3px;font-size:11px;font-weight:600}
.tg-b{background:rgba(192,57,43,.15);color:#c0392b}
.tg-s{background:rgba(39,174,96,.12);color:#27ae60}
.tab{display:none}.tab.on{display:block}
</style></head><body>
<div id="err" style="background:rgba(255,61,61,.1);color:#ff3d3d;padding:10px;border-radius:6px;display:none;margin:10px 0;font-size:12px"></div>
<div class="nv"><span class="on" id="nr">推荐</span><span id="np">交易指令</span><span id="na">模拟盘</span><span id="nl">日志</span></div>
<div id="tr" class="tab on"></div><div id="tp" class="tab"></div><div id="ta" class="tab"></div><div id="tl" class="tab"></div>
<script>
window.onerror=function(m,s,l){document.getElementById("err").style.display="block";document.getElementById("err").textContent="JS: "+m;return false};
try{
var D="""

# Append data + closing JS
html += json_str + """;
function show(t){
  document.querySelectorAll(".tab").forEach(function(x){x.classList.remove("on")});
  document.getElementById("t"+t).classList.add("on");
  ["nr","np","na","nl"].forEach(function(id){document.getElementById(id).classList.remove("on")});
  document.getElementById("n"+t).classList.add("on");
  if(t=="r")rec();if(t=="p")plan();if(t=="a")paper();if(t=="l")log();
}
function rec(){
  var ps=((D.records||[]).slice(-1)[0]||{}).picks||[],h="";
  ps.forEach(function(p){
    var tc=p.verdict=="买入"?"tg-b":"tg-s",rs=(p.reasons||[]).filter(function(r){return r.indexOf("止损")!==0}).slice(0,2).join(" . ");
    h+="<div class=cd><div class=r><span class=nm>"+esc(p.name)+" <span style=font-size:11px;color:#666>"+esc(p.symbol)+"</span></span><span style=font-size:15px;font-weight:600>$"+(p.price||0).toFixed(2)+"</span></div><div class=r style=margin-top:4px><span style=font-size:12px;color:#666>Score <b style=color:#d47800>"+(p.score||0)+"</b></span><span class=\"tg "+tc+"\">"+esc(p.verdict||"?")+"</span></div>";
    if(rs)h+="<div style=font-size:12px;color:#666;margin-top:4px;padding-top:4px;border-top:1px solid rgba(255,255,255,.04)>"+esc(rs)+"</div>";
    if(p.stop_loss)h+="<div style=font-size:11px;color:#d47800;padding:4px 6px;background:rgba(212,120,0,.06);border-left:2px solid #d47800;margin-top:4px>Stop $"+p.stop_loss.toFixed(2)+" | Target $"+(p.take_profit||0).toFixed(2)+"</div>";
    h+="</div>";
  });
  document.getElementById("tr").innerHTML=h||"<div style=text-align:center;color:#666;padding:30px>No picks</div>";
}
function plan(){
  var ps=((D.records||[]).slice(-1)[0]||{}).picks||[];
  var buys=ps.filter(function(p){return p.verdict=="买入"||p.verdict=="关注"});
  if(!buys.length){document.getElementById("tp").innerHTML="<div style=text-align:center;color:#666;padding:30px>暂无买入信号</div>";return}
  var h="<table style=width:100%;border-collapse:collapse;font-size:12px><tr style=font-size:10px;color:#666;text-align:left><th style=padding:6px 4px>股票</th><th style=padding:6px 4px>买入</th><th style=padding:6px 4px>止损</th><th style=padding:6px 4px>止盈</th><th style=padding:6px 4px>仓位</th><th style=padding:6px 4px>风险</th></tr>";
  buys.forEach(function(p){h+="<tr><td style=padding:7px 4px;font-weight:600>"+esc(p.name)+"</td><td style=padding:7px 4px>$"+(p.entry||p.price||0).toFixed(2)+"</td><td style=padding:7px 4px;color:#c0392b>$"+(p.stop_loss||0).toFixed(2)+"</td><td style=padding:7px 4px;color:#27ae60>$"+(p.take_profit||0).toFixed(2)+"</td><td style=padding:7px 4px>"+(p.position_pct||0)+"%</td><td style=padding:7px 4px>"+(p.risk_pct||0).toFixed(1)+"%</td></tr>"});
  h+="</table>";document.getElementById("tp").innerHTML=h;
}
function paper(){
  var pp=D.paper||{},h="",ret=((pp.equity||50000)-(pp.initial_cash||50000))/(pp.initial_cash||50000)*100,c=ret>=0?"#c0392b":"#27ae60";
  h+="<div class=cd><div class=r><span style=color:#666>总资产</span><span style=font-size:36px;font-weight:700;color:"+c+">$"+(pp.equity||50000).toFixed(0)+"</span></div>";
  h+="<div style=display:grid;grid-template-columns:1fr 1fr;gap:2px 10px;margin:8px 0;font-size:13px><span style=color:#666>收益率</span><span style=text-align:right;color:"+c+">"+ret.toFixed(1)+"%</span><span style=color:#666>持仓</span><span style=text-align:right>"+(pp.positions||0)+" 只</span><span style=color:#666>交易</span><span style=text-align:right>"+(pp.total_trades||0)+" 笔</span></div>";
  var bm=D.benchmark;if(bm&&bm.return_pct!=null){var r2=bm.return_pct||0,c2=r2>=0?"#c0392b":"#27ae60",df=ret-r2,c3=df>0?"#c0392b":"#27ae60";h+="<div style=display:flex;justify-content:space-between;padding:4px 8px;font-size:12px;background:rgba(255,255,255,.03);border-radius:4px><span style=color:#666>vs "+esc(bm.name||"CSI300")+"</span><span style=color:"+c2+">"+r2.toFixed(1)+"%</span><span style=font-weight:600;color:"+c3+">Alpha "+(df>0?"+":"")+df.toFixed(1)+"%</span></div>"}h+="</div>";
  (pp.positions_list||[]).forEach(function(p){var pc=p.pnl_pct>=0?"#c0392b":"#27ae60";h+="<div class=cd><div class=r><span class=nm>"+esc(p.name)+"</span><span style=font-size:14px;font-weight:600;color:"+pc+">"+(p.pnl_pct>0?"+":"")+(p.pnl_pct||0).toFixed(1)+"%</span></div><div style=font-size:11px;color:#666;font-family:monospace>"+p.shares+"股 | 成本$"+(p.avg_cost||0).toFixed(2)+" > 现$"+(p.current_price||0).toFixed(2)+" | 市值$"+(p.market_value||0).toFixed(0)+"</div></div>"});
  var hist=pp.history||[];if(hist.length){h+="<h3>已平仓</h3>";hist.slice(-10).reverse().forEach(function(t){var cl=(t.pnl||0)>=0?"#c0392b":"#27ae60";h+="<div class=cd><div class=r><span class=nm>"+esc(t.name||t.symbol)+"</span><span style=font-size:16px;font-weight:700;color:"+cl+">$"+(t.pnl>0?"+":"")+(t.pnl||0).toFixed(0)+"</span></div><div style=font-size:11px;color:#666;font-family:monospace>"+esc(t.shares||"")+"股 | 买$"+(t.entry_price||0).toFixed(2)+" > 卖$"+(t.exit_price||0).toFixed(2)+" | "+esc(t.reason||"")+"</div></div>"})}
  document.getElementById("ta").innerHTML=h||"<div style=text-align:center;color:#666;padding:30px>暂无数据</div>";
}
function log(){
  var h="",w=D.strategy_weights||{};h+="<h3>策略权重</h3>";
  Object.keys(w).sort().forEach(function(k){var v=w[k];h+="<div style=display:flex;align-items:center;padding:6px 0;font-size:13px><span style=flex:1>"+esc(k)+"</span><span style=flex:2;margin:0 10px;height:4px;background:#1c1c1c;border-radius:2px><span style=display:block;height:100%;border-radius:2px;background:#d47800;width:"+Math.round(v/1.5*100)+"%></span></span><span>"+v.toFixed(2)+"</span></div>"});
  var mr=D.market_regime||{};if(mr.regime){var rl={trending:"趋势",ranging:"震荡",mixed:"混合"};h+="<h3>市场状态</h3><div class=cd style=padding:8px 12px;font-size:13px>"+(rl[mr.regime]||mr.regime)+" (强度 "+mr.strength+")</div>"}
  var cl=D.changelog||"";if(cl){h+="<h3>更新日志</h3>";var ss=cl.split(/\\n(?=## \\d{4}-\\d{2}-\\d{2})/);for(var si=0;si<Math.min(ss.length,6);si++){var sec=ss[si];if(!sec.trim())continue;var lines=sec.split("\\n"),d="";if(lines[0].indexOf("## ")==0)d=lines[0].slice(3);h+="<div style=background:#141414;border:1px solid #2a2a2a;border-radius:8px;padding:10px 12px;margin:8px 0><div style=font-size:13px;font-weight:600;color:#d47800;margin-bottom:4px;padding-bottom:4px;border-bottom:1px solid #2a2a2a>"+esc(d)+"</div>";for(var li=1;li<lines.length;li++){var l=lines[li];if(l.indexOf("### ")==0){h+="<div style=font-size:11px;color:#ccc;margin:6px 0 2px>"+esc(l.slice(4))+"</div>";continue}if(l.indexOf("---")==0)continue;if(l.indexOf("- ")==0){var t=l.replace(/^- /,"").trim(),cls="lg-item";h+="<div style=font-size:11px;color:#666;padding:2px 0 2px 8px;border-left:2px solid #2a2a2a;margin:2px 0;line-height:1.6";if(t.indexOf("新增")>=0)h+=";border-left-color:#c0392b";else if(t.indexOf("移除")>=0)h+=";border-left-color:#27ae60";else if(t.indexOf("持续")>=0)h+=";border-left-color:#d47800";h+=">"+esc(t)+"</div>"}else if(l.trim())h+="<div style=font-size:10px;color:#666;padding:1px 0>"+esc(l)+"</div>"}h+="</div>"}}
  document.getElementById("tl").innerHTML=h||"<div style=text-align:center;color:#666;padding:30px>暂无日志</div>";
}
function esc(s){if(!s)return"";return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
["nr","np","na","nl"].forEach(function(id){document.getElementById(id).onclick=function(){show(id.charAt(1))}});
show("r");
}catch(e){document.getElementById("err").style.display="block";document.getElementById("err").textContent="ERR: "+e.message}
</script></body></html>"""

with open("now.html", "w") as f:
    f.write(html)
print("Size:", len(html))
print("Has D=:", "var D=" in html[:5000])
