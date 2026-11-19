"""Conservative excerpt-based exposure mapping, never observed price reactions."""
import re
from datetime import datetime, timezone, timedelta

SECTORS = ['油气开采','航空运输','半导体','软件与互联网','消费电子','汽车与新能源车','可选消费','必选消费','银行','非银金融','房地产','金属与矿业','医药生物','公用事业','工业制造','科技成长']
COMPANIES = [
    (r'\bnvidia\b|英伟达','英伟达（Nvidia）','半导体'),
    (r'\btsmc\b|taiwan semiconductor|台积电','台积电（TSMC）','半导体'),
    (r'\bamd\b|超微半导体','超微半导体（AMD）','半导体'),
    (r'\bmicrosoft\b|微软','微软（Microsoft）','软件与互联网'),
    (r'\bgoogle\b|\balphabet\b|谷歌','Alphabet（谷歌）','软件与互联网'),
    (r'\bamazon\b|亚马逊','亚马逊（Amazon）','可选消费'),
    (r'\bapple\b|苹果公司','苹果（Apple）','消费电子'),
    (r'\btesla\b|特斯拉','特斯拉（Tesla）','汽车与新能源车'),
    (r'\bnetflix\b|奈飞','奈飞（Netflix）','软件与互联网'),
    (r'\btencent\b|腾讯','腾讯','软件与互联网'),
    (r'\balibaba\b|阿里巴巴','阿里巴巴','可选消费'),
    (r'\binvestec\b','Investec','银行'),
]
SECTOR_PATTERNS = [
    (r'\bchip\w*\b|semiconductor|芯片|半导体','半导体'),
    (r'\bai\b|artificial intelligence|software|cloud computing|人工智能|软件|云计算','软件与互联网'),
    (r'airline|aviation|航空','航空运输'),
    (r'\bbank\w*\b|银行','银行'),
    (r'real estate|property developer|房地产','房地产'),
    (r'retail|consumer spending|retailer|零售|消费支出','可选消费'),
    (r'smartphone|consumer electronics|消费电子|智能手机','消费电子'),
    (r'automaker|electric vehicle|\bev\b|汽车|新能源车','汽车与新能源车'),
    (r'copper|iron ore|mining|miner\b|\bbhp\b|铜价|铁矿|矿业','金属与矿业'),
    (r'pharma|biotech|drug trial|clinical trial|医药|生物医药|临床试验','医药生物'),
    (r'utility|utilities|power grid|公用事业|电网','公用事业'),
    (r'manufactur|industrial equipment|工业设备|制造业','工业制造'),
    (r'grocery|staples|food producer|日用消费|食品饮料','必选消费'),
    (r'insurer|insurance company|brokerage|fintech|保险公司|券商|金融科技','非银金融'),
]

METRICS={
    '油气开采':'核实实现油价、产销量、单位开采成本及套保敞口',
    '航空运输':'核实航油采购及套保、客座率、票价与单位成本',
    '半导体':'核实订单、出货量与均价、产能利用率及毛利率',
    '软件与互联网':'核实付费客户、留存、云服务收入、算力成本及自由现金流',
    '汽车与新能源车':'核实交付量、单车售价、单车毛利及库存',
    '消费电子':'核实终端出货、产品均价、渠道库存及毛利率',
    '银行':'核实净息差、存款成本、不良率及拨备',
    '房地产':'核实销售回款、融资成本、债务到期与经营现金流',
    '金属与矿业':'核实金属实现售价、产销量、单位成本及资本开支',
    '医药生物':'核实正式试验终点、审批进度、商业化收入及研发现金消耗',
}


