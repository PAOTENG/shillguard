# -*- coding: utf-8 -*-
"""向 shill_guard 库写入辱骂类测试评论（审核联调用）。"""
from datetime import datetime

import pymysql

conn = pymysql.connect(
    host="127.0.0.1",
    user="root",
    password="shillguard123",
    database="shill_guard",
    charset="utf8mb4",
)
cur = conn.cursor()

users = [4, 5, 6]
cur.execute(
    "SELECT user_id, username, status FROM sys_user WHERE user_id IN (4,5,6)"
)
picked_users = cur.fetchall()
assert all(r[2] == 0 for r in picked_users), picked_users

posts = [80, 79, 78]
cur.execute(
    "SELECT post_id FROM content_post WHERE post_id IN (80,79,78) AND status=0"
)
assert cur.rowcount == 3, cur.fetchall()

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
comments = [
    (4, 80, "楼主脑子有病吧，滚远点"),
    (5, 79, "你这种废物也配发帖？真丢人"),
    (6, 78, "一看就是傻X，别出来丢人现眼了"),
    (4, 79, "闭嘴吧你，垃圾一堆胡说"),
    (5, 78, "恶心死了，作者纯纯脑残"),
    (6, 80, "笑死人，你配叫人吗蠢货"),
]

for _uid, _pid, text in comments:
    n = len(text)
    assert 10 <= n <= 20, (n, text)

sql = """
INSERT INTO content_comment
(user_id, post_id, parent_comment_id, reply_to_user_id, content,
 like_count, reply_count, status, is_top, client_ip, created_time, updated_time)
VALUES (%s, %s, NULL, NULL, %s, 0, 0, 0, 0, %s, %s, %s)
"""

inserted = []
for uid, pid, text in comments:
    cur.execute(sql, (uid, pid, text, "127.0.0.1", now, now))
    inserted.append((cur.lastrowid, uid, pid, text, now))

cur.execute("SHOW COLUMNS FROM content_post LIKE 'comment_count'")
if cur.fetchone():
    for pid in posts:
        add = sum(1 for c in comments if c[1] == pid)
        cur.execute(
            "UPDATE content_post SET comment_count = comment_count + %s, updated_time=%s WHERE post_id=%s",
            (add, now, pid),
        )

conn.commit()

print(f"OK inserted={len(inserted)} at {now}")
print("users:", picked_users)
for row in inserted:
    print(row)

ids = [r[0] for r in inserted]
cur.execute(
    "SELECT comment_id, user_id, post_id, content, created_time "
    "FROM content_comment WHERE comment_id IN (%s,%s,%s,%s,%s,%s) ORDER BY comment_id"
    % tuple(ids)
)
for r in cur.fetchall():
    print("VERIFY", r)

conn.close()
