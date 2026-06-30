# aquant — A 股量化交易系统

**自动选股 → 三策略联合评分 → 交易指令 → 模拟盘 → 自适应学习 → 手机随时查看**

## 快速开始

```bash
cd /Users/dh/AI/aquant
pip3 install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
./run_daily.sh
```

手机访问：`https://aldahuang.github.io/aquantsignal/`

## 命令

| 命令 | 作用 |
|------|------|
| `./run_daily.sh` | 每日一键：扫描→推荐→模拟盘→学习→推送 |
| `python3 -m aquant recommend --auto` | 自动选股 + 推荐 |
| `python3 -m aquant backtest <code> --strategy <name>` | 单股票回测 |
| `python3 -m aquant data fetch <code>` | 下载股票数据 |
| `python3 -m aquant scan --strategy <name> --symbols <codes>` | 扫描信号 |

## 目录结构

```
aquant/
├── aquant/                     # Python 包（~3600 行）
│   ├── cli.py                  # 命令行入口
│   ├── config.py               # YAML 配置（~/.aquant/config.yaml）
│   ├── utils.py                # 格式化 / 重试
│   ├── data/
│   │   ├── feed.py             # 数据获取（新浪API + SQLite缓存）
│   │   ├── cache.py            # SQLite 缓存
│   │   ├── symbols.py          # 股票代码工具
│   │   └── universe.py         # 自动选股 + 夏普排名 + 参数优化
│   ├── strategy/
│   │   ├── base.py             # 策略基类
│   │   ├── optimizer.py        # 市场状态识别 + 参数网格搜索
│   │   └── examples/           # 均线交叉 / 海龟突破 / 布林回归
│   ├── backtest/
│   │   ├── engine.py           # 回测引擎（事件循环）
│   │   ├── portfolio.py        # 资金管理（A股费率）
│   │   ├── metrics.py          # 夏普/回撤/胜率/盈亏比
│   │   └── reporter.py         # 报告 + 图表
│   └── live/
│       ├── scanner.py          # 信号扫描
│       ├── recommend.py        # 多策略推荐 + 交易指令（ATR止损止盈）
│       ├── paper.py            # 模拟盘引擎（资金管理/持仓/平仓）
│       ├── tracker.py          # 表现追踪 + 盈亏驱动自适应学习
│       └── changelog.py        # 每日更新日志
├── tests/                      # 54 个单元测试
├── run_daily.sh                # 每日自动（cron 15:30 + launchd 兜底）
├── deploy.sh                   # 推送到 GitHub Pages
├── wakeup_check.sh             # Mac 唤醒后补跑
├── index.html                  # 手机面板（推荐/K线/模拟盘/日志）
├── watchlist.txt               # 自选股（自动更新）
├── CHANGELOG.md                # 推荐演变日志（自动生成）
├── reports/                    # 每日报告 + 追踪数据（自动生成）
└── logs/                       # 运行日志
```

## 每日自动化

**定时**：周一到周五 15:30（A股收盘后），错过自动补

**流程**：

```
Step 1: 验证昨日推荐方向准确率
Step 2: 学习模拟盘盈亏 → 调整策略权重
Step 3: 全A股扫描 → 300只候选 → 夏普排名 → Top 20 精选
Step 4: 更新模拟盘（建仓/平仓/止损，预算控制）
Step 5: 生成日志 + K线数据
Step 6: 推送到 GitHub Pages（手机可查看）
```

## 策略

| 策略 | 原理 | 适用 |
|------|------|------|
| 均线交叉 | 快线上穿慢线→买入 | 趋势行情 |
| 海龟突破 | 突破N日高→买入 | 强势突破 |
| 布林回归 | 触及下轨→买入 | 震荡行情 |

系统自动检测市场状态（ADX），趋势市偏重均线和海龟，震荡市偏重布林。同时每天对候选股票做参数网格搜索，找到每只股票的最优参数。

## 交易指令

每只推荐附带完整操作计划：

- 买入价 / 止损价 / 止盈价（基于 ATR）
- 仓位（单笔风险 ≤ 2% 资金）
- 手机可查看 K 线迷你图

## 模拟盘

- 初始资金 ¥10,000，资金管理防超买
- 按评分排序买入，最多 8 只持仓
- 记录每笔成交价、佣金、印花税
- 活动时间线展示所有操作

## 自适应学习

模拟盘积累 5 笔以上平仓交易后自动激活：

- 盈利策略 → 加重；亏损 → 减重；严重亏损 → 半停用
- 市场状态变化时自动调整策略重心
- 每次调整记录在日志中

## 手机面板

`https://aldahuang.github.io/aquantsignal/`

四个标签页：推荐（含K线图）/ 交易指令 / 模拟盘 / 日志

## 测试

```bash
python3 -m unittest discover -s tests -v
# 54 tests, all passing
```
