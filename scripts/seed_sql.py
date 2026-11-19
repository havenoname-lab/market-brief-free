"""Build a private, consistent migration SQL file from an existing local news DB."""
import json,sqlite3,tempfile
from pathlib import Path
from news_web.service import NewsService
from news_web.analysis import AnalysisService
from scripts.sync_state import dump_states,restore_states,dump_collector,restore_collector,records
from scripts.cloud_sync import make_snapshots


def quote(value):
 return str(value) if isinstance(value,int) else "'"+str(value).replace("'","''")+"'"


def seed(source_path,output):
 with tempfile.TemporaryDirectory(prefix='market-brief-seed-') as directory:
  original=sqlite3.connect(source_path);backup=sqlite3.connect(Path(directory)/'source.db')
  try:original.backup(backup)
  finally:original.close();backup.close()
  source=NewsService(Path(directory)/'source.db');target=NewsService(Path(directory)/'merged.db')
  restore_states(target,dump_states(source));restore_collector(target,dump_collector(source))
  status=AnalysisService(target,config_path=Path(directory)/'none.json').status()
  status.update(configured=True,backend='workers_ai_free',quota_paused=False,free_daily_application_cap=100)
  article_records=records(target);snapshots=make_snapshots(target,status)
  with Path(output).open('w',encoding='utf-8',newline='\n') as stream:
   for row in article_records:
    values=[row['id'],row['source_id'],row['effective_ms'],json.dumps(row['tags'],ensure_ascii=False),row['search_text'],json.dumps(row['payload'],ensure_ascii=False),json.dumps(row['state'],ensure_ascii=False),row['content_hash']]
    stream.write('INSERT OR REPLACE INTO articles VALUES('+','.join(quote(v) for v in values)+');\n')
   for item in snapshots:
    values=[item['key'],json.dumps(item['value'],ensure_ascii=False),status.get('last_success') or 'migration']
    stream.write('INSERT OR REPLACE INTO snapshots VALUES('+','.join(quote(v) for v in values)+');\n')
  print('Prepared private migration:',len(article_records),'articles,',len(snapshots),'snapshots')
  return len(article_records)


if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('output');args=parser.parse_args();seed(args.source,args.output)
