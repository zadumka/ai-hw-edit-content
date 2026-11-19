"""agg.json -> self-contained HTML dashboard (rules of the GoIT report-assistant agent).

Usage:
    python -m hwreport.dashboard <agg.json> <out.html> --start 2026-11-09 --end 2026-11-15 \
        [--end-inclusive] [--asof 19.11.2026] [--check "..."] [--comparison "..."]

--end is the value used in the SQL filter. Without --end-inclusive the filter was
`created_at <= '<end>'`, which keeps only 00:00 of that day, and the page says so.
"""
import argparse
import datetime as dt
import json
import os

HERE = os.path.dirname(__file__)
MONTHS = ['січня', 'лютого', 'березня', 'квітня', 'травня', 'червня', 'липня', 'серпня',
          'вересня', 'жовтня', 'листопада', 'грудня']


def human_period(start: dt.date, last: dt.date) -> str:
    if start.month == last.month:
        return f'{start.day}–{last.day} {MONTHS[last.month - 1]} {last.year}'
    return f'{start.day} {MONTHS[start.month - 1]} – {last.day} {MONTHS[last.month - 1]} {last.year}'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('agg')
    ap.add_argument('out')
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--end-inclusive', action='store_true', help='the SQL used created_at < end + 1 day')
    ap.add_argument('--asof', default=dt.date.today().strftime('%d.%m.%Y'))
    ap.add_argument('--check', default='Кількість рядків на курс збігається з count(*) у базі.')
    ap.add_argument('--comparison', default='Немає даних: попередній тиждень не розраховано.')
    a = ap.parse_args(argv)

    D = json.load(open(a.agg))
    start = dt.date.fromisoformat(a.start)
    end = dt.date.fromisoformat(a.end)
    if a.end_inclusive:
        last, upto = end, end + dt.timedelta(days=1)
        sql = (f'<code>created_at</code> від {start:%d.%m.%Y} 00:00 до {upto:%d.%m.%Y} 00:00, '
               f'день {end:%d.%m} повністю.')
    else:
        last, upto = end - dt.timedelta(days=1), end
        sql = (f'<code>created_at</code> від {start:%d.%m.%Y} 00:00 до {end:%d.%m.%Y} 00:00. '
               f'День {end:%d.%m} у вибірку не входить.')
    T = D['total']
    page = open(os.path.join(HERE, 'dashboard_template.html')).read()
    for k, v in {
        '__PERIOD_HUMAN__': human_period(start, last),
        '__PERIOD_SHORT__': f'{start:%d.%m} 00:00 – {upto:%d.%m} 00:00',
        '__PERIOD_SQL__': sql,
        '__ASOF__': a.asof,
        '__N_COURSES__': str(len(D['courses'])),
        '__SELF__': str(T['self_changed']),
        '__CHANGED__': str(T['changed']),
        '__COMPARISON__': a.comparison,
        '__CHECK__': a.check,
        '__VECTORS__': 'uk-hw-vectors-v1 (cc.uk.300), похибка середньої схожості модуля до 0,04 пункту',
    }.items():
        page = page.replace(k, v)
    page = page.replace('__DATA__', json.dumps(D, ensure_ascii=False))
    import re
    left = re.findall(r'__[A-Z_]+__', page)
    assert not left, f'unfilled placeholders: {left}'
    open(a.out, 'w').write(page)
    print('written', a.out)


if __name__ == '__main__':
    main()
