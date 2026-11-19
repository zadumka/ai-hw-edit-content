"""Rebuild data/uk-hw-vectors-*.npz from the full fastText model cc.uk.300.bin.gz.

Needed only to refresh the dictionary (for example with words of new courses). Runs on a machine
that has the model; reads it as a stream, about 3 GB of RAM and 2-3 minutes.

    python tools/build_vectors.py <cc.uk.300.bin.gz> <extra_tokens.json> <out.npz> [--top 100000]

extra_tokens.json: a JSON list of words (gensim preprocess_string tokens of cleaned review texts)
that must get exact vectors in addition to the --top most frequent model words.
"""
import argparse, gzip, json, struct
import numpy as np
from gensim.models.fasttext import ft_ngram_hashes

ap = argparse.ArgumentParser()
ap.add_argument('model'); ap.add_argument('extra'); ap.add_argument('out'); ap.add_argument('--top', type=int, default=100000)
a = ap.parse_args()
extra = set(json.load(open(a.extra)))
f = gzip.open(a.model, 'rb')
rd = lambda fmt: struct.unpack('<' + fmt, f.read(struct.calcsize('<' + fmt)))
magic, ver = rd('ii'); assert magic == 793712314
dim, ws, epoch, minCount, neg, wordNgrams, loss, model, bucket, minn, maxn, lrU = rd('12i'); rd('d')
size, nwords, nlabels = rd('iii'); ntokens, prune = rd('qq')
sel = {}; buf = b''; i = 0
while i < size:
    buf += f.read(1 << 22); pos = 0
    while i < size:
        z = buf.find(b'\0', pos)
        if z < 0 or z + 10 > len(buf): break
        w = buf[pos:z].decode('utf8', 'replace')
        if i < a.top or w in extra: sel[w] = i
        pos = z + 10; i += 1
    buf = buf[pos:]

class R:
    def __init__(s, b, f): s.b = b; s.f = f
    def read(s, n):
        if s.b:
            x = s.b[:n]; s.b = s.b[n:]
            return x + s.f.read(n - len(x)) if len(x) < n else x
        return s.f.read(n)

g = R(buf, f)
if prune > 0: g.read(prune * 8)
assert not struct.unpack('<?', g.read(1))[0]
m, n = struct.unpack('<qq', g.read(16)); assert n == dim and m == nwords + bucket
words = sorted(set(sel) | extra, key=lambda w: (sel.get(w, 10**9), w))
need = []
for w in words:
    rows = [nwords + h for h in ft_ngram_hashes(w, minn, maxn, bucket)]
    if w in sel: rows = [sel[w]] + rows
    need.append(rows)
needed = np.unique(np.fromiter((r for rows in need for r in rows), dtype=np.int64))
store = np.zeros((len(needed), dim), dtype='f2'); r0 = 0
while r0 < m:
    k = min(40000, m - r0)
    blk = np.frombuffer(g.read(k * dim * 4), dtype='<f4').reshape(k, dim)
    lo, hi = np.searchsorted(needed, [r0, r0 + k])
    if hi > lo: store[lo:hi] = blk[needed[lo:hi] - r0]
    r0 += k
vecs = np.zeros((len(words), dim), 'f4')
for j, rows in enumerate(need):
    if rows: vecs[j] = store[np.searchsorted(needed, rows)].astype('f4').mean(axis=0)

def q8(x):
    s = np.abs(x).max(axis=1) / 127.0; s[s == 0] = 1
    return np.round(x / s[:, None]).astype(np.int8), s.astype('f4')

wq, wsc = q8(vecs)
mask = needed >= nwords
bq, bsc = q8(store[mask].astype('f4'))
np.savez_compressed(a.out, words_int8=wq, words_scale=wsc, ngram_ids=(needed[mask] - nwords).astype(np.int32),
                    ngram_int8=bq, ngram_scale=bsc,
                    words_utf8=np.frombuffer('\n'.join(words).encode('utf8'), dtype=np.uint8))
print('words', len(words), 'ngram buckets', int(mask.sum()))
