# 在 Ubuntu 22.04.5 虚拟机上跑 Benchmark 专用 Compose

## 重要说明

1. **不要把下面内容追加进业务中间件的 `docker-compose.yml`**（MySQL/ES/RabbitMQ 那份）。  
   评测与业务分离，避免内存打爆。本文件是独立的 `docker-compose.bench.yml`。
2. 本 compose **只提供「评测工作区 + Docker CLI」**，不会一键跑完 SWE-bench/AgentBench。  
   具体评测仍要在 `bench-runner` 里按官方仓库 `git clone` + 官方命令执行。
3. 跑公开 Benchmark 时建议：**先 `docker compose -f docker-compose.bench.yml up`，用完 `down`**；必要时临时停业务里的 `kibana`。

---

## 一、把文件拷到虚拟机

在 **Windows**（有本仓库的机器）可用 scp（按你的 SSH 账号改）：

```bat
scp D:\project\shill-guard-ai\deploy\docker-compose.bench.yml user@192.168.150.101:~/shill-guard-bench/docker-compose.bench.yml
```

或在 VM 上直接新建文件，把 `docker-compose.bench.yml` 内容粘贴进去。

在 **Ubuntu 22.04.5 VM** 上：

```bash
mkdir -p ~/shill-guard-bench/data/swebench ~/shill-guard-bench/data/agentbench ~/shill-guard-bench/data/reports
cd ~/shill-guard-bench
# 确保 docker-compose.bench.yml 在此目录
ls -l docker-compose.bench.yml
```

---

## 二、启动 / 进入 / 停止（常用命令）

```bash
cd ~/shill-guard-bench

# 启动（首次会 apt 装 git/python/docker-cli，稍慢）
docker compose -f docker-compose.bench.yml up -d

# 看日志（确认出现 bench-runner ready）
docker compose -f docker-compose.bench.yml logs -f bench-runner

# 进入工作区
docker compose -f docker-compose.bench.yml exec bench-runner bash

# 在容器内自检
docker version
python3 --version
ls -la /workspace

# 用完关闭（不删 data 目录里的数据集）
exit   # 先退出容器 shell
docker compose -f docker-compose.bench.yml down
```

查看占用：

```bash
docker ps --filter name=shill-bench
docker stats shill-bench-runner --no-stream
```

---

## 三、进容器后：SWE-bench（示例骨架）

> 官方仓库与参数会随版本变，以 [SWE-bench](https://github.com/princeton-nlp/SWE-bench) 当前 README 为准。下面是常见流程骨架。

```bash
# 已在 bench-runner 容器内，cwd=/workspace
cd /workspace/swebench
git clone https://github.com/princeton-nlp/SWE-bench.git
cd SWE-bench
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 按官方文档运行 evaluation / Verified 子集
# 例（命令名以官方为准，勿照抄过期参数）：
# python -m swebench.harness.run_evaluation --help
```

数据集与实例容器会占大量磁盘；请保证 VM 磁盘充足，数据落在宿主机 `~/shill-guard-bench/data/`。

---

## 四、进容器后：AgentBench（示例骨架）

```bash
cd /workspace/agentbench
git clone https://github.com/THUDM/AgentBench.git
cd AgentBench
# 按官方 README 安装依赖并只跑 1～2 个环境子集
```

---

## 五、跑评测时如何给业务腾内存（可选）

在**业务 compose 所在目录**（不是 bench 目录）：

```bash
# 仅示例：临时停 Kibana
docker compose stop kibana

# 评测结束后
docker compose start kibana
```

---

## 六、若你坚持「追加」进业务 yml（不推荐）

只把业务文件里 `services:` 下**追加** `bench-runner` 整段（见 `docker-compose.bench.yml` 中该 service），并增加：

```yaml
networks:
  shill-bench-net:
    driver: bridge

volumes:
  bench_home:
```

同时把 `bench-runner` 的 `networks` 改成同时加入 `shill-guard-net`（若需要访问业务网，一般**不需要**）。

**仍强烈建议用独立文件 + 上面第二节命令，不要追加。**

---

## 七、与 Windows 的关系

- 业务 AI / Pi / Hermes / MCP：继续在 Windows `D:\project\shill-guard-ai`。  
- 公开 Benchmark 重任务：在 VM 的 `shill-bench-runner` 里跑。  
- 跑完把 `reports` 里的结果 scp 回 Windows 即可。
