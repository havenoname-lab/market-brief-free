const state = {sources: [], source: '', articles: [], query: '', unread: false, topics: [], topic: '', offset:0, hasMore:false};
let seen;
try { seen = new Set(JSON.parse(localStorage.getItem('market-brief-read') || '[]')); }
catch { seen = new Set(); }
const el = id => document.getElementById(id);
const labels = {ok: '检查成功', partial: '部分栏目异常', error: '检查失败', unverified: '等待首次检查', pending: '待接入', empty: '暂无文章', stale: '更新停滞', undated: '日期未知', delayed: '更新可能滞后'};
const fmt = value => value ? new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai', month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)) : '时间未提供';
function node(tag, cls, content) { const n=document.createElement(tag); if(cls)n.className=cls; if(content!==undefined)n.textContent=content; return n; }
async function request(path, options) { const res=await fetch(path, options); if(!res.ok) throw new Error('服务暂时不可用'); return res.json(); }
function sourceName(id){return state.sources.find(s=>s.id===id)?.name || id;}
function selectTopic(topic){state.topic=topic;state.offset=0;renderTopics();loadArticles().catch(showError);}
function renderTopics(){
  el('topic-filters').replaceChildren(...['',...state.topics].map(topic=>{
    const b=node('button','topic-chip'+(state.topic===topic?' selected':''),topic||'全部主题');
    b.type='button';b.setAttribute('aria-pressed',String(state.topic===topic));b.onclick=()=>selectTopic(topic);return b;
  }));
}
function sourceButton(id,name,count){
  const b=node('button','source-button'+(state.source===id?' active':'')); b.type='button'; b.setAttribute('aria-pressed',String(state.source===id));
  b.append(node('span','badge',id?name.charAt(0):'≡'),node('span','',name),node('span','count',String(count)));
  b.onclick=()=>{state.source=id;state.offset=0;renderSources();loadArticles().catch(showError);}; return b;
}
function renderSources(){
  el('source-nav').replaceChildren(sourceButton('','全部新闻',state.sources.reduce((a,s)=>a+s.count,0)),...state.sources.map(s=>sourceButton(s.id,s.name,s.count)));
  el('configured').textContent=state.sources.filter(s=>s.configured).length+' / 11';
  el('healthy').textContent=state.sources.filter(s=>s.status==='ok').length+' / 11';
  el('article-count').textContent=state.sources.reduce((a,s)=>a+s.count,0);
  const times=state.sources.map(s=>s.last_attempt).filter(Boolean).sort();
  el('last-check').textContent=times.length?'上次尝试检查 '+fmt(times.at(-1))+' 北京时间':'尚未执行检查';
  el('source-status').replaceChildren(...state.sources.map(s=>{
    const row=node('div','status-row'); const name=node(s.homepage?'a':'span','source-name',s.name);
    if(s.homepage){name.href=s.homepage;name.target='_blank';name.rel='noopener noreferrer';}
    row.title=s.note||'';
    row.append(name,node('span','status-label '+s.status,labels[s.status]||s.status),node('span','status-detail',[s.error || (s.last_success?'最近成功 '+fmt(s.last_success):s.configured?'等待检查':'待接入'), s.note].filter(Boolean).join(' · ')));return row;
  }));
}
function markRead(id){seen.add(id);try{localStorage.setItem('market-brief-read',JSON.stringify([...seen].slice(-3000)));}catch{} renderArticles();}
function verificationBlock(impacts){
  const block=node('details','verification-block');block.append(node('summary','','股价验证对象与方法（待行情验证）'));
  for(const impact of impacts){
    const row=node('div','verification-item');row.append(node('strong','',impact.sector+' · '+impact.direction+'情景'),node('p','','验证对象：'+impact.verification.targets.join('、')),node('p','','传导依据：'+impact.reason));
    row.append(node('p','','对照基准：'+impact.verification.benchmark));
    const list=node('ul');for(const check of impact.verification.checks)list.append(node('li','',check));row.append(list,node('small','',impact.verification.market_data));block.append(row);
  }
  return block;
}
let boardRequest=0;
let selectedSector='';
function selectSector(sector){
  selectedSector=selectedSector===sector?'':sector;
  for(const tile of el('sector-board').querySelectorAll('.sector-tile')){
    const active=tile.dataset.sector===selectedSector;
    tile.classList.toggle('selected',active);tile.setAttribute('aria-expanded',String(active));
  }
  for(const panel of el('sector-board').querySelectorAll('.sector-card')){
    panel.hidden=panel.dataset.sector!==selectedSector;
    if(!panel.hidden)panel.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
}
async function loadSectorBoard(){
  const version=++boardRequest;
  try{
    const data=await request('/api/sector-board?hours='+el('sector-window').value);if(version!==boardRequest)return;
    el('sector-summary').textContent='最近 '+data.window_hours+' 小时收录 '+data.total_articles+' 篇 · '+data.unclassified_articles+' 篇待识别板块 · '+data.undated_articles+' 篇无发布时间，按首次收录计时 · 汇集于 '+fmt(data.as_of)+'（北京时间）。每栏最多展示 8 条，相同标题去重；每 30 秒刷新，信源计划每 30 分钟检查，调度可能延迟。';
    const panels=[];
    const tiles=data.sectors.map((group,index)=>{
      const active=selectedSector===group.sector;
      const tile=node('button','sector-tile'+(active?' selected':''));tile.type='button';tile.dataset.sector=group.sector;
      tile.setAttribute('aria-expanded',String(active));tile.setAttribute('aria-controls','sector-detail-'+index);
      tile.append(node('strong','',group.sector));
      const counts=node('span','sector-counts');counts.append(node('span','positive-count','利好 '+group.positive_count),node('span','negative-count','利空 '+group.negative_count));
      tile.append(counts,node('small','','待定 '+group.uncertain_count+' · 点击查看详情'));
      tile.onclick=()=>selectSector(group.sector);
      const card=node('article','sector-card');card.id='sector-detail-'+index;card.dataset.sector=group.sector;card.hidden=!active;
      const heading=node('div','sector-detail-heading');heading.append(node('h2','',group.sector+' · 消息详情'));
      const close=node('button','topic-chip','收起详情 ×');close.type='button';close.onclick=()=>{selectSector(group.sector);el('sector-board').querySelectorAll('.sector-tile')[index].focus({preventScroll:true});};heading.append(close);card.append(heading);
      const columns=node('div','signal-columns');
      for(const [key,label] of [['positive','潜在利好'],['negative','潜在利空']]){
        const column=node('section','signal-column '+key);column.append(node('h3','',label+' · '+group[key+'_count']));
        if(!group[key].length)column.append(node('p','signal-empty','此时间段暂无明确消息'));
        for(const [i,item] of group[key].entries()){
          const entry=node('div','signal-entry');const link=node('a','',item.title);link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';entry.append(link);
          entry.append(node('small','',sourceName(item.source_id)+' · '+fmt(item.published_at||item.first_seen)+(item.published_at?'':'（收录）')));
          if(item.summary_zh)entry.append(node('p','',item.summary_zh));
          else entry.append(node('small','','中文概述正在排队生成'));
          entry.append(node('p','signal-reason',item.reason),node('p','signal-target','验证：'+item.verification.targets.join('、')+' · 待行情验证'));
          const evidence=node('details','signal-evidence');evidence.append(node('summary','','查看归类依据'),node('p','',item.evidence),node('small','',item.basis));entry.append(evidence);
          if(i<2)column.append(entry);
          else{let more=column.querySelector('.signal-more');if(!more){more=node('details','signal-more');more.append(node('summary','','展开其余消息'));column.append(more);}more.append(entry);}
        }
        columns.append(column);
      }
      const uncertain=node('details','signal-uncertain');uncertain.append(node('summary','','方向待定 '+group.uncertain_count+' 条（不计入利好利空）'));
      for(const item of group.uncertain){const p=node('p');const a=node('a','',item.title);a.href=item.url;a.target='_blank';a.rel='noopener noreferrer';p.append(a,node('small','',' · '+sourceName(item.source_id)+' · '+fmt(item.published_at||item.first_seen)),node('span','','；验证对象：'+item.verification.targets.join('、')));uncertain.append(p);}
      card.append(columns,uncertain);panels.push(card);return tile;
    });
    el('sector-board').replaceChildren(...tiles,...panels);
  }catch(error){if(version===boardRequest)el('sector-summary').textContent='板块汇集更新失败，已有内容保留；下次自动重试。';}
}
function renderArticles(){
  el('feed-title').textContent=state.source?sourceName(state.source):'最新新闻';
  const rows=state.articles.filter(a=>!state.unread||!seen.has(a.id));
  if(!rows.length){
    const empty=node('div','empty');empty.append(node('strong','',state.query||state.unread||state.topic?'没有符合条件的文章':'新闻源准备就绪，等待内容。'),node('div','',state.source&&!state.sources.find(s=>s.id===state.source)?.configured?'此媒体尚未接入，可在下方查看来源状态。':'可更换筛选条件，或点击“检查新文章”。未接入来源不会生成示例新闻。'));el('articles').replaceChildren(empty);return;
  }
  el('articles').replaceChildren(...rows.map((a,i)=>{
    const card=node('article','news-card'),body=node('div'),meta=node('div','news-meta');
    meta.append(node('span','source',sourceName(a.source_id)),node('time','',a.published_at?fmt(a.published_at):'发布时间未提供'));
    if(!seen.has(a.id))meta.append(node('span','new-tag','未读'));
    const title=node('h3'),link=node('a','',a.title_zh||a.title);link.href=a.url;link.target='_blank';link.rel='noopener noreferrer';link.onclick=()=>markRead(a.id);title.append(link);
    const summary=node('p','',a.summary_zh || (({stale:'新闻已变更，中文概述待更新。',error:'中文内容暂不可用。',pending:'中文解读尚未生成。'}[a.analysis_status]||'')+' '+(a.summary||'来源未提供公开摘要，请前往媒体阅读原文。')));
    const bottom=node('div','news-bottom'),read=node('a','read-link','阅读原文 ↗');read.href=a.url;read.target='_blank';read.rel='noopener noreferrer';read.onclick=()=>markRead(a.id);
    const tags=node('div','article-tags');
    for(const tag of a.tags||[]){const chip=node('button','topic-chip',tag);chip.type='button';chip.title='按此主题筛选（关键词规则）';chip.onclick=()=>selectTopic(tag);tags.append(chip);}
    bottom.append(node('span','impact',a.chain?'潜在影响 · '+a.impact:'完整链条待生成'),read);body.append(meta,title,summary);
    if(a.analysis_error){body.append(node('p','analysis-notice',a.analysis_error+'。'+(a.needs_review?'多次校验未通过，等待复核。':a.retry_at?'下次允许重试 '+fmt(a.retry_at)+'，按队列处理。':'等待重新生成具体诊断。')));}
    if(a.chain){
      const analysis=node('div','analysis-card');analysis.append(node('strong','','潜在股价影响：'+a.direction+' · 置信度'+a.confidence),node('p','',a.rationale));
      analysis.append(node('small','',(a.chain_method||'模型条件分析')+' · '+(a.mechanism_path||'待验证路径')));
      const chain=node('ol','impact-chain');
      for(const [key,label] of [['fact','① 报道事实'],['business','② 业务与产业链'],['financial','③ 财务传导'],['valuation','④ 预期与估值'],['price','⑤ 股价情景']]){
        const step=node('li');step.append(node('strong','',label+(key==='fact'?' · 来源陈述':' · 条件推断')),node('p','',a.chain[key]));chain.append(step);
      }
      analysis.append(chain);
      for(const [key,label] of [['conditions','成立条件'],['risks','反向风险'],['watchpoints','后续验证']]){const block=node('div','chain-support');block.append(node('strong','',label));const list=node('ul');for(const item of a[key]||[])list.append(node('li','',item));block.append(list);analysis.append(block);}
      analysis.append(node('p','','作用时间：'+a.horizon));
      if(a.targets?.length)analysis.append(node('p','','相关公司／行业：'+a.targets.join('、')));
      analysis.append(node('small','','分析时间 '+fmt(a.analyzed_at)+'（北京时间） · 仅依据公开标题和摘要 · 未接入实时行情'));
      body.append(analysis);
    }else if(a.summary_zh && !a.analysis_error){body.append(node('p','analysis-notice','中文概述已就绪；完整财务与估值传导链条正在补充。'));
    }
    const original=node('details','original-text');original.append(node('summary','','查看原文标题与公开摘要'),node('p','',a.title),node('p','',a.summary||'无公开摘要'));body.append(original);
    if(a.sector_impacts?.length)body.append(verificationBlock(a.sector_impacts));
    else body.append(node('p','analysis-notice','股价验证对象待识别：公开摘要尚不足以定位具体板块或公司，暂不加入板块利好／利空。'));
    body.append(tags,bottom);card.append(node('div','news-number',String(i+1).padStart(2,'0')),body);return card;
  }));
}
function showError(){el('feedback').textContent='读取失败，请检查云端服务是否仍在运行。已有内容暂时保留。';}
let articleRequest=0;
async function loadArticles(){const version=++articleRequest;const data=await request('/api/articles?'+new URLSearchParams({source:state.source,q:state.query,topic:state.topic,offset:state.offset,limit:50,hours:el('sector-window').value}));if(version!==articleRequest)return;state.articles=data.articles;state.hasMore=data.has_more;renderArticles();renderPagination();}
function renderPagination(){
 const prev=node('button','topic-chip','上一页'),next=node('button','topic-chip','下一页');prev.disabled=state.offset===0;next.disabled=!state.hasMore;
 prev.onclick=()=>{state.offset=Math.max(0,state.offset-50);loadArticles().catch(showError);};next.onclick=()=>{state.offset+=50;loadArticles().catch(showError);};
 el('pagination').replaceChildren(prev,node('span','disclosure','第 '+(state.offset/50+1)+' 页 · 每页最多 50 篇'),next);
}
async function loadContinuity(){
 const data=await request('/api/continuity');
 el('continuity-summary').textContent='已记录 '+data.channels.length+' 个栏目，'+data.gap_count+' 条可能缺口。恢复采集不代表历史漏文已补齐。采集由云端定时任务执行，调度可能延迟；不依赖本机开机。';
 el('channel-status').replaceChildren(...data.channels.map(c=>node('p','disclosure',sourceName(c.source_id)+' / '+c.channel+' · '+(labels[c.status]||c.status)+' · '+c.count+' 篇 · '+fmt(c.last_attempt))));
 el('gap-status').replaceChildren(...data.gaps.map(g=>node('p','disclosure',sourceName(g.source_id)+' / '+g.channel+' · '+fmt(g.start)+' 至 '+(g.end?fmt(g.end):'尚未恢复')+' · '+g.reason+' · 完整性未核实')));
}
async function loadHistoryCoverage(){
  const hours=el('sector-window').value;
  const data=await request('/api/history-coverage?hours='+hours);
  if(el('sector-window').value!==hours)return;
  el('history-note').textContent='当前范围共 '+data.total+' 篇已收录新闻。'+data.note+' 部分索引仅开放最近 2–3 天，Espresso 与 Appy Geek 尚无可用历史接口。';
  el('history-sources').replaceChildren(...data.sources.map(s=>node('p','history-source',s.name+' · '+s.count+' 篇 · '+(s.oldest?fmt(s.oldest)+' 至 '+fmt(s.newest):'无可核实的发布时间范围')+(s.undated?' · '+s.undated+' 篇无发布时间':'')+' · 完整性未核实')));
}
async function load(){const data=await request('/api/sources');state.sources=data.sources;renderSources();await Promise.all([loadArticles(),loadContinuity(),loadSectorBoard(),loadHistoryCoverage()]);}
async function loadAnalysisStatus(){const data=await request('/api/analysis/status');el('ai-status').textContent=data.configured?(data.processing?'云端解读生成中':'自动解读已配置'):'自动解读待配置';el('ai-note').textContent=(data.configured?'旧版及完整解读 '+data.ready+' 篇，完整链条 '+data.chain_ready+' 篇、待补 '+data.pending_chain+' 篇。'+(data.last_duration_seconds?'最近一篇耗时 '+data.last_duration_seconds+' 秒。':''):'持续自动中文解读尚未启用；已有中文内容可查看。')+(data.quota_paused?'免费AI额度已用完或暂不可用，解读排队中。':'免费AI额度内排队，优先财经相关消息。')+'实际行情服务未接入。';}
el('refresh').onclick=async()=>{const b=el('refresh');b.disabled=true;try{await load();await loadAnalysisStatus();el('feedback').textContent='已读取云端最新记录；采集计划每30分钟执行，可能延迟。';}catch{showError();}finally{b.disabled=false;}};
let timer;el('search').oninput=e=>{state.query=e.target.value;state.offset=0;clearTimeout(timer);timer=setTimeout(()=>loadArticles().catch(showError),250);};
el('unread').onchange=e=>{state.unread=e.target.checked;renderArticles();};
el('sector-window').onchange=()=>{state.offset=0;loadSectorBoard();loadArticles().catch(showError);loadHistoryCoverage().catch(showError);};
request('/api/topics').then(data=>{state.topics=data.topics;renderTopics();}).catch(showError);
load().catch(showError);loadAnalysisStatus().catch(showError);setInterval(()=>{load().catch(showError);loadAnalysisStatus().catch(showError);},30000);
// Reload an already-open dashboard when its HTML, scripts or styles change.
const loadedUiVersion=document.querySelector('meta[name="ui-version"]')?.content;
if(loadedUiVersion)setInterval(async()=>{
  try{
    const response=await fetch('/api/ui-version',{cache:'no-store'});
    if(!response.ok)return;
    const data=await response.json();
    if(data.version!==loadedUiVersion){const next=new URL(location.href);next.searchParams.set('v',data.version);location.replace(next.href);}
  }catch{}
},30000);
