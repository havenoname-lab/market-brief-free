import asyncio,json
from pathlib import Path
from news_web.service import NewsService,SOURCES
from news_web.channels import EXTRA_CHANNELS

async def run(service,source_id='',max_pages=5):
 if service.lock.locked():return {'status':'busy'}
 async with service.lock:
  results=[]
  for key,_,_,url in SOURCES:
   if not url or (source_id and key!=source_id):continue
   template={'forbes':'https://www.forbes.com/business/feed/?paged={page}',
             'information':'https://www.theinformation.com/feed?page={page}'}.get(key)
   results.append(await service.backfill_feed(key,'primary',url,template,max_pages))
   if service.extra_channels:
    for channel,extra_url in EXTRA_CHANNELS.get(key,[]):
     results.append(await service.backfill_feed(key,channel,extra_url,None,max_pages))
  return {'status':'complete','results':results,'complete_history':False}

if __name__=='__main__':
 s=NewsService(Path(__file__).parent/'data'/'news.db')
 print(json.dumps(asyncio.run(run(s)),ensure_ascii=True))
