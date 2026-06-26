# aquant — A股量化交易系统

自动选股 → 三策略联合评分 → 交易指令 → 模拟盘 → 自适应学习 → 手机查看

## 技术栈

- Python ≥ 3.9, CLI 入口 `aquant` 命令
- 数据源: 新浪财经 API (主) / AKShare (备用)
- 本地缓存: SQLite (`~/.aquant/cache/aquant.db`)
- 前端: 单文件 HTML (`index.html`) — 托管在 GitHub Pages
- Shell: `run_daily.sh` — 每日 cron 自动化

## 项目结构

```
aquant/
├── aquant/                  # Python 包
│   ├── cli.py               # CLI 入口 (argparse)
│   ├── config.py            # YAML 配置 (~/.aquant/config.yaml)
│   ├── utils.py             # format_cny, format_pct, retry
│   ├── data/
│   │   ├── feed.py          # DataFeed: 缓存优先 + 新浪API/akshare
│   │   ├── cache.py         # SQLite 缓存
│   │   ├── symbols.py       # 股票代码标准化
│   │   └── universe.py      # 全市场筛选 → 夏普排名
│   ├── strategy/
│   │   ├── base.py          # BaseStrategy (init → next → finish)
│   │   └── examples/        # ma_cross, turtle, mean_revert
│   ├── backtest/
│   │   ├── engine.py        # BacktestEngine (事件循环)
│   │   ├── portfolio.py     # Portfolio (A股费率)
│   │   ├── metrics.py       # 夏普/回撤/胜率/波动率
│   │   └── reporter.py      # 报告 + 图表
│   └── live/
│       ├── scanner.py       # 信号扫描
│       ├── recommend.py     # 三策略联合评分 + 交易计划
│       ├── paper.py         # 模拟盘引擎
│       ├── tracker.py       # 表现追踪 + 自适应权重
│       └── changelog.py     # 每日更新日志
├── tests/                   # 54 个单元测试 (unittest)
├── run_daily.sh             # 每日自动运行 (cron 15:30)
├── deploy.sh                # 推送到 GitHub Pages
├── index.html               # 手机面板
├── watchlist.txt            # 自选股 (自动更新)
├── CHANGELOG.md             # 推荐演变日志 (自动生成)
├── reports/                 # 每日报告 + 追踪数据
└── logs/                    # 运行日志
```

## 常用命令

```bash
# 安装
pip3 install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple

# 每日一键
./run_daily.sh

# 自动选股 + 推荐
python3 -m aquant recommend --auto --save --update-watchlist

# 回测
python3 -m aquant backtest 000001 --strategy ma_cross --plot

# 扫描
python3 -m aquant scan --strategy turtle --symbols 000001,600519

# 下载数据
python3 -m aquant data fetch 000001

# 运行测试
python3 -m unittest discover -s tests -v
```

## 架构要点

- **数据流**: 新浪API → SQLite缓存 → DataFeed.get() → 策略/回测/推荐
- **推荐评分 (0-100)**: 信号一致性(40分) + 信号新鲜度(30分) + 历史夏普(30分)
- **交易计划**: 买入价=当前价, 止损=买入价-2×ATR, 止盈=买入价+3×ATR, 仓位按单笔亏损≤2%资金
- **自适应学习**: 模拟盘平仓≥5笔后激活, 按策略累计盈亏调整权重
- **前端**: 纯静态 HTML, 读取 `reports/tracker.json`, GitHub Pages 托管

## 注意事项

- 新浪API有时不稳定，数据下载失败会fallback到akshare
- 一手(100股)是A股最小交易单位
- 建议收盘后运行 (15:30+)，确保数据完整
- 模拟盘初始资金 ¥10,000，按实际A股费率(佣金0.03%, 印花税0.1%卖)
- pip 清华源安装更快；网络不稳定时 akshare 可能超时
