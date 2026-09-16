# -*- coding: utf-8 -*-
"""
从 golden_set.json 生成 seed_golden.sql：
  - 15 个普通测试用户（role=0，password=123456 BCrypt）
  - 110 条测试内容，全部 created_time = TODAY
  - 分配策略（测试三种禁言场景）：
      用户 01-05 : 只有正常内容              -> 预期 mute: none
      用户 06-10 : 恰好 1 条违规内容          -> 预期 mute: mute_3days
      用户 11-15 : 3-4 条违规内容 + 若干正常   -> 预期 mute: mute_7days
"""
import json

GOLDEN_SET_PATH = r"d:\Projects\shill-guard-ai\loadtest\golden_set.json"
OUTPUT_SQL      = r"d:\Projects\shill-guard\seed_golden.sql"

# ── BCrypt hash for "123456" (cost=10) ──
# 用 bcrypt 库现场计算，避免使用未经验证的哈希
try:
    import bcrypt
    pwd = bcrypt.hashpw(b"123456", bcrypt.gensalt(rounds=10)).decode()
    print(f"[bcrypt] 动态生成: {pwd}")
except ImportError:
    # fallback: 固定预计算值（已在 Spring BCryptPasswordEncoder 下验证）
    pwd = "$2a$10$EblZqNptyYvcLm/VwDptluAkl/Z1XkJ9gBcEmLaEcYKGMNyaGwKXy"
    print(f"[bcrypt] 使用预设值: {pwd}")

BCRYPT_123456 = pwd

NICKNAMES = [
    "晨光微语", "落叶行者", "星河漫步", "烟雨江南", "月影清风",
    "暖阳小鹿", "流年轻唱", "碧海潮生", "寒梅傲雪", "紫竹听雨",
    "浅夏微凉", "云端漫步", "秋水长天", "青松问道", "薄荷凉风",
]

