from __future__ import annotations

import asyncio
import hashlib
import html
import re
import sqlite3
import ssl
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse,parse_qsl,urlencode

import httpx
from news_web.topics import classify
from news_web.continuity import Continuity
from news_web.channels import EXTRA_CHANNELS


SOURCES = [
    ('bbc', 'BBC', 'https://www.bbc.com/business', 'https://feeds.bbci.co.uk/news/business/rss.xml'),
    ('bloomberg', 'Bloomberg', 'https://www.bloomberg.com', 'https://feeds.bloomberg.com/markets/news.rss'),
    ('businessweek', 'Businessweek（英文）', 'https://www.bloomberg.com/businessweek', 'https://feeds.bloomberg.com/businessweek/news.rss'),
    ('wsj', 'WSJ', 'https://www.wsj.com', 'https://feeds.content.dowjones.io/public/rss/RSSMarketsMain'),
    ('espresso', 'The Economist Espresso', 'https://www.economist.com', 'https://www.economist.com/the-world-in-brief/rss.xml'),
    ('forbes', 'Forbes', 'https://www.forbes.com', 'https://www.forbes.com/business/feed/'),
    ('ft', 'Financial Times', 'https://www.ft.com', 'https://www.ft.com/rss/home'),
    ('information', 'The Information', 'https://www.theinformation.com', 'https://www.theinformation.com/feed'),
    ('techinasia', 'Tech in Asia', 'https://www.techinasia.com', 'https://feeds.feedburner.com/PennOlson'),
    ('appygeek', 'Appy Geek', None, None),
    ('washingtonpost', 'Washington Post', 'https://www.washingtonpost.com', 'https://feeds.washingtonpost.com/rss/business'),
]

SOURCE_NOTES = {
    'bbc': 'Business、Technology、World 公开订阅；非全站内容',
    'bloomberg': 'Markets、Technology、Economics 公开标题与摘要，原文可能需订阅',
    'businessweek': '英文版公开订阅；尚未接入图片中的繁体中文版',
    'wsj': 'Markets、Business、Technology 新订阅地址；旧 feeds.a.dj.com 已过时',
    'espresso': '公开 RSS 验证返回 HTTP 403；官方 World in Brief 内容 API 需 Economist Pro 客户授权',
    'forbes': 'Business 栏目公开订阅，非全部 Forbes 内容',
    'ft': '首页、Markets、Technology 公开标题与摘要，原文可能需订阅',
    'information': '仅使用公开订阅的标题与摘要，付费正文仍需订阅',
    'techinasia': '旧 PennOlson 公开订阅，覆盖和更新可能滞后；非官网全量内容',
    'appygeek': '已找到同名应用官方商店与网站，但未确认与截图应用相同，暂无公开文章接口',
    'washingtonpost': 'Business、Technology 公开订阅，原文可能需订阅',
}


def feed_health(rows):
    if not rows:
        return 'empty', '接口可读取，但没有可用文章'
    dates = [datetime.fromisoformat(row['published_at']) for row in rows if row.get('published_at')]
    if not dates:
        return 'undated', '来源未提供可解析的发布时间，无法判断时效'
    age = datetime.now(timezone.utc) - max(dates)
    if age.days >= 14:
        return 'stale', '最新文章已超过 14 天，来源可能停止更新'
    if age.days >= 3:
        return 'delayed', '已有至少 3 天未见新文章，可能更新缓慢或滞后'
    return 'ok', None


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical_article_url(url):
    parts=urlparse(url)
    query=[(k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True)
           if not k.lower().startswith(('utm_','at_')) and k.lower() not in ('mod','cmpid','srnd','fbclid','gclid','reflink','sharetype')]
    return (parts.hostname,(parts.path.rstrip('/') or '/'),urlencode(sorted(query)))


def plain(value):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', '', html.unescape(value or ''))).strip()


