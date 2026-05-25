import { Buffer } from 'node:buffer';

const VERCEL_URL = process.env.VERCEL_URL || 'inspection-371.vercel.app';

const INDEX_HTML = `<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>台北捷運371型電聯車 巡檢保養查詢</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; background: #f0f2f5; color: #1c1e21; }
header { background: linear-gradient(135deg, #1a73e8, #1557b0); color: #fff; padding: 16px 24px; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,.15); }
header h1 { font-size: 18px; font-weight: 600; margin-bottom: 2px; }
header .sub { font-size: 13px; opacity: .8; }
.container { max-width: 1400px; margin: 0 auto; padding: 16px; display: grid; grid-template-columns: 340px 1fr; gap: 16px; }
.sidebar { position: sticky; top: 80px; align-self: start; }
.card { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.1); padding: 16px; margin-bottom: 12px; }
.card h3 { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #555; }
.sidebar .card { padding: 14px; }
.search-box input { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; outline: none; }
.search-box input:focus { border-color: #1a73e8; box-shadow: 0 0 0 2px rgba(26,115,232,.15); }
.check-item-list { max-height: 350px; overflow-y: auto; border: 1px solid #e4e6eb; border-radius: 6px; margin-top: 8px; }
.check-item-list label { display: flex; align-items: flex-start; gap: 6px; padding: 5px 10px; font-size: 12px; font-weight: 400; cursor: pointer; border-bottom: 1px solid #f0f2f5; line-height: 1.4; word-break: break-all; }
.check-item-list label:hover { background: #f0f7ff; }
.check-item-list label input { margin-top: 2px; flex-shrink: 0; }
.check-item-list .select-all { position: sticky; top: 0; background: #f8f9fa; padding: 6px 10px; font-size: 12px; font-weight: 500; border-bottom: 1px solid #e4e6eb; display: flex; align-items: center; gap: 6px; z-index: 1; }
.filter-actions { display: flex; gap: 8px; margin-top: 8px; }
.filter-actions button { flex: 1; padding: 8px 12px; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-primary { background: #1a73e8; color: #fff; }
.btn-primary:hover { background: #1557b0; }
.btn-outline { background: #fff; color: #555; border: 1px solid #ddd !important; }
.btn-outline:hover { background: #f5f5f5; }
.result-card { margin-top: 12px; }
.result-card h2 { font-size: 16px; margin-bottom: 8px; }
.result-card .stats { font-size: 13px; color: #666; margin-bottom: 10px; }
.search-result { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-bottom: 8px; padding: 12px 14px; cursor: pointer; transition: all .15s; border-left: 3px solid transparent; }
.search-result:hover { background: #f0f7ff; border-left-color: #1a73e8; }
.search-result .car-num { font-weight: 600; font-size: 15px; color: #1a73e8; margin-bottom: 4px; }
.search-result .detail { font-size: 12px; color: #555; line-height: 1.5; display: flex; flex-wrap: wrap; gap: 4px 12px; }
.search-result .detail-item { white-space: nowrap; }
.search-result .detail-label { color: #888; }
.selected { border-left-color: #28a745; background: #f0fff0; }
.selected .car-num { color: #28a745; }
.selected:hover { background: #e8ffe8; }
.empty-state { text-align: center; padding: 40px 20px; color: #888; }
.empty-state .icon { font-size: 48px; margin-bottom: 12px; }
.empty-state p { font-size: 14px; }
#apiResult { white-space: pre-wrap; font-size: 12px; font-family: monospace; background: #f8f9fa; padding: 8px; border-radius: 4px; overflow-x: auto; }
.toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: #fff; padding: 8px 16px; border-radius: 20px; font-size: 13px; z-index: 200; opacity: 0; transition: opacity .3s; }
.toast.show { opacity: 1; }
</style>
</head>
<body>
<header><h1>🚇 台北捷運371型電聯車 巡檢保養查詢</h1><div class="sub">inspection-371 · 批次輸出</div></header>
<div class="container">
<div class="sidebar">
<div class="card"><h3>🔍 搜尋條件</h3><div class="search-box"><input type="text" id="searchInput" placeholder="輸入車號、車型、廠商…" oninput="filterResults()"></div>
<div class="filter-actions"><button class="btn-primary" onclick="selectAllVisible()">全選</button><button class="btn-outline" onclick="deselectAll()">清除選擇</button><button class="btn-outline" onclick="clearFilters()">清除篩選</button></div>
<div class="card" style="margin-top:12px"><h3>📦 批次動作</h3><button class="btn-primary" style="width:100%;margin-bottom:6px" onclick="batchExport()">📥 匯出選擇 (JSON)</button><button class="btn-primary" style="width:100%" onclick="batchExportFull()">📥 匯出完整明細</button></div>
<div class="card" style="margin-top:0"><h3>📋 選取統計</h3><div class="stats"><span id="selectedCount">0</span> / <span id="totalCount">0</span> 輛車</div></div>
</div>
<div class="main-content">
<div class="card"><h3>📊 統計總覽</h3><div id="statsSummary" class="stats">載入中…</div></div>
<div class="card result-card"><h2>📋 搜尋結果</h2><div class="stats"><span id="resultCount">0</span> 筆資料</div><div id="results"></div></div>
</div>
</div>
<div id="toast" class="toast"></div>
<script>
async function loadData() {
try {
const params=new URLSearchParams({limit:'500'});
const resp=await fetch('/api/data?'+params);
const text=await resp.text();
const data=JSON.parse(text);
if(data.error)throw new Error(data.error);
window.allData=data; renderStats(); filterResults();
document.getElementById('totalCount').textContent=data.length;
} catch(e){document.getElementById('results').innerHTML='<div class="empty-state"><div class="icon">⚠️</div><p>載入失敗：'+e.message+'</p></div>';}
}
function renderStats(){if(!window.allData||!window.allData.length){document.getElementById('statsSummary').innerHTML='無資料';return;}
const total=window.allData.length; const cars={}; const types={}; const mfrs={};
window.allData.forEach(r=>{if(r.車號)cars[r.車號]=true;if(r.車型)types[r.車型]=(types[r.車型]||0)+1;if(r.製造商)mfrs[r.製造商]=(mfrs[r.製造商]||0)+1;});
document.getElementById('statsSummary').innerHTML='<div class="detail">'+
'<span class="detail-item"><span class="detail-label">總資料筆數：</span>'+total+'</span>'+
'<span class="detail-item"><span class="detail-label">不重複車號：</span>'+Object.keys(cars).length+'</span>'+
'<span class="detail-item"><span class="detail-label">車型數：</span>'+Object.keys(types).length+'</span>'+
'<span class="detail-item"><span class="detail-label">製造商數：</span>'+Object.keys(mfrs).length+'</span></div>';}
function filterResults(){const q=(document.getElementById('searchInput').value||'').toLowerCase().trim();
const data=window.allData||[]; const filtered=q?data.filter(r=>JSON.stringify(Object.values(r)).toLowerCase().includes(q)):data;
document.getElementById('resultCount').textContent=filtered.length;
const container=document.getElementById('results'); if(!filtered.length){container.innerHTML='<div class="empty-state"><div class="icon">🔍</div><p>無符合資料</p></div>';return;}
container.innerHTML=filtered.map((r,i)=>'<div class="search-result'+(r._selected?' selected':'')+'" data-idx="'+i+'" onclick="toggleSelect('+i+')">'+
'<div class="car-num">'+(r.車號||'無車號')+'</div>'+
'<div class="detail">'+Object.entries(r).filter(([k])=>k!=='_selected').map(([k,v])=>'<span class="detail-item"><span class="detail-label">'+k+'：</span>'+String(v??'-')+'</span>').join('')+'</div></div>').join('');}
function toggleSelect(i){if(!window.allData[i])return;window.allData[i]._selected=!window.allData[i]._selected;filterResults();updateSelectedCount();}
function selectAllVisible(){const q=(document.getElementById('searchInput').value||'').toLowerCase().trim();
(window.allData||[]).forEach((r,i)=>{if(!q||JSON.stringify(Object.values(r)).toLowerCase().includes(q))r._selected=true;});filterResults();updateSelectedCount();showToast('已全選');}
function deselectAll(){(window.allData||[]).forEach(r=>r._selected=false);filterResults();updateSelectedCount();showToast('已清除選擇');}
function clearFilters(){document.getElementById('searchInput').value='';filterResults();}
function updateSelectedCount(){document.getElementById('selectedCount').textContent=(window.allData||[]).filter(r=>r._selected).length;}
function batchExport(){const sel=(window.allData||[]).filter(r=>r._selected);if(!sel.length){showToast('請先選擇至少一筆資料');return;}
const blob=new Blob([JSON.stringify(sel,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='inspection_export_'+new Date().toISOString().slice(0,10)+'.json';a.click();showToast('已匯出 '+sel.length+' 筆');}
function batchExportFull(){const sel=(window.allData||[]).filter(r=>r._selected);if(!sel.length){showToast('請先選擇至少一筆資料');return;}
const opts={headers:{'Content-Type':'application/json'},method:'POST',body:JSON.stringify(sel)};
fetch('/api/export_detail?'+new URLSearchParams({filename:'batch_export_'+Date.now()}),opts).then(r=>r.json()).then(d=>{if(d.url){window.open(d.url,'_blank');showToast('已產生下載連結');}else showToast('匯出失敗：'+(d.error||'未知錯誤'));}).catch(e=>showToast('匯出失敗：'+e.message));}
function showToast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000);}
loadData();
</script>
</body>
</html>`;

export default async function handler(req, res) {
  try {
    // Parse the actual request path
    const rawUrl = req.url || '/';
    const queryIdx = rawUrl.indexOf('?');
    const path = queryIdx >= 0 ? rawUrl.substring(0, queryIdx) : rawUrl;
    const qs = queryIdx >= 0 ? rawUrl.substring(queryIdx) : '';

    // Serve embedded HTML for root
    if (path === '/' || path === '/index.html') {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      return res.status(200).send(INDEX_HTML);
    }

    // For API routes, proxy to the internal Flask/Python endpoint
    const targetUrl = `https://${VERCEL_URL}/api${path}${qs}`;

    const upstream = await fetch(targetUrl, {
      method: req.method,
      headers: Object.fromEntries([...req.headers.entries()]),
    });

    res.status(upstream.status);
    upstream.headers.forEach((val, key) => {
      if (key !== 'content-encoding') {
        res.setHeader(key, val);
      }
    });
    const body = await upstream.arrayBuffer();
    return res.send(Buffer.from(body));
  } catch (err) {
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    return res.status(500).send(`Proxy error: ${err.message}`);
  }
}