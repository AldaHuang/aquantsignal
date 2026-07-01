#!/bin/bash
# 推送报告到 GitHub Pages，手机可随时访问
# 首次使用需要：
#   1. GitHub 上创建仓库：aquantsignal（或你喜欢的名字）
#   2. Settings → Pages → Source: main branch, root
#   3. 把下面的 GITHUB_USER 改成你的 GitHub 用户名
# 之后每次 run_daily.sh 跑完会自动部署

set -e
cd "$(dirname "$0")"

GITHUB_USER="AldaHuang"
REPO_NAME="aquantsignal"             # ← 改成你的仓库名
COMMIT_MSG="$(date +%Y-%m-%d) 每日推荐更新"

# Initialize git if needed
if [ ! -d .git ]; then
  git init
  git remote add origin "git@github.com:${GITHUB_USER}/${REPO_NAME}.git"
fi

# Add web-facing files
git add index.html reports/tracker.json reports/paper.json CHANGELOG.md watchlist.txt
git commit -m "$COMMIT_MSG" 2>/dev/null || echo "  (no changes to commit)"

# Push
git push -u origin main 2>&1 || echo "  Push failed — check GitHub username/repo"
echo ""
echo "  📱 手机访问: https://${GITHUB_USER}.github.io/${REPO_NAME}/"
