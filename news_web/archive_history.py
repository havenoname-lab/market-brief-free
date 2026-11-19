"""Public daily archive discovery and article-header metadata only."""
import asyncio
import hashlib
import json
from datetime import datetime,timezone,timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit
from news_web.history import canonical,import_rows
from news_web.service import plain,timestamp
from news_web.topics import classify


class ArchiveLinks(HTMLParser):
 def __init__(self):
  super().__init__();self.depth=0;self.href=None;self.title=[];self.links=[]
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='ul':
   if self.depth:self.depth+=1
   elif attrs.get('data-testid')=='sitemap-stories':self.depth=1
  if self.depth and tag=='a':self.href=attrs.get('href');self.title=[]
 def handle_data(self,data):
  if self.href:self.title.append(data)
 def handle_endtag(self,tag):
  if tag=='a' and self.href:
   if urlsplit(self.href).netloc=='www.washingtonpost.com':self.links.append((self.href,plain(' '.join(self.title))))
   self.href=None
  if tag=='ul' and self.depth:self.depth-=1


class HeaderMetadata(HTMLParser):
 def __init__(self):super().__init__();self.active=False;self.chunks=[];self.documents=[]
 def handle_starttag(self,tag,attrs):
  if tag=='script' and dict(attrs).get('type')=='application/ld+json':self.active=True;self.chunks=[]
 def handle_data(self,data):
  if self.active:self.chunks.append(data)
 def handle_endtag(self,tag):
  if tag=='script' and self.active:
   self.documents.append(''.join(self.chunks));self.active=False


def article_metadata(html,url):
 parser=HeaderMetadata();parser.feed(html)
 def candidates(item):
  if isinstance(item,list):
   for child in item:yield from candidates(child)
  elif isinstance(item,dict):
   if item.get('headline') and item.get('datePublished'):yield item
   if '@graph' in item:yield from candidates(item['@graph'])
 for document in parser.documents:
  try:data=json.loads(document)
  except ValueError:continue
  for item in candidates(data):
   published=timestamp(item['datePublished'])
   if not published:continue
   source='washingtonpost'
   return dict(id=hashlib.sha256(f'{source}:{url}'.encode()).hexdigest()[:24],source_id=source,url=url,
       title=plain(item['headline'])[:1000],summary=plain(item.get('description',''))[:1200],published_at=published,impact='待分析')
 return None


async def run(service,days=7):
 current=datetime.now(timezone.utc);since=current-timedelta(days=days)
 with service.connect() as db:existing={canonical(r[0]) for r in db.execute("SELECT url FROM articles WHERE source_id='washingtonpost'")}
 candidates={};reports=[]
 # Include both boundary calendar dates; only exact publication timestamps determine inclusion.
 for i in range(days+2):
  day=(current-timedelta(days=i)).strftime('%Y/%m/%d')
  url='https://www.washingtonpost.com/sitemap/'+day+'/'
  result=dict(source='washingtonpost',archive=url,inserted=0,complete_history=False)
  try:
   parser=ArchiveLinks();parser.feed((await service.fetch(url)).decode('utf-8'))
   links=parser.links
   # Original requested coverage is financial/market-relevant news, not lifestyle archives.
   relevant=[(u,t) for u,t in links if urlsplit(u).path.startswith(('/business/','/technology/')) or classify(t,'')!=['其他']]
   for u,t in relevant:
    if canonical(u) not in existing:candidates[u]=t
   result.update(status='ok',listed=len(links),relevant=len(relevant))
  except Exception as exc:result.update(status='error',error=type(exc).__name__)
  reports.append(result)
  print(json.dumps(result),flush=True)
  await asyncio.sleep(.5)
 semaphore=asyncio.Semaphore(2);inserted=0;failed=0;outside=0;blocked=0
 async def read(url):
  nonlocal inserted,failed,outside,blocked
  async with semaphore:
   if blocked>=3:failed+=1;return
   try:
    body=await service.fetch(url)
    row=await asyncio.to_thread(article_metadata,body.decode('utf-8'),url)
    if row and since<=datetime.fromisoformat(row['published_at'])<=current:
     inserted+=import_rows(service,[row])
    elif row:outside+=1
    else:failed+=1
   except Exception as exc:
    failed+=1
    if getattr(getattr(exc,'response',None),'status_code',None) in (401,403):blocked+=1
   await asyncio.sleep(.5)
 await asyncio.gather(*(read(u) for u in candidates))
 report=dict(source='washingtonpost',method='public_daily_archive_headers',days=days,candidates=len(candidates),inserted=inserted,
     failed=failed,outside_window=outside,complete_history=False,archives=reports,
     scope='财经／科技栏目及标题含市场相关主题的日档案；仅使用公开JSON-LD标题、摘要与原始发布时间。')
 with service.connect() as db:
  db.execute('INSERT INTO backfill_runs(source_id,channel,finished_at,result) VALUES(?,?,?,?)',
      ('washingtonpost','daily_archive',datetime.now(timezone.utc).isoformat(),json.dumps(report)))
 (service.db_path.parent/'archive_7d.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=True),flush=True)
 return report


async def main():
 from pathlib import Path
 from news_web.service import NewsService
 s=NewsService(Path(__file__).parent/'data'/'news.db')
 try:await run(s)
 finally:await s.close()


if __name__=='__main__':asyncio.run(main())
