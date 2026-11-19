from __future__ import annotations

import asyncio
import os
import logging
import hashlib
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime, timezone

from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from news_web.service import NewsService
from news_web.topics import TOPICS
from news_web.access import configure_access
from news_web.analysis import AnalysisService

ROOT = Path(__file__).resolve().parent


def ui_version():
    digest=hashlib.sha256()
    for name in ('index.html','app.js','styles.css','topics.css'):
        digest.update((ROOT/'static'/name).read_bytes())
    return digest.hexdigest()[:12]


def create_app(service=None, background=True):
    svc = service or NewsService(os.getenv('NEWS_DB_PATH', str(ROOT / 'data' / 'news.db')))
    analysis = AnalysisService(svc)

    async def analysis_loop():
        await asyncio.sleep(5)
        while True:
            try:
                await analysis.run_batch(limit=max(1,min(8,int(analysis.config().get('batch_size',8)))))
            except Exception:
                logging.exception('News analysis failed; retrying later')
            await asyncio.sleep(max(5,int(analysis.config().get('poll_seconds',60))))

    async def refresh_loop():
        await asyncio.sleep(2)
        previous_gaps = svc.continuity()['gap_count']
        while True:
            try:
                await svc.refresh()
                continuity = svc.continuity()
                with svc.connect() as db:
                    last = db.execute('SELECT max(finished_at) FROM backfill_runs').fetchone()[0]
                due = not last or (datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds()>86400
                if due or continuity['gap_count']>previous_gaps:
                    from news_web.backfill import run
                    await run(svc,max_pages=3)
                    from news_web.history import run as import_public_indexes
                    await import_public_indexes(svc,days=7)
                previous_gaps=continuity['gap_count']
            except Exception:
                logging.exception('News refresh failed; retrying next cycle')
            await asyncio.sleep(300)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(refresh_loop()) if background else None
        analysis_task=asyncio.create_task(analysis_loop()) if background else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if analysis_task:
            analysis_task.cancel()
            with suppress(asyncio.CancelledError):
                await analysis_task
        await svc.close()

    app = FastAPI(title='Market Brief · 财经新闻台', lifespan=lifespan)
    configure_access(app)
    app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='news-static')

    @app.middleware('http')
    async def ui_cache_control(request,call_next):
        response=await call_next(request)
        if request.url.path in ('/','/api/ui-version'):
            response.headers['Cache-Control']='no-store'
        elif request.url.path.startswith('/static/'):
            response.headers['Cache-Control']='no-cache'
        return response

    @app.get('/healthz')
    def health():
        return {'ok': True}

    @app.get('/')
    def index():
        version=ui_version()
        html=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
        for name in ('app.js','styles.css','topics.css'):
            html=html.replace('/static/'+name,'/static/'+name+'?v='+version)
        html=html.replace('</head>','<meta name="ui-version" content="'+version+'"></head>')
        return HTMLResponse(html)

    @app.get('/api/ui-version')
    def current_ui_version():
        return {'version':ui_version()}

    @app.get('/api/articles')
    def articles(source: str = '', q: str = Query('', max_length=200), topic: str = '', offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),hours:int=Query(168,ge=1,le=168)):
        if topic and topic not in TOPICS:
            raise HTTPException(status_code=422, detail='未知新闻分类')
        rows=svc.articles(source=source, query=q, topic=topic,offset=offset,limit=limit+1,hours=hours)
        return {'articles': rows[:limit],'has_more':len(rows)>limit,'offset':offset}

    @app.get('/api/continuity')
    def continuity():
        return svc.continuity()

    @app.get('/api/sector-board')
    def sector_board(hours:int=Query(168,ge=1,le=168)):
        return svc.sector_board(hours)

    @app.get('/api/history-coverage')
    def history_coverage(hours:int=Query(168,ge=1,le=168)):
        return svc.history_coverage(hours)

    @app.get('/api/analysis/status')
    def analysis_status():
        return analysis.status()

    @app.get('/api/topics')
    def topics():
        return {'topics': TOPICS, 'method': '标题与公开摘要关键词规则，支持多标签；可能误分或漏分'}

    @app.get('/api/sources')
    def sources():
        return {'sources': svc.sources(), 'refresh_interval_seconds': 300,
                'refreshing': svc.lock.locked(), 'mode': 'framework'}

    @app.post('/api/refresh')
    async def refresh(request: Request):
        # Local-only service: reject cross-site mutation from arbitrary browser pages.
        origin = request.headers.get('origin')
        if origin:
            parsed_origin = urlsplit(origin)
            if parsed_origin.scheme not in ('http', 'https') or parsed_origin.netloc != request.headers.get('host'):
                raise HTTPException(status_code=403, detail='不允许跨站刷新')
        return await svc.refresh()

    return app


app = create_app()
