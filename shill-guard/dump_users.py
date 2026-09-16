# -*- coding: utf-8 -*-
"""
读取 shill_guard.sys_user 表的所有用户账号信息，写到 accounts_all.txt。
这是本机自用开发脚本，仅连本地虚拟机上的开发数据库。
"""
import sys
import subprocess

# 1. 确保 pymysql 可用，缺了就装
try:
    import pymysql
except ImportError:
    print("pymysql 未安装，正在安装...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymysql", "-q"])
    import pymysql

# 2. 数据库连接信息（与 application.yml 对齐）
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_USER = "root"
DB_PASS = "shillguard123"
DB_NAME = "shill_guard"

# 3. 连接并查询
conn = pymysql.connect(
    host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
    database=DB_NAME, charset="utf8mb4"
)
sql = """
    SELECT user_id, username, password, nickname, role, status,
           created_time, last_login_time
    FROM sys_user
    ORDER BY user_id
"""
with conn.cursor() as cur:
    cur.execute(sql)
    rows = cur.fetchall()
conn.close()

# 4. 写到 txt 文件
out_path = r"D:\Projects\shill-guard\accounts_all.txt"
role_map = {0: "普通用户", 1: "审核员", 2: "管理员", 3: "超级管理员"}
status_map = {0: "正常", 1: "禁言", 2: "封号"}

lines = []
lines.append("=" * 70)
lines.append("ShillGuard 平台 - sys_user 表全部用户清单")
lines.append("数据库: shill_guard @ 192.168.150.101:3306")
lines.append(f"用户总数: {len(rows)}")
lines.append("说明: password 字段为 BCrypt 加密后的哈希，无法逆向还原明文。")
lines.append("=" * 70)
lines.append("")

if not rows:
    lines.append("(表为空，没有任何用户)")
else:
    header = f"{'user_id':<8}{'username':<20}{'role':<14}{'status':<8}{'nickname':<16}{'created_time':<22}{'last_login_time':<22}"
    lines.append(header)
    lines.append("-" * 110)
    for r in rows:
        uid, uname, pwd, nick, role, status, created, last_login = r
        role_txt = role_map.get(role, str(role))
        status_txt = status_map.get(status, str(status))
        nick = nick or ""
        created_s = str(created) if created else ""
        last_login_s = str(last_login) if last_login else "NULL"
        lines.append(f"{uid:<8}{uname:<20}{role_txt:<14}{status_txt:<8}{nick:<16}{created_s:<22}{last_login_s:<22}")
    lines.append("")
    lines.append("=" * 70)
    lines.append("密码哈希明细（BCrypt，不可逆）:")
    lines.append("=" * 70)
    for r in rows:
        uid, uname, pwd, nick, role, status, created, last_login = r
        lines.append(f"user_id={uid}  username={uname}  password={pwd}")

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"完成：共 {len(rows)} 个用户，已写入 {out_path}")
for r in rows:
    uid, uname, pwd, nick, role, status, created, last_login = r
    print(f"  user_id={uid}  username={uname}  role={role_map.get(role,role)}  status={status_map.get(status,status)}  nickname={nick}")
