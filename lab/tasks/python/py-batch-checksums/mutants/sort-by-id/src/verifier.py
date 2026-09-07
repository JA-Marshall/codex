from concurrent.futures import ThreadPoolExecutor
from worker import check

def verify(root, entries):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return sorted(pool.map(lambda entry: check(root, entry), entries), key=lambda item: item["id"])
