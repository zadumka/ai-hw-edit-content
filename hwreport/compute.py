"""CSV of saved AI reviews -> similarity per review -> aggregates for the dashboard.

Usage:
    python -m hwreport.compute <reviews.csv> <out_dir> [--model cc.uk.300.bin.gz]

The CSV has the columns of the export query in the LMS scenario `ai-hw-mentor-edits-report`:
homework_id, order, version, original, edited, created_at, edited_at, edited_by, passed,
has_mentor_changes_block, module_id, module_name, course_name, student_username.

Writes <out_dir>/reviews.csv (one row per review with similarity) and <out_dir>/agg.json.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from gensim.parsing.preprocessing import preprocess_string
from sklearn.feature_extraction.text import TfidfVectorizer

from .text import to_plain_text
from .vectors import Dictionary

HERE = os.path.dirname(__file__)


def similarity_for_course(g, kv):
    """Notebook formula. TF-IDF is fitted per course, as in the weekly notebook reports."""
    m = TfidfVectorizer().fit_transform(pd.concat([g.o, g.e], axis=0))
    n = m.shape[0] // 2
    cos = np.asarray(m[:n].multiply(m[n:]).sum(axis=1)).ravel()
    wmd = np.array([0.0 if o == e else kv.wmdistance(preprocess_string(o), preprocess_string(e))
                    for o, e in zip(g.o, g.e)])
    return cos, wmd, (50 * (cos + 1) + np.clip(100 * (1 - wmd / 3), 0, 100)) / 2


def aggregate(r, courses):
    meta = {c['name']: c for c in courses}

    def agg(g):
        c = g[g.changed]
        return dict(n=int(len(g)), changed=int(g.changed.sum()),
                    edit=round(100 - float(g.similarity.mean()), 2),
                    depth=(round(100 - float(c.similarity.mean()), 2) if len(c) else None),
                    self_changed=int((g.changed & g.self_edit).sum()))

    days = sorted(r.day.unique())

    def detail(g):
        top = g[g.changed].sort_values('similarity').head(20)
        return dict(
            daily=[dict(day=pd.Timestamp(d).strftime('%d.%m'), n=int((g.day == d).sum()),
                        changed=int((g.changed & (g.day == d)).sum())) for d in days],
            top=[dict(course=x.short, module=x.module_name, student=x.student_username, editor=x.edited_by,
                      homework_id=int(x.homework_id), order=int(x.order), version=int(x.version),
                      sim=round(float(x.similarity), 2), len_o=len(x.o), len_e=len(x.e))
                 for _, x in top.iterrows()])

    D = dict(courses=[], modules=[], total=agg(r), all=detail(r), by={},
             days=[dict(label=pd.Timestamp(d).strftime('%d.%m'), iso=str(d)) for d in days])
    for name, g in r.groupby('course_name', sort=False):
        c = meta[name]
        D['courses'].append(dict(course=c['short'], full=name, grp=c['group'], target=c['target'], **agg(g)))
        D['by'][c['short']] = detail(g)
    for (name, mid, mname), g in r.groupby(['course_name', 'module_id', 'module_name'], sort=False):
        c = meta[name]
        D['modules'].append(dict(course=c['short'], target=c['target'], module=mname, **agg(g)))
    return D


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('csv')
    ap.add_argument('out_dir')
    ap.add_argument('--vectors', default=None, help='path to uk-hw-vectors-*.npz (default: data/ in this repo)')
    a = ap.parse_args(argv)
    courses = json.load(open(os.path.join(HERE, 'courses.json')))['courses']
    known = {c['name'] for c in courses}

    df = pd.read_csv(a.csv)
    unknown = sorted(set(df.course_name) - known)
    if unknown:
        sys.exit(f'Courses missing from hwreport/courses.json (add short name, group, target): {unknown}')
    df = df.drop_duplicates(['course_name', 'homework_id', 'order', 'version'])
    cache = {}
    clean = lambda t: cache.setdefault(t, to_plain_text(t))
    df['o'] = df.original.map(clean)
    df['e'] = df.edited.map(clean)

    vocab = Dictionary(a.vectors) if a.vectors else Dictionary()
    kv, cov = vocab.keyed_vectors(list(df.o) + list(df.e))
    print(f"tokens: {cov['tokens']}, without vector: {cov['without_vector']}")

    parts = []
    for _, g in df.groupby('course_name', sort=False):
        g = g.copy()
        g['cos'], g['wmd'], g['similarity'] = similarity_for_course(g, kv)
        parts.append(g)
    r = pd.concat(parts)
    short = {c['name']: c['short'] for c in courses}
    r['short'] = r.course_name.map(short)
    r['changed'] = r.o != r.e
    r['self_edit'] = r.edited_by == r.student_username
    r['day'] = pd.to_datetime(r.created_at, utc=True).dt.strftime('%Y-%m-%d')

    os.makedirs(a.out_dir, exist_ok=True)
    r.drop(columns=['o', 'e']).to_csv(os.path.join(a.out_dir, 'reviews.csv'), index=False)
    D = aggregate(r, courses)
    json.dump(D, open(os.path.join(a.out_dir, 'agg.json'), 'w'), ensure_ascii=False)
    print('rows per course:')
    for c in D['courses']:
        print(f"  {c['full']}: {c['n']} saved, {c['changed']} changed, edit {c['edit']} % (target {c['target']} %)")


if __name__ == '__main__':
    main()
