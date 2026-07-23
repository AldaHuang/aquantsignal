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
function esc(s){if(!s)return"";return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
["nr","np","na","nl"].forEach(function(id){document.getElementById(id).onclick=function(){show(id.charAt(1))}});
show("r");
}catch(e){document.getElementById("err").style.display="block";document.getElementById("err").textContent="ERR: "+e.message}
</script></body></html>"""

with open("now.html", "w") as f:
    f.write(html)
print("Size:", len(html))
print("Has D=:", "var D=" in html[:5000])
