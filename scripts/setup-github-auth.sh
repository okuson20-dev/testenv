#!/usr/bin/env bash
# GitHub へ push するための SSH 認証セットアップ（macOS / Linux）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="${HOME}/.ssh/id_ed25519_github"
REPO_SSH="git@github.com:okuson20-dev/testenv.git"

echo "=== GitHub SSH 認証セットアップ ==="
echo ""

if ! test -t 0; then
  echo "注意: このターミナルは対話式ではありません。"
  echo "  macOS の「ターミナル」アプリから実行してください（Cursor 内蔵ターミナルでも可・TTY 必須）。"
  echo ""
fi

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

if [[ ! -f "${KEY}" ]]; then
  echo "SSH 鍵を作成します: ${KEY}"
  read -r -p "GitHub 登録メールアドレス: " email
  ssh-keygen -t ed25519 -C "${email}" -f "${KEY}" -N ""
else
  echo "既存の鍵を使用: ${KEY}"
fi

# ~/.ssh/config に GitHub 用ホスト設定
if ! grep -q "Host github.com" "${HOME}/.ssh/config" 2>/dev/null; then
  cat >> "${HOME}/.ssh/config" <<EOF

Host github.com
  HostName github.com
  User git
  IdentityFile ${KEY}
  IdentitiesOnly yes
EOF
  chmod 600 "${HOME}/.ssh/config"
  echo "追記しました: ~/.ssh/config"
fi

echo ""
echo "=== 次の公開鍵を GitHub に登録してください ==="
echo "  https://github.com/settings/ssh/new"
echo ""
cat "${KEY}.pub"
echo ""
read -r -p "GitHub に登録したら Enter を押してください..."

echo "接続テスト..."
ssh -T git@github.com || true

cd "${ROOT}"
if git remote get-url origin &>/dev/null; then
  git remote set-url origin "${REPO_SSH}"
  echo "origin を SSH に変更: ${REPO_SSH}"
else
  git remote add origin "${REPO_SSH}"
fi

echo ""
echo "push します..."
git push -u origin main

echo ""
echo "完了。以降: git push"
