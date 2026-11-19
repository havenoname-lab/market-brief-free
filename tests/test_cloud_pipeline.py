import gzip,json,base64,sqlite3
from datetime import datetime,timezone,timedelta
from news_web.service import NewsService
from scripts.cloud_sync import make_snapshots,unpack


def test_scheduled_half_hour_gap_is_not_reported_as_outage(tmp_path):
 s=NewsService(tmp_path/'n.db')
 s.record_channel('bbc','primary','ok',None,1)
 with s.connect() as db:db.execute('UPDATE channel_status SET last_attempt=?',((datetime.now(timezone.utc)-timedelta(minutes=40)).isoformat(),))
 s.record_channel('bbc','primary','ok',None,1)
 assert s.continuity()['gap_count']==0
 with s.connect() as db:db.execute('UPDATE channel_status SET last_attempt=?',((datetime.now(timezone.utc)-timedelta(minutes=80)).isoformat(),))
 s.record_channel('bbc','primary','ok',None,1)
 assert s.continuity()['gap_count']==1


def test_cloud_snapshots_preserve_all_three_windows(tmp_path):
 s=NewsService(tmp_path/'n.db')
 s.save_rows([dict(id='a',source_id='bbc',title='Oil prices rise',summary='',url='https://example.com/a',published_at=None,impact='待分析')])
 snapshots={r['key']:unpack(r['value']) for r in make_snapshots(s,{'configured':True})}
 assert all(snapshots['sector-board-'+str(h)]['total_articles']==1 for h in (24,72,168))
 assert snapshots['sources']['refresh_interval_seconds']==1800


def test_snapshot_wrapper_round_trips_without_data_loss():
 original={'title':'中文标题','news':['x'*1000]*200}
 packed={'_gzip':base64.b64encode(gzip.compress(json.dumps(original,ensure_ascii=False).encode())).decode()}
 assert unpack(packed)==original
