# aquant — A 股量化交易系统

**自动选股 → 三策略联合评分 → 交易指令 → 模拟盘 → 自适应学习 → 手机随时查看**

## 快速开始

```bash
cd /Users/dh/AI/aquant

# 安装依赖（只需一次）
pip3 install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple

# 一键运行（自动扫描全市场、生成推荐、更新手机面板）
./run_daily.sh
```

手机访问：`https://aldahuang.github.io/aquantsignal/`

## 命令

| 命令 | 作用 |
|------|------|
| `./run_daily.sh` | 每日一键：扫描→推荐→模拟盘→学习→推送 |
| `python3 -m aquant recommend --auto` | 自动选股 + 推荐 + 交易指令 |
| `python3 -m aquant backtest 000001 --strategy ma_cross` | 单股票回测 |
| `python3 -m aquant data fetch 000001` | 下载单只股票数据 |
| `python3 -m aquant scan --strategy ma_cross --symbols 000001,600519` | 扫描指定股票信号 |

### recommend --auto 可选参数

```
--top-n 20        # 精选 20 只（默认）
--max-price 50    # 只看 50 元以下股票（默认 100）
--no-star=false   # 包含科创板
--no-save         # 不保存报告
--no-update       # 不更新自选股
```

## 目录结构

```
aquant/
├── aquant/                     # Python 包
│   ├── cli.py                  # 命令行入口
│   ├── config.py               # 配置管理
│   ├── utils.py                # 工具函数
│   ├── data/
│   │   ├── feed.py             # 数据获取（新浪API + 缓存）
│   │   ├── cache.py            # SQLite 缓存
│   │   ├── symbols.py          # 股票代码工具
│   │   └── universe.py         # 自动选股 + 夏普排名
│   ├── strategy/
│   │   ├── base.py             # 策略基类
│   │   └── examples/           # 均线交叉 / 海龟突破 / 布林回归
│   ├── backtest/
│   │   ├── engine.py           # 回测引擎（事件循环）
│   │   ├── portfolio.py        # 资金管理（A股费率）
│   │   ├── metrics.py          # 绩效指标（夏普/回撤/胜率）
│   │   └── reporter.py         # 报告 + 图表
│   └── live/
│       ├── scanner.py          # 信号扫描
│       ├── recommend.py        # 多策略推荐 + 交易指令
│       ├── paper.py            # 模拟盘引擎
│       ├── tracker.py          # 表现追踪 + 自适应学习
│       └── changelog.py        # 每日更新日志
├── tests/                      # 54 个单元测试
├── run_daily.sh                # 每日自动运行脚本
├── deploy.sh                   # 推送到 GitHub Pages
├── index.html                  # 手机面板
├── watchlist.txt               # 自选股（自动更新）
├── CHANGELOG.md                # 推荐演变日志（自动生成）
├── reports/                    # 每日报告 + 追踪数据（自动生成）
└── logs/                       # 运行日志（自动生成）
```

## 每日自动化

**定时**：周一到周五 15:30（A股收盘后）自动运行

**流程**：

```
Step 1: 验证昨日推荐命中率
Step 2: 学习模拟盘盈亏 → 调整策略权重
Step 3: 全市场扫描 → 夏普排名 → 推荐
Step 4: 更新模拟盘（建仓/平仓/止损）
Step 5: 生成日志（记录增减原因 + 学习变化）
Step 6: 推送到 GitHub Pages（手机可看）
```

## 策略

| 策略 | 原理 | 适用场景 |
|------|------|----------|
| 均线交叉 | 快线上穿慢线→买入，下穿→卖出 | 趋势行情 |
| 海龟突破 | 突破 N 日最高价→买入，跌破 M 日最低→卖出 | 强势突破 |
| 布林回归 | 触及下轨→买入，回归中轨→卖出 | 震荡行情 |

系统自动判断哪只股票适合哪种策略，综合评分给出推荐。

## 交易指令

每只推荐附带：

- **买入价**：次日开盘价
- **止损价**：买入价 - 2×ATR（跌破立即卖出）
- **止盈价**：买入价 + 3×ATR（涨到卖出）
- **仓位**：按单笔亏损 ≤ 2% 资金计算
- **风险**：止损触发时的最大亏损比例

## 自适应学习

模拟盘积累 5 笔以上平仓交易后自动激活：

- 盈利的策略 → 加重
- 亏损的策略 → 减重
- 严重亏损 → 半停用
- 每次调整记录在日志中

## 依赖

- Python ≥ 3.9
- akshare, pandas, numpy, matplotlib, pyyaml, certifi

## 故障排查

### 数据下载失败 / 网络超时

新浪 API（`money.finance.sina.com.cn`）偶尔不稳定。系统会自动 fallback 到 AKShare：

```bash
# 测试数据获取
python3 -m aquant data fetch 000001

# 单只股票回测（用模拟数据测试策略逻辑）
python3 -m aquant backtest 000001 --strategy ma_cross --mock
```

### 缓存问题

数据缓存在 `~/.aquant/cache/aquant.db`（SQLite）。如需强制刷新：

```bash
python3 -m aquant data fetch 000001 --force
```

### 回测报 "Insufficient data"

- 确保数据时间跨度足够：`--start 2020-01-01`
- 或使用 `--mock` 生成模拟数据快速验证策略逻辑

### 手机面板不显示

1. 确认已运行过 `./run_daily.sh`（至少需要 `reports/tracker.json`）
2. 本地测试：`cd aquant && python3 -m http.server 8080`，然后访问 `http://localhost:8080`
3. 线上：确认 `deploy.sh` 已推送最新 `reports/` 到 GitHub Pages

## 测试

```bash
python3 -m unittest discover -s tests -v
# 54 tests, all passing
```
