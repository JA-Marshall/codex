from concurrent.futures import ThreadPoolExecutor
from worker import check

def verify(root, entries):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return [item for item in pool.map(lambda entry: check(root, entry), entries) if item["status"] != "error"]
