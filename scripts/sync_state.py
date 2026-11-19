"""Lossless local/cloud record serialization; contains no account credentials."""
import hashlib
import json
from news_web.service import canonical_article_url


def dump_states(service):
 with service.connect() as db:
  analyses={r['article_id']:dict(r) for r in db.execute('SELECT * FROM article_analysis')}
  diagnostics={r['article_id']:dict(r) for r in db.execute('SELECT * FROM analysis_diagnostics')}
  rows=[dict(r) for r in db.execute('SELECT * FROM articles ORDER BY first_seen,id')]
 return [dict(row=row,analysis=analyses.get(row['id']),diagnostic=diagnostics.get(row['id'])) for row in rows]


def restore_states(service,states):
 rows=[state['row'] for state in states]
 if not rows:return
 service.save_rows(rows)
 with service.connect() as db:
  identities={(r['source_id'],canonical_article_url(r['url'])):r['id'] for r in db.execute('SELECT id,source_id,url FROM articles')}
  for state in states:
   row=state['row'];identity=identities[(row['source_id'],canonical_article_url(row['url']))]
   db.execute('UPDATE articles SET first_seen=min(first_seen,?) WHERE id=?',(row['first_seen'],identity))
   analysis=state.get('analysis')
   if analysis:
    db.execute('INSERT OR REPLACE INTO article_analysis VALUES(?,?,?,?,?,?,?)',
      (identity,analysis['content_hash'],analysis['status'],analysis['payload'],analysis['analyzed_at'],analysis['provider'],analysis['error']))
   diagnostic=state.get('diagnostic')
   if diagnostic:
    db.execute('INSERT OR REPLACE INTO analysis_diagnostics VALUES(?,?,?,?,?,?,?)',
      (identity,diagnostic['content_hash'],diagnostic['attempts'],diagnostic['code'],diagnostic['detail'],diagnostic['retry_at'],diagnostic['updated_at']))


def records(service):
 from datetime import datetime
 states={item['row']['id']:item for item in dump_states(service)}
 result=[]
 for payload in service.articles(limit=max(1,len(states))):
  row=states[payload['id']]['row']
  record=dict(id=row['id'],source_id=row['source_id'],effective_ms=int(datetime.fromisoformat(row['published_at'] or row['first_seen']).timestamp()*1000),
      tags=payload['tags'],search_text=' '.join(str(payload.get(k,'')) for k in ('title','summary','title_zh','summary_zh')).lower(),
      payload=payload,state=states[row['id']])
  record['content_hash']=hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
  result.append(record)
 return result


TABLES=('source_status','channel_status','gaps','backfill_runs')
def dump_collector(service):
 data={}
 with service.connect() as db:
  for table in TABLES:
   order=' ORDER BY id DESC LIMIT 200' if table in ('gaps','backfill_runs') else ''
   data[table]=[dict(r) for r in db.execute('SELECT * FROM '+table+order)]
 return data


def restore_collector(service,data):
 if not data:return
 with service.connect() as db:
  for table in TABLES:
   columns=[row[1] for row in db.execute('PRAGMA table_info('+table+')')]
   for row in data.get(table,[]):
    db.execute('INSERT OR REPLACE INTO '+table+' ('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(row.get(k) for k in columns))
