"""Build only the public UI assets, without local data or credentials."""
import hashlib,json
from pathlib import Path


def build():
 root=Path(__file__).resolve().parents[1];source=root/'news_web'/'static'
 out=root/'public'/'static';out.mkdir(parents=True,exist_ok=True)
 for name in ('styles.css','topics.css'):(out/name).write_bytes((source/name).read_bytes())
 js=(source/'app.js').read_text(encoding='utf-8')
 js=js.replace('本机解读生成中','云端解读生成中').replace('本机服务','云端服务')
 js=js.replace('信源约每 5 分钟检查。','信源计划每 30 分钟检查，调度可能延迟。')
 js=js.replace('服务依赖电脑开机、登录和网络。','采集由云端定时任务执行，调度可能延迟；不依赖本机开机。')
 js=js.replace("'实际行情服务未接入。'","(data.quota_paused?'免费AI额度已用完或暂不可用，解读排队中。':'免费AI额度内排队，优先财经相关消息。')+'实际行情服务未接入。'")
 # Reload the latest stored snapshot; a page visit does not trigger publisher requests.
 start=js.index("el('refresh').onclick=")
 end=js.index('\nlet timer;',start)
 js=js[:start]+"el('refresh').onclick=async()=>{const b=el('refresh');b.disabled=true;try{await load();await loadAnalysisStatus();el('feedback').textContent='已读取云端最新记录；采集计划每30分钟执行，可能延迟。';}catch{showError();}finally{b.disabled=false;}};"+js[end:]
 (out/'app.js').write_text(js,encoding='utf-8')
 html=(source/'index.html').read_text(encoding='utf-8').replace('框架预览','免费云端版').replace('本机框架','免费云端服务')
 html=html.replace('运行期间 · 每 5 分钟检查','云端采集 · 计划每 30 分钟').replace('↻ 检查新文章','↻ 刷新云端记录')
 version=hashlib.sha256((html+js+(out/'topics.css').read_text(encoding='utf-8')+(out/'styles.css').read_text(encoding='utf-8')).encode()).hexdigest()[:12]
 for name in ('styles.css','topics.css','app.js'):html=html.replace('/static/'+name,'/static/'+name+'?v='+version)
 html=html.replace('</head>','<meta name="ui-version" content="'+version+'"></head>')
 (root/'public'/'index.html').write_text(html,encoding='utf-8')
 config=json.loads((root/'wrangler.jsonc').read_text(encoding='utf-8'))
 config['vars']['UI_VERSION']=version
 (root/'wrangler.jsonc').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Built cloud UI',version)
 return version


if __name__=='__main__':build()
