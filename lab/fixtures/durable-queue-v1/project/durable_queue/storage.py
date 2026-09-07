import sqlite3


def connect(path):
    connection = sqlite3.connect(path, timeout=5)
    connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    return connection
