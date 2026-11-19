"""Weekly aggregates -> one self-contained HTML dashboard with a period switcher.

The page keeps every week it shows in a JSON block (<script id="hw-data">), so a weekly update
reads the published page, adds the new week and writes the page again:

    python -m hwreport.dashboard out.html \
        --week out/2026-11-09/agg.json --start 2026-11-09 --end 2026-11-15 --asof 19.11.2026 \
        --check "Кількість рядків збігається з базою для всіх 13 курсів (9 601)." \
        [--merge existing_index.html] [--keep 26] [--end-inclusive]

--end is the date used in the SQL filter. Without --end-inclusive the filter was
`created_at <= '<end>'`, which keeps only 00:00 of that day, and the page says so.
A week whose start date is already in the page is replaced. Only aggregates are embedded:
no e-mails of students or mentors (the page is published to the company wiki).
"""
import argparse
import datetime as dt
import json
import os
import re

HERE = os.path.dirname(__file__)
MONTHS = ['січня', 'лютого', 'березня', 'квітня', 'травня', 'червня', 'липня', 'серпня',
          'вересня', 'жовтня', 'листопада', 'грудня']
VECTORS = 'uk-hw-vectors-v1 (cc.uk.300), похибка середньої схожості модуля до 0,04 пункту'
DATA_RE = re.compile(r'<script type="application/json" id="hw-data">(.*?)</script>', re.S)


def human_period(start, last):
    if start.month == last.month:
        return f'{start.day}–{last.day} {MONTHS[last.month - 1]} {last.year}'
    return f'{start.day} {MONTHS[start.month - 1]} – {last.day} {MONTHS[last.month - 1]} {last.year}'


def week_entry(agg, start, end, end_inclusive, asof, check):
    if end_inclusive:
        last, upto = end, end + dt.timedelta(days=1)
        sql = (f'<code>created_at</code> від {start:%d.%m.%Y} 00:00 до {upto:%d.%m.%Y} 00:00, '
               f'день {end:%d.%m} повністю.')
    else:
        last, upto = end - dt.timedelta(days=1), end
        sql = (f'<code>created_at</code> від {start:%d.%m.%Y} 00:00 до {end:%d.%m.%Y} 00:00. '
               f'День {end:%d.%m} у вибірку не входить.')
    for scope in [agg['all'], *agg['by'].values()]:
        for r in scope['top']:
            assert 'student' not in r and 'editor' not in r, 'e-mails must not reach the page'
    return dict(start=start.isoformat(), label=f'{start:%d.%m} – {last:%d.%m.%Y}',
                period_human=human_period(start, last), period_short=f'{start:%d.%m} 00:00 – {upto:%d.%m} 00:00',
                period_sql=sql, asof=asof, check=check, data=agg)


def compact(entry, names):
    """Shrink one week for the page: names of modules go to a shared list, rows become arrays."""
    D = entry['data']
    cidx = {c['course']: i for i, c in enumerate(D['courses'])}
    def mid(name):
        if name not in names: names.append(name)
        return names.index(name)
    stats = lambda x: [x['n'], x['changed'], x['edit'], x['depth'], x['self_changed']]
    reviews = {}
    for c in D['courses']:
        for r in D['by'][c['course']]['top']:
            reviews[(r['homework_id'], r['order'], r['version'], c['course'])] = [
                cidx[c['course']], mid(r['module']), r['homework_id'], r['order'], r['version'],
                r['sim'], r['len_o'], r['len_e'], int(r['self'])]
    out = {k: v for k, v in entry.items() if k != 'data'}
    out.update(
        c=[[c['course'], c['full'], c['grp'], c['target'], *stats(c)] for c in D['courses']],
        t=stats(D['total']),
        m=[[cidx[m['course']], mid(m['module']), *stats(m)] for m in D['modules']],
        days=[d['iso'] for d in D['days']],
        dA=[[d['n'], d['changed']] for d in D['all']['daily']],
        dC=[[[d['n'], d['changed']] for d in D['by'][c['course']]['daily']] for c in D['courses']],
        r=sorted(reviews.values(), key=lambda x: x[5]))
    return out


def read_weeks(html_path):
    m = DATA_RE.search(open(html_path, encoding='utf-8').read())
    if not m:
        raise SystemExit(f'No <script id="hw-data"> block in {html_path}')
    raw = json.loads(m.group(1))
    return raw['weeks'], raw['names']


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--week', required=True, help='agg.json of the week to add')
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--end-inclusive', action='store_true')
    ap.add_argument('--asof', default=dt.date.today().strftime('%d.%m.%Y'))
    ap.add_argument('--check', default='Кількість рядків на курс збігається з count(*) у базі.')
    ap.add_argument('--merge', help='published index.html whose weeks to keep')
    ap.add_argument('--keep', type=int, default=8, help='how many latest weeks to keep')
    a = ap.parse_args(argv)

    weeks, names = read_weeks(a.merge) if a.merge else ([], [])
    new = compact(week_entry(json.load(open(a.week)), dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end),
                             a.end_inclusive, a.asof, a.check), names)
    weeks = sorted([w for w in weeks if w['start'] != new['start']] + [new], key=lambda w: w['start'])[-a.keep:]
    payload = dict(updated=a.asof, names=names, weeks=weeks)
    # indent=0 keeps every value on its own short line: the wiki takes a page in chunks of ~20 KB
    data = json.dumps(payload, ensure_ascii=False, indent=0).replace('</', '<\\/')
    page = open(os.path.join(HERE, 'dashboard_template.html'), encoding='utf-8').read()
    page = page.replace('__VECTORS__', VECTORS).replace('__DATA__', data)
    left = re.findall(r'__[A-Z_]+__', page)
    assert not left, f'unfilled placeholders: {left}'
    assert '@' not in data, 'an e-mail address reached the page data'
    open(a.out, 'w', encoding='utf-8').write(page)
    print('written', a.out, '| weeks:', ', '.join(w['label'] for w in weeks), '| size', len(page.encode()), 'bytes')


if __name__ == '__main__':
    main()
