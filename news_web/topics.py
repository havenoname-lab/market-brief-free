"""Transparent, free topic rules for public titles and summaries (not full-text AI)."""
import re

RULES = {
    '宏观': ('宏观', '通胀', '利率', '央行', '美联储', '经济增长', '就业', '关税', 'inflation', 'interest rate', 'rate cut', 'rate hike', 'central bank', 'fed', 'gdp', 'economy', 'economic', 'tariff', 'unemployment'),
    '科技': ('科技', '人工智能', '半导体', '芯片', '云计算', '数据中心', 'ai', 'artificial intelligence', 'semiconductor', 'chip', 'chips', 'technology', 'tech', 'software', 'cloud computing', 'data centre', 'data center', 'nvidia', 'openai'),
    '消费': ('消费', '零售', '电商', '食品', '餐饮', '旅游', '奢侈品', 'retail', 'consumer', 'shoppers', 'shopping', 'supermarket', 'food', 'restaurant', 'tourism', 'luxury', 'e-commerce'),
    '金融': ('金融', '银行', '保险', '券商', '信贷', '加密货币', 'bank', 'banks', 'banking', 'insurance', 'lending', 'credit', 'bitcoin', 'cryptocurrency', 'wall street'),
    '能源': ('能源', '石油', '天然气', '电力', '光伏', '煤炭', 'oil', 'gas', 'energy', 'solar', 'renewable', 'electricity', 'coal', 'opec'),
    '医疗': ('医疗', '医药', '新药', '疫苗', '生物科技', 'healthcare', 'pharma', 'drug', 'drugs', 'vaccine', 'biotech', 'fda'),
    '工业': ('工业', '制造', '汽车', '航空', '航运', '供应链', 'manufacturing', 'factory', 'factories', 'automotive', 'car', 'cars', 'airline', 'aircraft', 'shipping', 'supply chain', 'boeing'),
    '国际局势': ('地缘', '战争', '冲突', '制裁', '外交', 'war', 'conflict', 'sanctions', 'geopolitical', 'diplomacy', 'ceasefire'),
}
TOPICS = [*RULES, '其他']
PATTERNS = {topic: [re.compile(r'(?<!\w)' + re.escape(term) + r'(?!\w)', re.I)
                    if term.isascii() else re.compile(re.escape(term)) for term in terms]
            for topic, terms in RULES.items()}


def classify(title, summary):
    text = f'{title} {summary}'
    return [topic for topic, patterns in PATTERNS.items() if any(p.search(text) for p in patterns)] or ['其他']