def escape(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")

with open(GOLDEN_SET_PATH, encoding="utf-8") as f:
    data = json.load(f)

# 按 expected_action 分类
violations  = [d for d in data if d.get("expected_action") in ("auto_mute", "manual_review")]
normals     = [d for d in data if d.get("expected_action") == "none"]
others      = [d for d in data if d.get("expected_action") not in ("auto_mute", "manual_review", "none")]
print(f"总用例: {len(data)}，违规: {len(violations)}，正常: {len(normals)}，其他: {len(others)}")

# ── 分配策略 ──
user_contents = {i: [] for i in range(15)}  # index -> list of (content, is_vio)

# 把 46 条违规分配给用户 5-14
# 用户 5-9 各 1 条（5*1=5条），用户 10-14 每人 3 条（5*3=15条），剩余 26 条
# 实际分配：用户 6-10 各 1 条，用户 11-15 平分剩余
for i, vio in enumerate(violations[:5]):
    user_contents[5 + i].append((vio["content"], True))

remaining_vios = violations[5:]  # 41 条
per_user = len(remaining_vios) // 5  # 8 条
for i in range(5):
    for v in remaining_vios[i * per_user: (i + 1) * per_user]:
        user_contents[10 + i].append((v["content"], True))
# 尾巴分给前几个高危用户
for i, v in enumerate(remaining_vios[5 * per_user:]):
    user_contents[10 + (i % 5)].append((v["content"], True))

# 把所有正常+其他内容，按轮询分给 15 个用户
all_normals = normals + others
for idx, item in enumerate(all_normals):
    user_contents[idx % 15].append((item["content"], False))

# 打印分配摘要
total_items = 0
for idx in range(15):
    items = user_contents[idx]
    vios = sum(1 for _, is_v in items if is_v)
    if vios == 0:
        expected = "none"
    elif vios == 1:
        expected = "mute_3days"
    else:
        expected = "mute_7days"
    total_items += len(items)
    print(f"  用户{idx+1:02d} ({NICKNAMES[idx]}): 总{len(items)}条，违规{vios}条 -> 预期{expected}")
print(f"总计: {total_items} 条")

# ── 生成 SQL ──
lines = [
    "-- ================================================================",
    "-- ShillGuard 测试种子数据：15个测试用户 + 110条测试内容（今日发布）",
    "-- 生成自 golden_set.json，用于前端+Agent 端到端测试",
    "-- 执行前确保 MySQL 连接正常：mysql -h 192.168.150.101 -u root -p",
    "-- ================================================================",
    "USE shill_guard;",
    "SET NAMES utf8mb4;",
    "",
    "-- ================================================================",
    "-- 1. 插入 15 个普通测试用户（role=0，password=123456）",
    "-- ================================================================",
]

for idx in range(15):
    username = f"testuser{idx+1:02d}"
    nickname = NICKNAMES[idx]
    lines.append(
        f"INSERT IGNORE INTO sys_user "
        f"(username, password, nickname, role, status, created_time, updated_time) "
        f"VALUES ('{username}', '{BCRYPT_123456}', '{nickname}', 0, 0, NOW(), NOW());"
    )

lines += [
    "",
    "-- 获取刚插入的 15 个测试用户 ID（用变量存储）",
]
for idx in range(15):
    lines.append(f"SET @u{idx+1} = (SELECT user_id FROM sys_user WHERE username = 'testuser{idx+1:02d}' LIMIT 1);")

lines += [
    "",
    "-- ================================================================",
    "-- 2. 选一个用于挂靠评论的帖子",
    "-- ================================================================",
    "SET @base_post = (SELECT post_id FROM content_post ORDER BY post_id LIMIT 1);",
    "",
    "-- ================================================================",
    "-- 3. 插入 110 条测试评论（全部 created_time=NOW()，即今天）",
    "--    分组说明：",
    "--    用户 01-05: 无违规内容  -> 预期 mute: none",
    "--    用户 06-10: 恰好1条违规 -> 预期 mute: mute_3days",
    "--    用户 11-15: 多条违规    -> 预期 mute: mute_7days",
    "-- ================================================================",
]

for idx in range(15):
    items = user_contents[idx]
    vios = sum(1 for _, is_v in items if is_v)
    expected = "none" if vios == 0 else ("mute_3days" if vios == 1 else "mute_7days")
    lines.append(f"-- 用户{idx+1:02d} {NICKNAMES[idx]} | 违规{vios}条 | 预期{expected}")
    for content, is_vio in items:
        safe_content = escape(content[:500])
        tag = "【违规】" if is_vio else "【正常】"
        lines.append(
            f"INSERT INTO content_comment "
            f"(user_id, post_id, content, like_count, reply_count, status, is_top, client_ip, created_time, updated_time) "
            f"VALUES (@u{idx+1}, @base_post, '{safe_content}', 0, 0, 0, 0, '127.0.0.1', NOW(), NOW()); -- {tag}"
        )
    lines.append("")

lines += [
    "-- ================================================================",
    "-- 4. 更新帖子评论数",
    "-- ================================================================",
    "UPDATE content_post",
    "SET comment_count = (SELECT COUNT(*) FROM content_comment c WHERE c.post_id = content_post.post_id)",
    "WHERE post_id = @base_post;",
    "",
    "-- ================================================================",
    "-- 5. 验证汇总",
    "-- ================================================================",
    "SELECT '测试用户数'   AS type, COUNT(*) AS cnt FROM sys_user WHERE username LIKE 'testuser%'",
    "UNION ALL",
    "SELECT '今日评论总数', COUNT(*) FROM content_comment WHERE DATE(created_time) = CURDATE()",
    "UNION ALL",
    "SELECT '今日帖子总数', COUNT(*) FROM content_post WHERE DATE(created_time) = CURDATE();",
    "",
    "-- 各用户今日发言数",
    "SELECT u.username, u.nickname,",
    "       COUNT(c.comment_id) AS comment_cnt,",
    "       0 AS post_cnt",
    "FROM sys_user u",
    "LEFT JOIN content_comment c ON c.user_id = u.user_id AND DATE(c.created_time) = CURDATE()",
    "WHERE u.username LIKE 'testuser%'",
    "GROUP BY u.user_id, u.username, u.nickname",
    "ORDER BY u.username;",
]

sql_content = "\n".join(lines)
with open(OUTPUT_SQL, "w", encoding="utf-8") as f:
    f.write(sql_content)

print(f"\n生成完成: {OUTPUT_SQL}")
