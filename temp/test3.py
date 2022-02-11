import typing as t


def chunk(seq: t.Sequence[t.Any], n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def chunk_b(seq: t.Sequence[t.Any], n: int):
    start = 0
    for end in range(len(seq) % n, len(seq) + 1, n):
        yield seq[start:end]
        start = end


a = tuple(range(50))
b = tuple(chunk(a, 6))
b_ = tuple(chunk_b(a, 6))

print('%s\n%s\n%s' % (a, b, b_))
