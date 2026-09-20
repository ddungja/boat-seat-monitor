import json, re, shutil, requests, time
from pathlib import Path
from datetime import datetime, date
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote

ROOT=Path(__file__).resolve().parent
CFG=ROOT/"site_sources.json"
DOCS=ROOT/"docs"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0.0.0 Safari/537.36"
s=requests.Session(); s.headers.update({"User-Agent":UA,"Accept-Language":"ko-KR,ko;q=0.9,en;q=0.8"})

def esc(v): return (str(v or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#039;"))
def page_url(u,p): return re.sub(r'([?&])page=\d+',rf'\1page={p}',u) if "page=" in u else u+("&" if "?" in u else "?")+f"page={p}"
def parse_date(t,start,end):
    for m in re.finditer(r'(?<!\d)(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})(?!\d)',t):
        try: d=datetime(*map(int,m.groups()))
        except: continue
        if start<=d<=end:return d
    for m in re.finditer(r'(?<!\d)(\d{1,2})[./-](\d{1,2})(?!\d)',t):
        try: d=datetime(start.year,*map(int,m.groups()))
        except: continue
        if start<=d<=end:return d
def imgs(blob):
    blob=str(blob).replace("\\/","/").replace("\\u002F","/")
    out=[]; seen=set()
    for u in re.findall(r'https?://imga\.sunsang24\.com/ship_board/[^"\'\s<>\\]+',blob,re.I):
        u=u.rstrip("),;]}>"); k=re.sub(r'_(?:smini|mini|thumb)(?=\.[A-Za-z0-9]+(?:\?|$))','',u)
        if k not in seen: seen.add(k); out.append(u)
    return out
def full(u): return re.sub(r'_(?:smini|mini|thumb)(?=\.[A-Za-z0-9]+(?:\?|$))','',u)
def dl(u,p):
    for x in dict.fromkeys([full(u),u]):
        try:
            r=s.get(x,timeout=30,headers={"User-Agent":UA,"Accept":"image/*,*/*;q=0.8"})
            if r.status_code==200 and ((r.headers.get("Content-Type") or "").startswith("image/") or r.content[:3]==b"\xff\xd8\xff"):
                p.write_bytes(r.content); return True
        except: pass
    return False
def blocks(soup):
    nodes=[]
    for sel in ["li","article",".list",".item",".board-list",".board_item",".post",".card","tr"]:
        try:nodes += soup.select(sel)
        except:pass
    return [n for n in nodes if len(n.get_text(" ",strip=True))>=20]
def list_posts(html,src,url,start,end):
    soup=BeautifulSoup(html,"html.parser"); kw=src["keyword"].lower(); found={}; n=0
    for node in blocks(soup):
        text=node.get_text(" ",strip=True)
        if kw not in text.lower(): continue
        dt=parse_date(text,start,end)
        if not dt: continue
        title=""
        for sel in ["h1","h2","h3","h4",".title",".subject","a"]:
            tag=node.select_one(sel)
            if tag:
                t=tag.get_text(" ",strip=True)
                if kw in t.lower() or re.search(r'\d{1,2}[./-]\d{1,2}',t): title=t; break
        if not title:title=text[:160]
        detail=""
        for a in node.find_all("a",href=True):
            if "board_detail" in str(a["href"]): detail=urljoin(url,str(a["href"])); break
        photos=imgs(str(node)); key=detail or f"{dt:%Y%m%d}|{title}"
        found[key]={"date":dt.strftime("%Y-%m-%d"),"sort":dt.strftime("%Y%m%d"),"title":title,"body":text,"detail":detail,"photos":photos,"key":re.sub(r'\W+','',key)[-50:]}; n+=1
    return list(found.values())
def enrich(p):
    if not p["detail"]: return p
    try:
        r=s.get(p["detail"],timeout=30)
        if r.status_code!=200:return p
        soup=BeautifulSoup(r.text,"html.parser")
        for sel in [".title",".view_title",".subject","h1","h2","h3"]:
            t=soup.select_one(sel)
            if t and len(t.get_text(" ",strip=True))>=5: p["title"]=t.get_text(" ",strip=True); break
        for sel in [".editor",".view_content",".view-content",".board_view_content",".content"]:
            n=soup.select_one(sel)
            if n and len(n.get_text("\n",strip=True))>=20: p["body"]="\n".join(x.strip() for x in n.get_text("\n",strip=True).splitlines() if x.strip()); break
        ph=imgs(r.text)
        if ph:p["photos"]=ph
    except:pass
    return p
def collect(src):
    start=datetime.strptime(src["start_date"],"%Y-%m-%d"); today=date.today(); end=datetime(today.year,today.month,today.day); got={}
    for pg in range(1,11):
        try:r=s.get(page_url(src["board_url"],pg),timeout=30)
        except:break
        if r.status_code!=200:break
        ps=list_posts(r.text,src,page_url(src["board_url"],pg),start,end)
        for p in ps: got.setdefault(p["key"],p)
        if len(got)>=src.get("max_posts",30):break
        if not ps and pg>=3:break
        time.sleep(.1)
    out=[]
    for p in sorted(got.values(),key=lambda x:x["sort"],reverse=True)[:src.get("max_posts",30)]:
        p=enrich(p)
        month=p["date"][:7].replace("-",""); ph=[]
        for u in p["photos"]:
            m=re.search(r'/ship_board/(\d{6})/',u)
            if not m or m.group(1)==month: ph.append(u)
        p["photos"]=list(dict.fromkeys(ph))
        if p["photos"]: out.append(p)
    return out
def safe(title,key):
    x=re.sub(r'[\\/:*?"<>|]','_',title); x=re.sub(r'\s+',' ',x).strip()
    return f"{x[:80]}_{key}.html"

def build():
    cfg=json.loads(CFG.read_text(encoding="utf-8")); sources=[x for x in cfg["sources"] if x.get("enabled",True)]
    if DOCS.exists(): shutil.rmtree(DOCS)
    (DOCS/"assets"/"photos").mkdir(parents=True); (DOCS/"posts").mkdir(); (DOCS/".nojekyll").write_text("")
    css="""*{box-sizing:border-box}body{margin:0;font-family:Arial,'Malgun Gothic',sans-serif;background:#f4f7f9;color:#14202a}a{text-decoration:none;color:inherit}.wrap{width:min(1180px,calc(100% - 30px));margin:auto}header{background:#fff;border-bottom:1px solid #dce5ea}header .wrap{display:flex;justify-content:space-between;gap:18px;align-items:center;padding:17px 0}.logo{font-weight:900;color:#076b98;font-size:22px}.nav{display:flex;gap:14px;flex-wrap:wrap;font-size:14px;font-weight:700}.hero{padding:36px 0 20px}.tabs{display:flex;gap:9px;flex-wrap:wrap}.tab{padding:10px 15px;border:1px solid #dce5ea;border-radius:999px;background:#fff;font-weight:800;cursor:pointer}.tab.active{background:#076b98;color:#fff}.filters{display:flex;gap:10px;margin:16px 0}.filters input{padding:11px;border:1px solid #dce5ea;border-radius:10px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;padding:12px 0 50px}.card{background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 10px 28px #0001}.thumb{aspect-ratio:4/3;position:relative;background:#ddd}.thumb img{width:100%;height:100%;object-fit:cover}.badge{position:absolute;right:10px;bottom:10px;background:#000a;color:#fff;border-radius:999px;padding:6px 9px;font-size:12px}.body{padding:17px}.date{color:#076b98;font-weight:800;font-size:13px}.body h2{font-size:18px}.preview{color:#677681;line-height:1.65;font-size:14px}.hidden{display:none!important}.content{padding:36px 0 60px}.content p,.content li{line-height:1.9}.detail-text{background:#fff;padding:24px;border-radius:18px;line-height:1.95;margin:20px 0}.gallery{display:grid;gap:16px}.gallery img{width:100%;border-radius:14px}footer{background:#fff;border-top:1px solid #dce5ea;padding:28px 0;color:#677681;font-size:13px}@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:650px){header .wrap{flex-direction:column;align-items:flex-start}.grid{grid-template-columns:1fr}.filters{display:grid}}"""
    (DOCS/"assets"/"style.css").write_text(css,encoding="utf-8")
    nav='<nav class="nav"><a href="../index.html">조황</a><a href="../guide.html">이용안내</a><a href="../about.html">소개</a><a href="../privacy.html">개인정보처리방침</a><a href="../contact.html">문의</a></nav>'
    tabs=['<button class="tab active" data-source="all">전체</button>']; cards=[]
    for src in sources:
        posts=collect(src); tabs.append(f'<button class="tab" data-source="{src["id"]}">{esc(src["name"])} ({len(posts)})</button>')
        for p in posts:
            local=[]
            for i,u in enumerate(p["photos"],1):
                ext=".png" if ".png" in u.lower() else ".jpg"; fn=f'{src["id"]}_{p["key"]}_{i:02d}{ext}'; fp=DOCS/"assets"/"photos"/fn
                if dl(u,fp): local.append("../assets/photos/"+fn)
            if not local: continue
            fn=safe(p["title"],p["key"])
            detail=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(p["title"])}</title><link rel="stylesheet" href="../assets/style.css"></head><body><header><div class="wrap"><a class="logo" href="../index.html">선상 조황 모아보기</a>{nav}</div></header><main class="wrap content"><div class="date">{p["date"]} · {esc(src["name"])}</div><h1>{esc(p["title"])}</h1><p><a href="{esc(p["detail"])}" target="_blank">선상24 원문 보기</a></p><div class="detail-text">{'<br>'.join(esc(p["body"]).splitlines())}</div><div class="gallery">{''.join(f'<img src="{x}" loading="lazy">' for x in local)}</div></main></body></html>'''
            (DOCS/"posts"/fn).write_text(detail,encoding="utf-8")
            search=esc((src["name"]+" "+p["title"]+" "+p["body"]).lower())
            cards.append(f'<article class="card source-card" data-source="{src["id"]}" data-date="{p["date"]}" data-search="{search}"><a href="posts/{quote(fn)}"><div class="thumb"><img src="assets/photos/{Path(local[0]).name}" loading="lazy"><span class="badge">사진 {len(local)}장</span></div><div class="body"><div class="date">{p["date"]} · {esc(src["name"])}</div><h2>{esc(p["title"])}</h2><p class="preview">{esc(p["body"].replace(chr(10)," ")[:140])}</p></div></a></article>')
    index=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>선상 조황 모아보기</title><link rel="stylesheet" href="assets/style.css"></head><body><header><div class="wrap"><a class="logo" href="index.html">선상 조황 모아보기</a><nav class="nav"><a href="index.html">조황</a><a href="guide.html">이용안내</a><a href="about.html">소개</a><a href="privacy.html">개인정보처리방침</a><a href="contact.html">문의</a></nav></div></header><main class="wrap"><section class="hero"><h1>최신 선상 조황을 한눈에</h1><p>선박별·날짜별 조황을 정리하고 원문 출처를 연결합니다.</p></section><div class="tabs">{''.join(tabs)}</div><div class="filters"><input id="search" placeholder="선박명·제목·본문 검색"><input id="date" type="date"></div><p><strong id="count"></strong></p><section class="grid">{''.join(cards)}</section></main><footer><div class="wrap">© 2026 선상 조황 모아보기</div></footer><script>const tabs=[...document.querySelectorAll('.tab')],cards=[...document.querySelectorAll('.source-card')],q=document.getElementById('search'),d=document.getElementById('date'),c=document.getElementById('count');let cur='all';function a(){{let n=0;cards.forEach(x=>{{const ok=(cur==='all'||x.dataset.source===cur)&&(!q.value||x.dataset.search.includes(q.value.toLowerCase()))&&(!d.value||x.dataset.date===d.value);x.classList.toggle('hidden',!ok);if(ok)n++;}});c.textContent='조황 '+n+'건';}}tabs.forEach(t=>t.onclick=()=>{{cur=t.dataset.source;tabs.forEach(x=>x.classList.toggle('active',x===t));a();}});q.oninput=a;d.onchange=a;a();</script></body></html>'''
    (DOCS/"index.html").write_text(index,encoding="utf-8")
    def simple(name,title,body):
        (DOCS/name).write_text(f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><link rel="stylesheet" href="assets/style.css"></head><body><header><div class="wrap"><a class="logo" href="index.html">선상 조황 모아보기</a><nav class="nav"><a href="index.html">조황</a><a href="guide.html">이용안내</a><a href="about.html">소개</a><a href="privacy.html">개인정보처리방침</a><a href="contact.html">문의</a></nav></div></header><main class="wrap content"><h1>{title}</h1>{body}</main></body></html>',encoding="utf-8")
    simple("about.html","사이트 소개","<p>여러 선사의 공개 조황을 선박·날짜 기준으로 정리해 이용자가 최근 현장 상황을 쉽게 비교하도록 돕는 정보 사이트입니다.</p><p>각 상세페이지에 원문 출처 링크를 제공합니다.</p>")
    simple("guide.html","이용안내","<p>선박 탭, 검색, 날짜 필터를 이용해 조황을 찾을 수 있습니다.</p><ul><li>실제 조과는 기상·물때·포인트에 따라 달라질 수 있습니다.</li><li>예약 및 출항 여부는 각 선사의 최신 안내를 확인하세요.</li></ul>")
    simple("privacy.html","개인정보처리방침","<p>사이트 운영 과정에서 호스팅 서버 로그가 처리될 수 있습니다.</p><p>향후 Google AdSense 등 제3자 광고 서비스를 사용할 경우 쿠키가 광고 제공 및 측정을 위해 사용될 수 있으며, 관련 내용을 본 방침에 반영합니다.</p>")
    simple("contact.html","문의","<p>게시물 수정·삭제 또는 권리 관련 문의를 받을 수 있도록 실제 운영 이메일을 추후 이 페이지에 기재할 예정입니다.</p>")
    (DOCS/"robots.txt").write_text("User-agent: *\nAllow: /\n",encoding="utf-8")
    print("docs 생성 완료")

if __name__=="__main__": build()
