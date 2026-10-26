# 🚀 CortexForge v2.0 — 48-Hour Launch Playbook (Target: 100+ GitHub Stars)

> **Goal:** Reach 100+ organic GitHub stars on [`rekurt/cortex-forge`](https://github.com/rekurt/cortex-forge) within 48 hours by riding the massive **NousResearch Hermes Agent** wave (140,000+ stars) and targeting self-hosted / AI infrastructure communities.

---

## 1. Why Developers Star CortexForge Instantly

1. **Rides the hottest AI agent wave (`NousResearch/hermes-agent`):** Everyone is trying Hermes Agent, but running it for a team of 10–1,000 employees exposes master API keys and lacks per-user/per-department token caps.
2. **Solves a hard, universal pain point in pure Python stdlib:**
   - **Zero API Key Exposure:** Agent containers only see opaque `QUOTA_KEY_<NAME>` tokens; `quota-proxy` swaps in the real upstream credential on the fly.
   - **Real-time SSE Streaming Token Accounting (`SSEUsageParser`):** Counts `text/event-stream` tokens on the fly (both Anthropic `message_start`/`message_delta` and OpenAI `usage` chunks) with hard `429` cutoffs and thread-safe admission guards.
   - **1,000-User Scale on Pure Docker Compose:** `scripts/bulk-users.py` provisions 1,000 isolated instances in `0.5s` with Compose shard profiles (`shard-0..shard-9`) and isolated Linux bridges (`corp-shard-<N>`) to bypass the Linux kernel `BR_MAX_PORTS=1024` limit.
3. **10-Second Zero-Dependency Live Demo (`make demo`):** Visitors can clone and run `make demo` without Docker or API keys and watch a live multi-tenant SSE quota + 1,000-agent broadcast benchmark in their terminal.

---

## 2. Immediate GitHub Repository Optimization Checklist

Run these commands (with owner authorization) to maximize GitHub search discovery and social preview conversion:

```bash
# 1. Update repository description & topics (remove legacy 'openclaw', add 'hermes-agent', 'nousresearch', 'ai-agents')
gh repo edit rekurt/cortex-forge \
  --description "⚡ Enterprise Multi-Tenant Control Plane for Hermes Agent — run 1 to 1,000+ isolated AI assistants with SSE token quotas, inter-agent broker & zero API key exposure" \
  --add-topic hermes-agent,nousresearch,ai-agents,llm-proxy,token-quota,telegram-bot \
  --remove-topic openclaw
```

---

## 3. Copy-Paste Launch Posts (48-Hour Schedule)

### Channel A: `NousResearch/hermes-agent` Community Showcase (Highest Conversion — Est. 30–50 ⭐)

Post in **`NousResearch/hermes-agent` GitHub Discussions (Show & Tell / Integrations)** and the **Nous Research Discord (`#hermes-agent` / `#showcase`)**:

**Title:**
> ⚡ CortexForge v2.0 — Open-source Multi-Tenant Control Plane to run 1 to 1,000+ isolated Hermes Agent instances with SSE token quotas & zero API key exposure

**Body:**
```markdown
Hey everyone! 👋

We migrated our multi-tenant team assistant platform **CortexForge** to **Hermes Agent (`nousresearch/hermes-agent:v0.22.5`)** and open-sourced the full v2.0 Enterprise stack (MIT license, zero external Python dependencies):

🔗 **Repo:** https://github.com/rekurt/cortex-forge

### What problem does it solve?
When deploying Hermes Agent for a team or company (from 5 to 1,000 employees), you quickly hit three walls:
1. **API Key Leakage:** You don't want 100+ agent containers holding your real `ANTHROPIC_API_KEY` in their environment or `/opt/data/.env`.
2. **Unbounded Token Spend on SSE Streams:** Standard reverse proxies don't meter `text/event-stream` token usage per user or per department in real time.
3. **Inter-Agent Coordination & Fleet Provisioning:** Managing `hermes_data/`, `SOUL.md` sync, and network isolation for hundreds of bots.

### What CortexForge adds around Hermes Agent:
- 🔒 **Zero API Key Exposure (`quota-proxy`):** Each Hermes container only receives an opaque `QUOTA_KEY_<USER>`. `quota-proxy` authenticates the hash (`hmac.compare_digest`), enforces per-user & per-department monthly token caps, and injects the upstream credential (supports both direct Anthropic API and `CLIProxyAPI` Claude Max OAuth).
- 🌊 **Live SSE Streaming Token Accounting (`SSEUsageParser`):** Parses `text/event-stream` (`message_start` / `message_delta` and OpenAI `usage` chunks) on the fly with per-instance & per-department concurrency admission guards.
- 💬 **SQLite WAL Inter-Agent Message Broker (`message-broker`):** Direct bot-to-bot `/send`, priority queues, non-destructive `peek=1`, and 1,000-agent `/broadcast` in **14 ms**.
- 🚀 **1,000-User Bulk Provisioning (`scripts/bulk-users.py`):** Onboards 1,000 isolated Hermes Agent instances from CSV/JSON in **0.5s**, automatically generating Docker Compose shard profiles (`shard-0..shard-9`) and isolated bridge networks (`corp-shard-<N>`) so you never hit the Linux kernel `BR_MAX_PORTS=1024` bridge limit.

### Try it in 10 seconds (no Docker or API keys needed):
```bash
git clone https://github.com/rekurt/cortex-forge.git && cd cortex-forge
make demo
```

Would love feedback from the Hermes Agent community — and if this is useful for your team deployments, a ⭐ on GitHub helps a ton!
```

---

### Channel B: Hacker News — `Show HN` (Est. 40–80 ⭐)

- **Submit URL:** `https://github.com/rekurt/cortex-forge`
- **Title:**
  `Show HN: CortexForge – Run 1,000 isolated Hermes AI agents with SSE token quotas`
- **First Comment by Author (post immediately after submitting):**

```text
Hi HN! Author here.

When you give every employee in a company their own autonomous AI agent (with shell/workspace access and persistent memory via NousResearch's Hermes Agent), three engineering problems show up immediately:

1. Prompt injection or a curious user running `env` inside their agent container exposes your master Anthropic/OpenAI API key.
2. Most LLM requests use `text/event-stream` (SSE), so naive HTTP proxies either buffer the whole stream (breaking UX) or skip token accounting on streams altogether.
3. If you spin up 1,000 containers on a single Docker bridge network, you hit the Linux kernel `BR_MAX_PORTS = 1024` bridge port limit, and sequential `docker inspect` / `stats` polling takes 30+ minutes per cycle.

We built CortexForge (pure Python 3.12 stdlib, SQLite WAL, Docker Compose, MIT license) to solve these without requiring Kubernetes:

- `quota-proxy`: Agents only receive an opaque `QUOTA_KEY_<USER>` token. The proxy verifies the SHA-256 digest in constant time, enforces per-user and per-department monthly token caps with per-instance/per-department admission locks (so 8 concurrent requests against a 30-token cap can't all slip through before the first stream finishes), and parses SSE chunks line-by-line (capped at 64 KB/line against OOM) to record exact token usage in `finally`.
- `message-broker`: SQLite WAL inter-agent message bus supporting priority queues, pagination, and broadcasting to 1,000 agents in ~14 ms.
- `scripts/bulk-users.py`: Bulk-provisions 1,000 isolated agent workspaces and shards Docker Compose into `shard-0..shard-9` with dedicated bridge networks (`corp-shard-<N>`).

You can run a live local benchmark in 5 seconds without Docker or API keys (requires only Python 3.12+):

  git clone https://github.com/rekurt/cortex-forge.git && cd cortex-forge
  make demo

Happy to answer any questions about the SSE parser, SQLite WAL concurrency at 1,000 agents, or the security model!
```

---

### Channel C: Reddit (`r/LocalLLaMA`, `r/selfhosted`, `r/ClaudeAI`) (Est. 30–60 ⭐)

**Subreddits:**
1. `r/LocalLLaMA` — Title: `[Project] CortexForge v2.0: Open-source multi-tenant control plane for Hermes Agent (SSE token quotas, zero API key exposure, 1,000-bot scale on Docker Compose)`
2. `r/selfhosted` — Title: `CortexForge: Self-hosted multi-tenant AI assistant stack on Docker Compose (isolated per-user Hermes Agent bots, token quota proxy, inter-bot messenger)`

---

### Channel D: Telegram / Habr / Russian Dev Communities (Est. 25–40 ⭐)

**Текст поста для профильных Telegram-каналов и чатов (AI / DevOps / Python):**

```markdown
🔥 **CortexForge v2.0 (Open Source, MIT): как поднять 1 000 изолированных AI-ассистентов на Hermes Agent и не разориться на токенах**

Выложили в open-source **CortexForge v2.0** — готовую корпоративную платформу на базе нашумевшего `NousResearch/hermes-agent` (140k+ ⭐):
👉 **GitHub:** https://github.com/rekurt/cortex-forge (будем рады вашей звезде ⭐!)

**Что под капотом (чистый Python 3.12 stdlib + SQLite WAL + Docker Compose, 0 внешних зависимостей):**
• 🔒 **Никаких реальных API-ключей в контейнерах:** боты видят только `QUOTA_KEY_<USER>`, а `quota-proxy` подменяет ключ на лету (поддерживает и прямой Anthropic API, и подписку Claude Max через `CLIProxyAPI`).
• 📊 **Потоковый учёт токенов в SSE-стримах (`SSEUsageParser`):** считает `text/event-stream` на лету + персональные и департаментные лимиты с защитой от конкурентного пробития квоты.
• 💬 **Межинстансный брокер сообщений:** P2P-общение между ботами, приоритеты и broadcast на 1 000 агентов за **14 мс**.
• 🚀 **Масштаб до 1 000 пользователей (`make bulk-import`):** генерация 1 000 изолированных воркспейсов за 0.5 секунды с сетевым шардированием `corp-shard-0..9` (обход лимита ядра Linux в 1024 порта на bridge).

Пощупать вживую можно за 10 секунд без Docker и ключей:
`git clone https://github.com/rekurt/cortex-forge.git && cd cortex-forge && make demo`

Репозиторий и звезда: https://github.com/rekurt/cortex-forge ⭐
```

---

### Channel E: Awesome Lists PRs (Long-tail organic stars)

Open pull requests adding `CortexForge` to:
1. `awesome-selfhosted/awesome-selfhosted` (Section: *Artificial Intelligence / Chatbots*)
2. `Hannibal046/Awesome-LLM` (Section: *LLM Agent Frameworks & Infrastructure*)
3. `e2b-dev/awesome-ai-agents`
