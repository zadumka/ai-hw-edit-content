"""Word vectors for Word Mover's Distance without the 4.5 GB fastText model.

`data/uk-hw-vectors-v1.npz` holds, from cc.uk.300.bin:
  * words_*  - final vectors (as gensim's load_facebook_vectors returns them) for the 100k most
               frequent model words + every word seen in the AI reviews used to build it;
  * ngram_*  - raw subword-bucket vectors for all character 5-grams of those words.
A word that is not in the dictionary gets the mean of its known n-gram buckets, which is the
fastText rule for out-of-vocabulary words. Vectors are int8 with a per-row scale.

Measured on 9-14.11.2026 (13 courses, 79 modules) against the full model, simulating a week whose
words were NOT in the dictionary: max difference of a module's mean similarity 0.035 points,
of a course's 0.01 points.
"""
import os

import numpy as np
from gensim.models import KeyedVectors
from gensim.models.fasttext import ft_ngram_hashes
from gensim.parsing.preprocessing import preprocess_string

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'uk-hw-vectors-v1.npz')
MINN, MAXN, BUCKET, DIM = 5, 5, 2_000_000, 300


class Dictionary:
    def __init__(self, path: str = DEFAULT_PATH):
        d = np.load(path)
        self.words = bytes(d['words_utf8']).decode('utf8').split('\n')
        self.index = {w: i for i, w in enumerate(self.words)}
        self._wq, self._ws = d['words_int8'], d['words_scale']
        self._bq, self._bs = d['ngram_int8'], d['ngram_scale']
        self.bucket_pos = {int(b): i for i, b in enumerate(d['ngram_ids'])}

    def vector(self, word: str):
        i = self.index.get(word)
        if i is not None:
            return self._wq[i].astype('f4') * self._ws[i]
        rows = [self.bucket_pos[h] for h in ft_ngram_hashes(word, MINN, MAXN, BUCKET) if h in self.bucket_pos]
        if not rows:
            return None
        return (self._bq[rows].astype('f4') * self._bs[rows][:, None]).mean(axis=0)

    def keyed_vectors(self, texts):
        """KeyedVectors covering every token of `texts` that can get a vector."""
        tokens = set()
        for t in texts:
            tokens.update(preprocess_string(t))
        words, vecs, missing = [], [], 0
        for w in tokens:
            v = self.vector(w)
            if v is None:
                missing += 1
            else:
                words.append(w)
                vecs.append(v)
        kv = KeyedVectors(DIM)
        kv.add_vectors(words, np.array(vecs, dtype='f4'))
        return kv, {'tokens': len(tokens), 'without_vector': missing}