def timestamp(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def parse_feed(xml, source_id):
    root = ET.fromstring(xml)
    tag = lambda el: el.tag.rsplit('}', 1)[-1]
    if tag(root) not in ('rss', 'feed', 'RDF'):
        raise ValueError('响应不是 RSS 或 Atom 新闻源')
    rows = []
    for entry in root.iter():
        if tag(entry) not in ('item', 'entry'):
            continue
        values = {tag(child): child.text or '' for child in entry}
        links = [child for child in entry if tag(child) == 'link']
        link = next((child.get('href') or child.text or '' for child in links
                     if child.get('rel', 'alternate') == 'alternate'), '').strip()
        parsed = urlparse(link)
        title = plain(values.get('title'))
        if not title or parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.username:
            continue
        rows.append(dict(
            id=hashlib.sha256(f'{source_id}:{link}'.encode()).hexdigest()[:24],
            source_id=source_id, title=title[:1000], url=link,
            summary=plain(values.get('description') or values.get('summary'))[:1200],
            published_at=timestamp(values.get('pubDate') or values.get('published') or values.get('updated')),
            impact='待分析',
        ))
    return rows


class NewsService(Continuity):
    def __init__(self, db_path, fetch=None, extra_channels=True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.fetch = fetch or self.fetch_public
        self.lock = asyncio.Lock()
        self.extra_channels = extra_channels
        self.semaphore = asyncio.Semaphore(4)
        self._http_client=None
        self._http_init_lock=asyncio.Lock()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY, source_id TEXT, title TEXT, url TEXT, summary TEXT,
                    published_at TEXT, first_seen TEXT, impact TEXT);
                CREATE TABLE IF NOT EXISTS source_status (
                    id TEXT PRIMARY KEY, status TEXT, last_attempt TEXT, last_success TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS article_analysis (
                    article_id TEXT PRIMARY KEY,content_hash TEXT,status TEXT,payload TEXT,
                    analyzed_at TEXT,provider TEXT,error TEXT);
                CREATE TABLE IF NOT EXISTS analysis_diagnostics (
                    article_id TEXT PRIMARY KEY,content_hash TEXT,attempts INTEGER,code TEXT,
                    detail TEXT,retry_at TEXT,updated_at TEXT);
            ''')
        self.init_continuity()

    def save_rows(self, rows):
        inserted = 0
        with self.connect() as db:
            identities={(r['source_id'],canonical_article_url(r['url'])):r['id'] for r in db.execute('SELECT id,source_id,url FROM articles')}
            for row in rows:
                key=(row['source_id'],canonical_article_url(row['url']))
                if key in identities:row=dict(row,id=identities[key])
                else:identities[key]=row['id']
                exists=db.execute('SELECT 1 FROM articles WHERE id=?',(row['id'],)).fetchone()
                db.execute('''INSERT INTO articles VALUES (:id,:source_id,:title,:url,:summary,
                    :published_at,:first_seen,:impact) ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, summary=CASE WHEN excluded.summary<>'' THEN excluded.summary ELSE articles.summary END,
                    published_at=COALESCE(excluded.published_at,articles.published_at)''',dict(row,first_seen=now()))
                inserted += int(not exists)
        return inserted

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    async def fetch_public(self, url):
        if self._http_client is None:
            async with self._http_init_lock:
                if self._http_client is None:
                    context=await asyncio.to_thread(ssl.create_default_context)
                    self._http_client=httpx.AsyncClient(timeout=18,follow_redirects=True,verify=context)
        async with self._http_client.stream('GET', url, headers={'User-Agent': 'JoyceNewsReader/0.1'}) as res:
                res.raise_for_status()
                body = bytearray()
                async for part in res.aiter_bytes():
                    body.extend(part)
                    if len(body) > 3_000_000:
                        raise ValueError('新闻源响应过大')
                return bytes(body)

    async def close(self):
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client=None

    async def refresh(self):
        if self.lock.locked():
            return {'status': 'busy'}
        async with self.lock:
            await asyncio.gather(*(self.refresh_source(source) for source in SOURCES if source[3]))
        return {'status': 'complete'}

    async def refresh_source(self, source):
        if self.extra_channels:
            channels=[('primary',source[3]),*EXTRA_CHANNELS.get(source[0],[])]
        else:
            channels=[('primary',source[3])]
        results=await asyncio.gather(*(self.refresh_channel(source[0],key,url) for key,url in channels if url))
        if not results:
            return
        states=[r[0] for r in results]
        state='ok' if all(s=='ok' for s in states) else 'partial' if 'ok' in states else states[0]
        error=None if state=='ok' else '；'.join(r[1] for r in results if r[1])
        with self.connect() as db:
            db.execute('''INSERT INTO source_status VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,last_attempt=excluded.last_attempt,
                last_success=COALESCE(excluded.last_success,source_status.last_success),error=excluded.error''',
                (source[0],state,now(),now() if 'ok' in states else None,error))

    async def refresh_channel(self, source_id, channel, feed_url):
        async with self.semaphore:
            return await self._refresh_channel(source_id,channel,feed_url)

    async def _refresh_channel(self, source_id, channel, feed_url):
        attempt = now()
        try:
            rows = parse_feed(await self.fetch(feed_url), source_id)
            status, warning = feed_health(rows)
            self.save_rows(rows)
            self.record_channel(source_id,channel,status,warning,len(rows))
            return status,warning
        except Exception as exc:
            message = '连接或解析失败，请稍后重试'
            if isinstance(exc, httpx.HTTPStatusError):
                message = f'来源返回 HTTP {exc.response.status_code}'
            self.record_channel(source_id,channel,'error',message,0)
            return 'error',channel+': '+message

    def articles(self, source='', query='', limit=200, topic='', offset=0, hours=None):
        with self.connect() as db:
            results = []
            import json
            from news_web.analysis import fingerprint
            analyses={r['article_id']:dict(r) for r in db.execute('SELECT * FROM article_analysis')}
            diagnostics={r['article_id']:dict(r) for r in db.execute('SELECT * FROM analysis_diagnostics')}
            current=datetime.now(timezone.utc)
            for row in db.execute('''SELECT * FROM articles
                WHERE (? = '' OR source_id = ?)
                ORDER BY COALESCE(published_at,first_seen) DESC, id DESC''',
                (source, source)):
                article = dict(row)
                if hours is not None and not current-timedelta(hours=hours)<=datetime.fromisoformat(article['published_at'] or article['first_seen'])<=current:
                    continue
                analysis=analyses.get(article['id'])
                article.update(analysis_status='pending',price_reaction=None,analysis_basis='仅公开标题和摘要，未接入实时行情')
                if analysis:
                    article['analysis_status']=analysis['status'] if analysis['content_hash']==fingerprint(article) else 'stale'
                    article['analyzed_at']=analysis['analyzed_at']
                    if article['analysis_status'] in ('ready','partial') and analysis['payload']:
                        article.update(json.loads(analysis['payload']))
                        article['impact']=article.get('direction','待完善链条')
                    from news_web.analysis import ERROR_MESSAGES
                    diagnostic=diagnostics.get(article['id'])
                    article['analysis_error_code']=analysis['error']
                    article['analysis_error']=ERROR_MESSAGES.get(analysis['error'],'旧记录缺少具体原因，等待重新生成' if analysis['error'] else None)
                    article['retry_at']=diagnostic['retry_at'] if diagnostic else None
                    article['analysis_attempts']=diagnostic['attempts'] if diagnostic else 0
                    article['needs_review']=bool(diagnostic and diagnostic['attempts']>=3)
                article['tags'] = classify(article['title'], article['summary'])
                from news_web.signals import assess_exposures
                article['sector_impacts'] = assess_exposures(article)
                if query and query.casefold() not in ' '.join(str(article.get(k,'')) for k in ('title','summary','title_zh','summary_zh')).casefold():
                    continue
                if topic and topic not in article['tags']:
                    continue
                if offset:
                    offset-=1
                    continue
                results.append(article)
                if len(results) >= limit:
                    break
            return results

    def sector_board(self,hours=24):
        from news_web.signals import sector_board
        # Entire stored set, independent of feed pagination and sidebar filters.
        with self.connect() as db:
            count=db.execute('SELECT count(*) FROM articles').fetchone()[0]
        return sector_board(self.articles(limit=max(1,count)),hours=hours)

    def history_coverage(self,hours=168):
        import json
        current=datetime.now(timezone.utc);since=current-timedelta(hours=hours)
        groups={key:dict(source_id=key,name=name,count=0,oldest=None,newest=None,undated=0,complete=False) for key,name,_,_ in SOURCES}
        with self.connect() as db:
            rows=db.execute('SELECT source_id,published_at,first_seen FROM articles').fetchall()
        for row in rows:
            stamp=row['published_at'] or row['first_seen']
            if not since<=datetime.fromisoformat(stamp)<=current:continue
            group=groups[row['source_id']];group['count']+=1
            if not row['published_at']:group['undated']+=1;continue
            group['oldest']=min(group['oldest'] or stamp,stamp)
            group['newest']=max(group['newest'] or stamp,stamp)
        reports=[]
        for name in ('history_7d.json','archive_7d.json'):
            try:reports.append(json.loads((self.db_path.parent/name).read_text(encoding='utf-8')))
            except (OSError,ValueError):pass
        return dict(hours=hours,since=since.isoformat(),until=current.isoformat(),sources=list(groups.values()),
            total=sum(g['count'] for g in groups.values()),complete=False,last_backfills=reports,
            note='以下为已收录范围，最早与最晚日期不代表中间无漏文；无发布时间按首次收录计时。')

    def sources(self):
        with self.connect() as db:
            states = {row['id']: dict(row) for row in db.execute('SELECT * FROM source_status')}
            counts = {row[0]: row[1] for row in db.execute('SELECT source_id, count(*) FROM articles GROUP BY source_id')}
        return [dict(id=key, name=name, homepage=home, configured=bool(feed),
                     feed_url=feed, note=SOURCE_NOTES.get(key, ''),
                     status=states.get(key, {}).get('status', 'unverified' if feed else 'pending'),
                     last_attempt=states.get(key, {}).get('last_attempt'),
                     last_success=states.get(key, {}).get('last_success'),
                     error=states.get(key, {}).get('error'), count=counts.get(key, 0))
                for key, name, home, feed in SOURCES]