def assess_exposures(row):
    # Use source excerpts only. Translations and model opinions cannot create evidence.
    title=row['title'].strip()
    text=title+' '+row.get('summary','')
    companies=[(name,sector) for pattern,name,sector in COMPANIES if re.search(pattern,text,re.I)]
    sectors=list(dict.fromkeys([s for _,s in companies]+[s for p,s in SECTOR_PATTERNS if re.search(p,text,re.I)]))
    outputs=[]
    def add(sector,direction,reason,evidence,subject=None):
        named=companies if subject is None else [(name,s) for pattern,name,s in COMPANIES if re.search(pattern,subject,re.I)]
        targets=[name for name,s in named if s==sector] or [sector+'板块（行业整体，未指定个股）']
        outputs.append(dict(sector=sector,direction=direction,reason=reason,evidence=evidence[:500],
            basis='公开标题／摘要的机制规则 · 低置信度条件推断',
            verification=dict(status='待行情验证',targets=targets,
                benchmark='相关标的所在市场的宽基指数与同行业指数',
                checks=['以首次收录时间为观察起点；发布时间仅供参考，盘外消息从下一交易时段观察',
                    '比较后续 1 个交易日、3 个交易日的收益及相对行业／宽基超额收益、成交量变化',
                    METRICS.get(sector,'核实相关业务收入、利润率、订单及自由现金流与市场预期的差异'),
                    '结合公司公告及财务指标复核，排查同期财报、政策等共同事件'],
                market_data='未接入行情，尚未计算收益或验证归因')))
    # Headlines frame the event. Avoid extracting a direction from a contrary or hypothetical clause.
    rates=re.search(r'(?:rate[- ](?:rise|hike)|interest rates? (?:rise|hike)|加息|利率上升)',title,re.I)
    cuts=re.search(r'(?:rate[- ]cut|interest rates? (?:fall|cut)|降息|利率下行)',title,re.I)
    if rates or cuts:
        sectors=list(dict.fromkeys(sectors+['科技成长','房地产']))
    ambiguous=bool(re.search(r'\?|mixed|weigh|outlook|prospects|\b(?:may|might|could|would|should|consider\w*|if|not|no|forecast|expects?|predict\w*|set to|bets|fears|hopes|fail\w*|before|revers\w*|urge\w*)\b|rules? out|rule[ds] out|open to|price[ds]? (?:in )?rate|可能|或将|预计|有望|若|未|否|震荡|排除|考虑|呼吁|先涨后跌|先跌后涨',title,re.I))
    if not ambiguous:
        oil=re.search(r'(?:oil|crude) prices?\s+(?:\w+\s+){0,2}(rise\w*|surge\w*|climb\w*|jump\w*|rall\w*|fall\w*|drop\w*|slid\w*|slump\w*)|油价(上涨|上升|攀升|下跌|回落)',title,re.I)
        if oil:
            verb=next(g for g in oil.groups() if g)
            up=bool(re.match(r'rise|surg|climb|jump|rall|上涨|上升|攀升',verb,re.I))
            add('油气开采','利好' if up else '利空','若实现售价随油价变化且销量、成本稳定，可能通过收入及利润预期传导；套保和已定价因素可能抵消。',title)
            add('航空运输','利空' if up else '利好','若燃油采购成本同向变化，可能影响毛利及现金流；需核实燃油套保、票价和需求，不能直接断定股价。',title)
        if bool(rates)!=bool(cuts):
            add('科技成长','利空' if rates else '利好','若利率路径比市场定价更紧／松，折现率可能压低／抬高远期现金流现值；盈利与风险溢价变化可能抵消。',title)
            add('房地产','利空' if rates else '利好','若融资利率和按揭成本实际传导，可能改变融资现金流及购房需求；需区分国家、债务期限与信用风险。',title)
        subject=r'\b(?:earnings|profits?|revenue|sales|orders)\s+(?:(?:has|have|had|is|are|was|were|unexpectedly|sharply|slightly)\s+){0,3}'
        positive=re.search(subject+r'\b(?:beat\w*|rise|rises|rising|rose|climb\w*|grow|grows|growing|grew|surge\w*|jump\w*|increas\w*)\b|业绩超预期|(?:利润|营收|销量|订单)(?:增长|上升|增加)',title,re.I)
        negative=re.search(subject+r'\b(?:miss\w*|fall\w*|fell|drop\w*|declin\w*|slump\w*|decreas\w*)\b|业绩不及预期|(?:利润|营收|销量|订单)(?:下降|下滑|减少)',title,re.I)
        if bool(positive)!=bool(negative):
            match=positive or negative
            # Bind the event to its leading subject; later clauses and excerpt peers stay uncertain.
            leading=title[:match.start()]
            subject_sectors=list(dict.fromkeys([s for p,_,s in COMPANIES if re.search(p,leading,re.I)]+[s for p,s in SECTOR_PATTERNS if re.search(p,leading,re.I)]))
            for sector in subject_sectors:
                add(sector,'利好' if positive else '利空','若报道中的业绩变化具有持续性，可能改变相关主体的盈利与估值预期；需核实利润率、现金流及一致预期。单一公司不代表全板块。',title,subject=leading)
    for sector in sectors:
        if not any(r['sector']==sector for r in outputs):
            add(sector,'不确定','已识别行业或报道点名主体，尚缺明确的方向性事件；保留验证对象，等待经营数据和预期差。',title)
    if not outputs and re.search(r'\boil\b|\bcrude\b|油价|原油',title,re.I):
        add('油气开采','不确定','涉及原油供需，但方向未明确或仅为情景预测，暂不计入利好／利空。',title)
    return outputs


def sector_board(rows,hours=24,now=None):
    current=now or datetime.now(timezone.utc)
    cutoff=current-timedelta(hours=hours)
    groups={s:dict(sector=s,positive=[],negative=[],uncertain=[],positive_count=0,negative_count=0,uncertain_count=0) for s in SECTORS}
    total=undated=unclassified=0
    seen=set()
    for row in rows:
        stamp=row.get('published_at') or row['first_seen']
        if not cutoff<=datetime.fromisoformat(stamp)<=current:
            continue
        total+=1
        undated+=int(not row.get('published_at'))
        signals=row.get('sector_impacts',[])
        if not signals:unclassified+=1
        for signal in signals:
            bucket={'利好':'positive','利空':'negative'}.get(signal['direction'],'uncertain')
            # Identical titles across feeds count once; related stories are not assumed identical.
            key=(re.sub(r'\W+','',row['title'].casefold()),signal['sector'],bucket)
            if key in seen:continue
            seen.add(key)
            group=groups[signal['sector']]
            group[bucket+'_count']+=1
            if len(group[bucket])<8:
                group[bucket].append(dict(article_id=row['id'],title=row.get('title_zh') or row['title'],
                    summary_zh=row.get('summary_zh'),source_id=row['source_id'],url=row['url'],
                    published_at=row.get('published_at'),first_seen=row['first_seen'],
                    translation_pending=not bool(row.get('title_zh')),**signal))
    return dict(as_of=current.isoformat(),window_hours=hours,total_articles=total,undated_articles=undated,
        unclassified_articles=unclassified,sectors=list(groups.values()),market_data='not_connected',
        methodology='方向按公开标题中的明确事件与行业敞口规则归类；不确定与预测不计入利好利空。相同标题跨来源去重，每栏显示最近8条。')
