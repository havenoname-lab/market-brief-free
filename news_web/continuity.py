import json
import xml.etree.ElementTree as ET
from datetime import datetime,timezone
from urllib.parse import urljoin,urlparse


def next_page(xml,current):
 root=ET.fromstring(xml)
 for link in root.iter():
  if link.tag.rsplit('}',1)[-1]=='link' and link.get('rel')=='next':
   target=urljoin(current,link.get('href',''))
   if urlparse(target).scheme=='https' and urlparse(target).netloc==urlparse(current).netloc:
    return target
 return None


class Continuity:
 def init_continuity(self):
  with self.connect() as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS channel_status (
    source_id TEXT, channel TEXT, status TEXT, last_attempt TEXT, error TEXT, count INTEGER,
    PRIMARY KEY(source_id,channel));
    CREATE TABLE IF NOT EXISTS gaps (id INTEGER PRIMARY KEY,source_id TEXT,channel TEXT,
    start TEXT,end TEXT,reason TEXT,status TEXT DEFAULT 'unverified');
    CREATE TABLE IF NOT EXISTS backfill_runs(id INTEGER PRIMARY KEY,source_id TEXT,
    channel TEXT,finished_at TEXT,result TEXT);''')

 def record_channel(self,source,channel,status,error,count):
  current=datetime.now(timezone.utc)
  with self.connect() as db:
   old=db.execute('SELECT * FROM channel_status WHERE source_id=? AND channel=?',(source,channel)).fetchone()
   if old and (current-datetime.fromisoformat(old['last_attempt'])).total_seconds()>4500:
    db.execute('INSERT INTO gaps(source_id,channel,start,end,reason) VALUES(?,?,?,?,?)',
     (source,channel,old['last_attempt'],current.isoformat(),'超过75分钟没有采集检查，完整性未核实'))
   if status=='error' and (not old or old['status']!='error'):
    db.execute('INSERT INTO gaps(source_id,channel,start,end,reason) VALUES(?,?,?,?,?)',
     (source,channel,current.isoformat(),None,'抓取失败，可能存在漏文'))
   if old and old['status']=='error' and status!='error':
    db.execute('UPDATE gaps SET end=? WHERE source_id=? AND channel=? AND end IS NULL',
     (current.isoformat(),source,channel))
   db.execute('INSERT OR REPLACE INTO channel_status VALUES(?,?,?,?,?,?)',
    (source,channel,status,current.isoformat(),error,count))

 def continuity(self):
  with self.connect() as db:
   return {'channels':[dict(r) for r in db.execute('SELECT * FROM channel_status ORDER BY source_id,channel')],
    'gaps':[dict(r) for r in db.execute('SELECT * FROM gaps ORDER BY id DESC LIMIT 100')],
    'gap_count':db.execute('SELECT count(*) FROM gaps').fetchone()[0],
    'backfills':[dict(r) for r in db.execute('SELECT * FROM backfill_runs ORDER BY id DESC LIMIT 20')],
    'scope':'仅检测启用记录之后的停机和失败，恢复采集不代表漏文已补齐'}

 async def backfill_feed(self,source,channel,url,template=None,max_pages=10):
  from news_web.service import parse_feed
  visited=set(); seen=set(); pages=0;new=0;reason='page_limit';error=None
  for page in range(1,max_pages+1):
   if not url or url in visited:
    reason='no_next_page';break
   visited.add(url)
   try:
    xml=await self.fetch(url);rows=parse_feed(xml,source);pages+=1
    ids={r['id'] for r in rows}
    if not ids:
     reason='empty_page';break
    if ids<=seen:
     reason='repeated_page';break
    seen.update(ids);new+=self.save_rows(rows)
    following=next_page(xml,url)
    url=following or (template.format(page=page+1) if template else None)
   except Exception as exc:
    reason='fetch_failed';error=type(exc).__name__;break
  result={'source':source,'channel':channel,'pages':pages,'inserted':new,
   'stop_reason':reason,'error':error,'complete_history':False}
  with self.connect() as db:
   db.execute('INSERT INTO backfill_runs(source_id,channel,finished_at,result) VALUES(?,?,?,?)',
    (source,channel,datetime.now(timezone.utc).isoformat(),json.dumps(result)))
  return result
