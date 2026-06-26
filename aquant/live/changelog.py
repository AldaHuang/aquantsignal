"""Daily changelog: track recommendation evolution with reasons."""

import os
import json
from datetime import date, timedelta

CHANGELOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "CHANGELOG.md")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")


def write_changelog():
    """Append today's summary with detailed add/remove reasons to CHANGELOG.md."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    today_str = today.isoformat()

    tracker = _load_json("tracker.json")
    weights = tracker.get("strategy_weights", {})

    # Find records
    today_rec = _find_record(tracker, today_str)
    yesterday_rec = _find_record(tracker, yesterday.isoformat())
    yesterday_valid = yesterday_rec.get("validation") if yesterday_rec else None

    # Build changelog entry
    lines = [f"## {today_str}", ""]

    # ── Strategy weights with learning reasons ──
    if weights:
        from aquant.live.tracker import get_learning_status
        learn = get_learning_status()
        pnl_data = learn.get("pnl", {})

        lines.append("### 策略权重（模拟盘盈亏驱动）")
        lines.append("")
        for s, w in sorted(weights.items()):
            bar = "█" * max(1, int(w * 5))
            pnl = pnl_data.get(s, 0)
            if pnl > 5:
                note = f"累计盈利 ¥{pnl:.0f} → 加重"
            elif pnl < -5:
                note = f"累计亏损 ¥{pnl:.0f} → 减重"
            elif pnl < -50:
                note = f"持续亏损 → 半停用"
            else:
                note = "盈亏持平"
            lines.append(f"- {s}: **{w:.2f}** {bar} ({note})")
        lines.append("")

    # ── Yesterday hit rate ──
    if yesterday_valid:
        hits = yesterday_valid.get("buy_hits", 0)
        total = hits + yesterday_valid.get("buy_misses", 0)
        if total > 0:
            wr = yesterday_valid.get("buy_win_rate", 0) * 100
            lines.append(f"### 昨日命中率: {wr:.0f}% ({hits}/{total})")
            lines.append("")

    # ── Changes from yesterday with reasons ──
    today_picks = {p["symbol"]: p for p in today_rec.get("picks", [])} if today_rec else {}
    yesterday_picks = {p["symbol"]: p for p in yesterday_rec.get("picks", [])} if yesterday_rec else {}

    added = {s: p for s, p in today_picks.items() if s not in yesterday_picks}
    removed = {s: p for s, p in yesterday_picks.items() if s not in today_picks}
    stayed = {s: p for s, p in today_picks.items() if s in yesterday_picks}

    lines.append("### 📋 推荐变化")
    lines.append("")

    if added:
        lines.append(f"**新增 {len(added)} 只：**")
        lines.append("")
        for sym, p in sorted(added.items(), key=lambda x: -x[1].get("score", 0)):
            name = p.get("name", sym)
            score = p.get("score", 0)
            signals = p.get("signals", {})
            reasons = p.get("reasons", [])

            # Which strategies triggered
            buy_strats = [k for k, v in signals.items() if v == "BUY"]
            sell_strats = [k for k, v in signals.items() if v == "SELL"]
            verdict = p.get("verdict", "?")

            # Build reason string
            parts = [f"评分{score}"]
            if buy_strats:
                parts.append(f"{'+'.join(buy_strats)}看多")
            if sell_strats:
                parts.append(f"{'+'.join(sell_strats)}看空")
            # Extract Sharpe info from reasons
            for r in reasons:
                if "历史回测" in r:
                    parts.append(r)
                    break
            lines.append(
                f"- 🔴 **{name}** ({sym}) — {verdict} — "
                f"{'，'.join(parts)}"
            )
        lines.append("")

    if removed:
        lines.append(f"**移除 {len(removed)} 只：**")
        lines.append("")
        for sym, p in sorted(removed.items(), key=lambda x: -x[1].get("score", 0)):
            name = p.get("name", sym)
            old_score = p.get("score", 0)
            old_verdict = p.get("verdict", "?")

            # Try to find why it was removed
            if sym in today_picks:
                new_score = today_picks[sym].get("score", 0)
                diff = new_score - old_score
                reason = f"评分 {old_score}→{new_score} ({diff:+d})"
            else:
                # Not in today's top-N — figure out why
                old_signals = p.get("signals", {})
                old_buys = [k for k, v in old_signals.items() if v == "BUY"]
                old_sells = [k for k, v in old_signals.items() if v == "SELL"]

                if not old_buys and old_sells:
                    reason = "所有策略转空，建议卖出"
                elif not old_buys:
                    reason = "买入信号消失，转为观望"
                elif old_score < 30:
                    reason = f"评分过低({old_score})，被新候选替代"
                else:
                    reason = f"夏普排名下滑，新候选表现更优"

            lines.append(
                f"- 🟢 **{name}** ({sym}) — 曾{old_verdict} — {reason}"
            )
        lines.append("")

    if stayed:
        lines.append(f"**持续推荐 {len(stayed)} 只：**")
        lines.append("")
        for sym, p in sorted(stayed.items(), key=lambda x: -x[1].get("score", 0)):
            name = p.get("name", sym)
            score = p.get("score", 0)
            old = yesterday_picks.get(sym, {})
            old_score = old.get("score", 0)
            diff = score - old_score
            arrow = "↑" if diff > 2 else "↓" if diff < -2 else "→"
            lines.append(
                f"- **{name}** ({sym}) — 评分 {score} "
                f"({old_score}→{score} {arrow})"
            )
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Write ──
    entry = "\n".join(lines)
    if os.path.exists(CHANGELOG_PATH):
        with open(CHANGELOG_PATH) as f:
            existing = f.read()
        header_end = existing.find("\n---\n")
        if header_end > 0:
            existing = existing[header_end + 5:]
        entry = entry + existing

    with open(CHANGELOG_PATH, "w") as f:
        f.write(f"# aquant 更新日志\n\n")
        f.write(f"每日自动生成 — 追踪推荐演变和策略自适应\n\n")
        f.write(f"---\n\n")
        f.write(entry)


def _find_record(tracker, date_str):
    for rec in tracker.get("records", []):
        if rec.get("date") == date_str:
            return rec
    return None


def _load_json(filename):
    path = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)
