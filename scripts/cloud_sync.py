"""Finite scheduled collection job. Credentials come exclusively from environment variables."""
import asyncio,argparse,json,os,re,sqlite3,tempfile,time,gzip,base64
from pathlib import Path
from datetime import datetime,timezone,timedelta
import httpx
from news_web.service import NewsService
from news_web.analysis import AnalysisService,fingerprint
from news_web.topics import TOPICS,classify
from scripts.sync_state import dump_states,restore_states,records,dump_collector,restore_collector


class QuotaPause(Exception):pass


def unpack(value):
 return json.loads(gzip.decompress(base64.b64decode(value['_gzip']))) if value and '_gzip' in value else value


def make_snapshots(service,status):
 snapshots=[dict(key='sources',value={'sources':service.sources(),'refresh_interval_seconds':1800,'refreshing':False,'mode':'free_cloud'}),
    dict(key='topics',value={'topics':TOPICS,'method':'标题与公开摘要关键词规则，多标签，可能误分'}),
    dict(key='continuity',value=service.continuity()),dict(key='analysis/status',value=status),
    dict(key='_collector_state',value=dump_collector(service))]
 for hours in (24,72,168):
  board=service.sector_board(hours)
  for sector in board['sectors']:
   for direction in ('positive','negative','uncertain'):
    for item in sector[direction]:
     item['verification']={k:v for k,v in item['verification'].items() if k in ('targets','status')}
  snapshots.extend([dict(key='sector-board-'+str(hours),value=board),dict(key='history-coverage-'+str(hours),value=service.history_coverage(hours))])
 for item in snapshots:
  raw=json.dumps(item['value'],ensure_ascii=False).encode()
  if len(raw)>70000:item['value']={'_gzip':base64.b64encode(gzip.compress(raw,mtime=0)).decode()}
  if len(json.dumps(item,ensure_ascii=False).encode())>180000:raise ValueError('Snapshot exceeds cloud envelope: '+item['key'])
 return snapshots


class Cloud:
 def __init__(self):
  base=os.environ['CLOUD_BASE_URL'].rstrip('/')
  if not base.startswith('https://'):raise ValueError('Cloud endpoint must use HTTPS')
  token=os.environ['SYNC_TOKEN']
  if len(token)<24:raise ValueError('Sync token is too short')
  self.client=httpx.AsyncClient(base_url=base,headers={'Authorization':'Bearer '+token},timeout=120)
 async def call(self,method,path,**kwargs):
  for attempt in range(3):
   try:
    response=await self.client.request(method,path,**kwargs)
    if response.status_code==429 and path.endswith('/ai'):raise QuotaPause()
    if response.status_code>=500 and attempt<2:await asyncio.sleep(2*(attempt+1));continue
    response.raise_for_status();return response.json()
   except (httpx.TransportError,) as exc:
    if attempt==2:raise RuntimeError('Cloud transport failed') from None
    await asyncio.sleep(2*(attempt+1))
  raise RuntimeError('Cloud API unavailable')
 async def restore(self,service):
  after='';total=0
  while True:
   data=await self.call('GET','/api/admin/state',params={'after':after,'limit':100})
   restore_states(service,data['states'])
   if not after:restore_collector(service,unpack(data.get('collector')))
   total+=len(data['states']);after=data['next_after']
   if not data['has_more']:break
  print('Restored',total,'cloud article states',flush=True)
 async def upload(self,service,status):
  snapshots=make_snapshots(service,status)
  hashes={};after=''
  while True:
   previous=await self.call('GET','/api/admin/manifest',params={'after':after})
   hashes.update({r['id']:r['content_hash'] for r in previous['articles']})
   if not previous['has_more']:break
   after=previous['next_after']
  changed=[r for r in records(service) if hashes.get(r['id'])!=r['content_hash']]
  batch=[];size=0
  async def send(items):await self.call('POST','/api/admin/import',json={'records':items})
  for record in changed:
   item_size=len(json.dumps(record,ensure_ascii=False).encode())
   if item_size>180000:raise ValueError('An article exceeds the bounded sync batch size')
   if batch and (len(batch)>=10 or size+item_size>180000):await send(batch);batch=[];size=0
   batch.append(record);size+=item_size
  if batch:await send(batch)
  # Snapshots can be large; keep each request inside the same bounded import envelope.
  for item in snapshots:
   body={'records':[],'snapshots':[item]}
   if len(json.dumps(body,ensure_ascii=False).encode())>190000:raise ValueError('Snapshot exceeds cloud envelope: '+item['key'])
   await self.call('POST','/api/admin/import',json=body)
  print('Synced',len(changed),'changed articles and',len(snapshots),'snapshots',flush=True)
  return len(changed)


