"""Import dated public news-index metadata; never infer headlines from URL slugs."""
import asyncio
import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlsplit
from news_web.service import NewsService,plain,timestamp,canonical_article_url

NEWS_MAPS=[
 ('bloomberg','https://www.bloomberg.com/sitemaps/news/latest.xml'),
 ('ft','https://www.ft.com/sitemaps/news.xml'),
 ('wsj','https://www.wsj.com/wsjsitemaps/wsj_google_news.xml'),
 ('forbes','https://www.forbes.com/news_sitemap.xml'),
 ('washingtonpost','https://www.washingtonpost.com/sitemaps/news-sitemap.xml.gz'),
 *[('bbc',f'https://www.bbc.com/sitemaps/https-sitemap-com-news-{n}.xml') for n in (1,2,3)],
]
NS='{http://www.google.com/schemas/sitemap-news/0.9}'
SM='{http://www.sitemaps.org/schemas/sitemap/0.9}'


def parse_news_sitemap(xml,source,host,since,until):
 root=ET.fromstring(xml)
 rows=[];missing=0;outside=0
 if root.tag!=SM+'urlset':raise ValueError('Expected a news URL set')
 for entry in root.findall(SM+'url'):
  url=(entry.findtext(SM+'loc') or '').strip()
  parts=urlsplit(url)
  if parts.scheme!='https' or parts.netloc!=host or parts.username:continue
  news=entry.find(NS+'news')
  title=plain(news.findtext(NS+'title')) if news is not None else ''
  published=timestamp(news.findtext(NS+'publication_date')) if news is not None else None
  if not title or not published:missing+=1;continue
  if not since<=datetime.fromisoformat(published)<=until:outside+=1;continue
  rows.append(dict(id=hashlib.sha256(f'{source}:{url}'.encode()).hexdigest()[:24],
      source_id=source,title=title[:1000],url=url,summary='',published_at=published,impact='待分析'))
 return rows,dict(missing_metadata=missing,outside_window=outside,index_entries=len(root))


def canonical(url):
 return canonical_article_url(url)


def import_rows(service,rows):
 # Supplementary indexes have no abstract; never overwrite a richer existing RSS record.
 with service.connect() as db:
  existing={(r['source_id'],canonical(r['url'])) for r in db.execute('SELECT source_id,url FROM articles')}
 fresh=[]
 for row in rows:
  key=(row['source_id'],canonical(row['url']))
  if key not in existing:fresh.append(row);existing.add(key)
 return service.save_rows(fresh)


async def run(service,days=7):
 current=datetime.now(timezone.utc);since=current-timedelta(days=days)
 results=[]
 for source,url in NEWS_MAPS:
  result=dict(source=source,index_url=url,inserted=0,complete_history=False)
  try:
   xml=await service.fetch(url)
   if xml[:2]==b'\x1f\x8b':
    import gzip
    xml=gzip.decompress(xml)
   rows,info=parse_news_sitemap(xml,source,urlsplit(url).netloc,since,current)
   result.update(info,available_in_window=len(rows),inserted=import_rows(service,rows),status='ok',
       oldest=min((r['published_at'] for r in rows),default=None),newest=max((r['published_at'] for r in rows),default=None))
  except Exception as exc:
   result.update(status='error',error=type(exc).__name__)
  results.append(result)
  with service.connect() as db:
   db.execute('INSERT INTO backfill_runs(source_id,channel,finished_at,result) VALUES(?,?,?,?)',
       (source,'public_news_index',datetime.now(timezone.utc).isoformat(),json.dumps(result)))
  print(json.dumps(result,ensure_ascii=True),flush=True)
  await asyncio.sleep(.5)
 report=dict(started_at=current.isoformat(),finished_at=datetime.now(timezone.utc).isoformat(),days=days,
     since=since.isoformat(),results=results,inserted=sum(r['inserted'] for r in results),complete_history=False,
     scope='仅公开新闻索引提供的标题和真实发布时间；无摘要的不补造，不将最后修改时间当作发布时间。')
 (service.db_path.parent/'history_7d.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 return report


async def main():
 service=NewsService(Path(__file__).parent/'data'/'news.db')
 try:await run(service)
 finally:await service.close()


if __name__=='__main__':asyncio.run(main())
