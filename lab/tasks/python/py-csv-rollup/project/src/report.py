import csv

def rows(filename):
    with open(filename, encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))
