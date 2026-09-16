-- ================================================================
--  检测功能测试数据：5篇引流帖子 + 恶意评论（人身攻击/网暴/诈骗引流）
--  恶意评论集中在 user 8/11/9，便于检测 agent 打出高分
--  所有时间用 NOW()（今天）
-- ================================================================
USE shill_guard;
SET NAMES utf8mb4;

-- 5 篇容易引起舆论的图文帖子（发帖人：user 4-7）
INSERT INTO content_post (user_id, title, content, cover_url, media_url, post_type, topic_tag, status, view_count, like_count, comment_count, created_time, updated_time)
VALUES
(4, '月薪3000到底该不该生二胎？网友吵翻了', '最近看到一个话题，月薪3000的家庭想生二胎，有人说穷就别生害了孩子，有人说生育自由跟收入无关。大家怎么看？说实话我觉得量力而行，但也不该被道德绑架。', 'https://picsum.photos/800/600?random=101', 'https://picsum.photos/800/600?random=101', 2, '社会话题', 0, 12800, 342, 0, NOW(), NOW()),
(5, '00后整顿职场是自私还是清醒？', '动不动就准点下班、拒绝加班、怼领导，00后这是整顿职场还是不知天高地厚？老一辈当年都是任劳任怨过来的，现在年轻人是不是太矫情了？', 'https://picsum.photos/800/600?random=102', 'https://picsum.photos/800/600?random=102', 2, '职场话题', 0, 25600, 891, 0, NOW(), NOW()),
(6, '女主播直播翻车被全网群嘲，到底冤不冤？', '某女主播直播时口误说错话被录屏疯传，现在全网都在骂她，甚至有人扒出她家里地址。说实话她确实说错了，但这样网暴一个人是不是太过分了？', 'https://picsum.photos/800/600?random=103', 'https://picsum.photos/800/600?random=103', 2, '热点事件', 0, 45000, 1203, 0, NOW(), NOW()),
(7, '彩礼30万多不多？男生出不起就该被分手吗？', '谈了三年恋爱，女方要30万彩礼，男生家里拿不出来，女方直接提分手。有人说女方物质，有人说男生没本事。彩礼到底是习俗还是买卖？', 'https://picsum.photos/800/600?random=104', 'https://picsum.photos/800/600?random=104', 2, '情感话题', 0, 31000, 567, 0, NOW(), NOW()),
(4, '小镇做题家真的比不过大城市的孩子吗？', '看到有人嘲讽小镇做题家眼界窄、没见过世面，再努力也比不上大城市出身的人。这种说法是不是地域歧视？努力真的没用吗？', 'https://picsum.photos/800/600?random=105', 'https://picsum.photos/800/600?random=105', 2, '社会话题', 0, 18900, 445, 0, NOW(), NOW());

-- 取出刚插入的5个帖子ID
SET @p1 = (SELECT post_id FROM content_post WHERE user_id=4 AND title LIKE '月薪3000%' ORDER BY post_id DESC LIMIT 1);
SET @p2 = (SELECT post_id FROM content_post WHERE user_id=5 AND title LIKE '00后整顿职场%' ORDER BY post_id DESC LIMIT 1);
SET @p3 = (SELECT post_id FROM content_post WHERE user_id=6 AND title LIKE '女主播直播翻车%' ORDER BY post_id DESC LIMIT 1);
SET @p4 = (SELECT post_id FROM content_post WHERE user_id=7 AND title LIKE '彩礼30万%' ORDER BY post_id DESC LIMIT 1);
SET @p5 = (SELECT post_id FROM content_post WHERE user_id=4 AND title LIKE '小镇做题家%' ORDER BY post_id DESC LIMIT 1);

-- ================================================================
-- 恶意评论 user 8（赵丽吃瓜人）：人身攻击、网暴、地域歧视 —— 目标 score>=0.9
-- ================================================================
INSERT INTO content_comment (user_id, post_id, content, like_count, reply_count, status, is_top, client_ip, created_time, updated_time) VALUES
(8, @p1, '月薪3000还生孩子？你就是个自私的废物，穷人生什么生，生下来也是祸害社会，你家孩子注定是底层垃圾', 12, 0, 0, 0, '113.45.12.66', NOW(), NOW()),
(8, @p1, '楼上别洗了，穷鬼就是穷鬼，认知低还嘴硬，活该一辈子底层，你这种人也配上网上发言？', 8, 0, 0, 0, '113.45.12.66', NOW(), NOW()),
(8, @p2, '00后都是没断奶的巨婴，自私自利还美其名曰清醒，能力没有脾气倒不小，公司就该把你们这些废物全开了', 23, 0, 0, 0, '113.45.12.66', NOW(), NOW()),
(8, @p3, '这种女主播就是活该被骂，长那张脸就靠卖骚赚钱，翻车是迟早的事，被人肉也是她自找的，活该社死', 45, 0, 0, 0, '113.45.12.66', NOW(), NOW()),
(8, @p3, '把她家地址发出来怎么了，这种人就该让全小区知道她多不要脸，网暴她怎么了，她直播骗钱的时候怎么不嫌过分', 19, 0, 0, 0, '113.45.12.66', NOW(), NOW()),
(8, @p5, '小镇做题家就是眼界窄的土包子，再怎么刷题也改不了骨子里的穷酸样，大城市的人随便一个都甩你们十八条街', 31, 0, 0, 0, '113.45.12.66', NOW(), NOW());

