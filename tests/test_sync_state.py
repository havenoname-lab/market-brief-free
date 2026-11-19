from news_web.service import NewsService
from scripts.sync_state import dump_states,restore_states,records


def test_cloud_roundtrip_preserves_publication_and_first_seen(tmp_path):
 source=NewsService(tmp_path/'source.db');target=NewsService(tmp_path/'target.db')
 source.save_rows([dict(id='a',source_id='bbc',title='Chip sales rise',summary='Real public summary',url='https://example.com/a',published_at='2026-11-17T12:00:00+00:00',impact='待分析')])
 original=dump_states(source)
 restore_states(target,original)
 assert dump_states(target)==original
 assert records(target)[0]['effective_ms']==1794916800000


def test_record_hash_changes_on_source_correction(tmp_path):
 s=NewsService(tmp_path/'n.db')
 row=dict(id='a',source_id='bbc',title='Oil prices rise',summary='',url='https://example.com/a',published_at=None,impact='待分析')
 s.save_rows([row]);before=records(s)[0]['content_hash']
 s.save_rows([dict(row,title='Oil prices fall')]);after=records(s)[0]['content_hash']
 assert before!=after
