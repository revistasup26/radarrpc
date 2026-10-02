import sqlite3
conn = sqlite3.connect('../data/radar.db')
print('tiktok:', conn.execute('SELECT count(1) FROM articles WHERE title LIKE "%tiktok%" OR abstract LIKE "%tiktok%"').fetchone()[0])
print('tik tok:', conn.execute('SELECT count(1) FROM articles WHERE title LIKE "%tik tok%" OR abstract LIKE "%tik tok%"').fetchone()[0])