-- ================================================================
-- 恶意评论 user 11（金帅财富圈）：诈骗引流、站外推广 —— 目标 score>=0.9
-- ================================================================
INSERT INTO content_comment (user_id, post_id, content, like_count, reply_count, status, is_top, client_ip, created_time, updated_time) VALUES
(11, @p1, '月薪3000还纠结生不生二胎？不如跟我做副业，月入3万不是梦，加我微信 jinshuai888 一对一带你，名额有限先到先得', 5, 0, 0, 0, '118.22.33.109', NOW(), NOW()),
(11, @p2, '00后还整顿职场？不如来我团队，一部手机日入过千，不囤货不压货，加V：jinshuai888，零基础也能做，带你躺赚', 7, 0, 0, 0, '118.22.33.109', NOW(), NOW()),
(11, @p4, '彩礼拿不出来？教你一招，跟我做投资，5000本金一周翻倍，加我微信 jinshuai888 进内部群，导师带单稳赚不赔', 9, 0, 0, 0, '118.22.33.109', NOW(), NOW()),
(11, @p5, '小镇做题家不用认命，跟我搞币圈，去年我跟单的人全都财富自由了，加V jinshuai888 进财富密码群，错过拍大腿', 4, 0, 0, 0, '118.22.33.109', NOW(), NOW()),
(11, @p3, '别酸女主播了，人家一场直播顶你半年工资，想赚钱加我微信 jinshuai888，教你零粉起号月入十万，带你一起割韭菜', 6, 0, 0, 0, '118.22.33.109', NOW(), NOW());

-- ================================================================
-- 恶意评论 user 9（孙阳随便看看）：人身攻击+煽动 —— 目标 0.8~0.9 预警
-- ================================================================
INSERT INTO content_comment (user_id, post_id, content, like_count, reply_count, status, is_top, client_ip, created_time, updated_time) VALUES
(9, @p2, '说00后清醒的你们都是loser，自己没本事还怪社会，活该一辈子拧螺丝，废物就该认清自己的位置', 15, 0, 0, 0, '220.181.38.148', NOW(), NOW()),
(9, @p4, '要30万彩礼的女人都是拜金婊，卖女儿的货色，这种女的就该让她孤独终老，谁娶谁倒霉', 22, 0, 0, 0, '220.181.38.148', NOW(), NOW()),
(9, @p5, '小镇做题家就是酸，自己不行还怪地域，穷山恶水出来的能有什么见识，别丢人了', 11, 0, 0, 0, '220.181.38.148', NOW(), NOW()),
-- 一条正常评论，混在中间
(9, @p1, '其实生不生二胎是个人选择，量力而行就好，没必要上纲上线', 38, 0, 0, 0, '220.181.38.148', NOW(), NOW());

-- ================================================================
-- 正常评论 user 5/6/7（发帖人也参与讨论，正常发言，平衡数据）
-- ================================================================
INSERT INTO content_comment (user_id, post_id, content, like_count, reply_count, status, is_top, client_ip, created_time, updated_time) VALUES
(5, @p1, '我觉得关键看有没有人帮忙带孩子，经济反而是其次', 56, 0, 0, 0, '114.66.21.7', NOW(), NOW()),
(6, @p2, '准点下班本来就应该，加班不给钱才是问题所在', 102, 0, 0, 0, '114.66.21.8', NOW(), NOW()),
(7, @p3, '说错话可以批评，但网暴和扒地址真的越界了', 187, 0, 0, 0, '114.66.21.9', NOW(), NOW()),
(5, @p4, '彩礼这事双方商量着来就行，没有标准答案', 73, 0, 0, 0, '114.66.21.7', NOW(), NOW()),
(6, @p5, '小镇做题家的努力值得尊重，眼界可以慢慢开拓', 94, 0, 0, 0, '114.66.21.8', NOW(), NOW());

-- 更新帖子的评论数
UPDATE content_post SET comment_count = (SELECT COUNT(*) FROM content_comment WHERE content_comment.post_id = content_post.post_id) WHERE post_id IN (@p1,@p2,@p3,@p4,@p5);

SELECT '插入完成' AS result, COUNT(*) AS post_count FROM content_post WHERE created_time >= CURDATE()
UNION ALL
SELECT '评论总数', COUNT(*) FROM content_comment WHERE created_time >= CURDATE();