async def analyze(service,cloud,limit):
 analysis=AnalysisService(service,config_path=service.db_path.parent/'unused_ai_config.json')
 with service.connect() as db:
  rows=[dict(r) for r in db.execute('SELECT * FROM articles ORDER BY COALESCE(published_at,first_seen) DESC')]
  old={r['article_id']:dict(r) for r in db.execute('SELECT * FROM article_analysis')}
  diagnostics={r['article_id']:dict(r) for r in db.execute('SELECT * FROM analysis_diagnostics')}
 rows.sort(key=lambda r:0 if classify(r['title'],r['summary'])!=['其他'] else 1)
 calls=0;paused=False;started=time.monotonic()
 for row in rows:
  if calls>=limit:break
  now=datetime.now(timezone.utc)
  if datetime.fromisoformat(row['published_at'] or row['first_seen'])<now-timedelta(days=7):continue
  previous=old.get(row['id']);current=fingerprint(row);diagnostic=diagnostics.get(row['id'])
  if previous and previous['content_hash']==current and previous['status']=='ready' and json.loads(previous['payload'] or '{}').get('chain_version')==2:continue
  if diagnostic and diagnostic['content_hash']==current:
   if diagnostic['attempts']>=3 or (diagnostic['retry_at'] and datetime.fromisoformat(diagnostic['retry_at'])>now):continue
  generated=None
  try:
   calls+=1
   data=await cloud.call('POST','/api/admin/ai',json={'title':row['title'],'summary':row['summary']})
   raw=data['response']
   if isinstance(raw,str):
    raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip());generated=json.loads(raw)
   else:generated=raw
   analysis.save(row,generated,provider='mechanism_upgrade',require_chain=True)
   with service.connect() as db:db.execute("UPDATE article_analysis SET provider='workers_ai_free' WHERE article_id=?",(row['id'],))
   analysis.last_success=now.isoformat()
  except QuotaPause:paused=True;break
  except Exception as exc:
   analysis.record_failure(row,exc,generated)
  await asyncio.sleep(.5)
 status=analysis.status();status.update(configured=True,backend='workers_ai_free',processing=False,quota_paused=paused,
     last_duration_seconds=round(time.monotonic()-started,1),last_success=analysis.last_success,cadence_seconds=1800,
     free_daily_application_cap=100,scope='仅公开标题与摘要；免费AI额度内排队；未接入行情')
 print('AI attempts',calls,'quota_paused',paused,flush=True)
 return status


async def run(args):
 cloud=Cloud()
 with tempfile.TemporaryDirectory(prefix='market-brief-') as directory:
  service=NewsService(Path(directory)/'news.db')
  try:
   if args.seed_db:
    source_db=sqlite3.connect(args.seed_db);copy_db=sqlite3.connect(Path(directory)/'seed.db')
    try:source_db.backup(copy_db)
    finally:source_db.close();copy_db.close()
    source=NewsService(Path(directory)/'seed.db')
    restore_states(service,dump_states(source));restore_collector(service,dump_collector(source))
   else:await cloud.restore(service)
   if not args.seed_db or args.collect:
    await service.refresh()
    # Supplement public indexes at least once per UTC day, without rerunning on every view.
    with service.connect() as db:
     last=db.execute("SELECT max(finished_at) FROM backfill_runs WHERE channel='public_news_index'").fetchone()[0]
    if args.history or not last or datetime.fromisoformat(last).date()!=datetime.now(timezone.utc).date():
     from news_web.history import run as history
     await history(service,days=7)
   status=await analyze(service,cloud,args.ai_limit)
   await cloud.upload(service,status)
  finally:await service.close();await cloud.client.aclose()


if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--seed-db');parser.add_argument('--collect',action='store_true');parser.add_argument('--history',action='store_true');parser.add_argument('--ai-limit',type=int,default=2)
 args=parser.parse_args()
 if not 0<=args.ai_limit<=16:parser.error('ai-limit must be between 0 and 16')
 asyncio.run(run(args))
