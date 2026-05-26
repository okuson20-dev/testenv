# GitHub 認証が出ない・push できないとき

## 調査結果（この環境）

| 項目 | 状態 |
|------|------|
| リモート URL | `https://github.com/okuson20-dev/testenv.git` |
| credential.helper | `osxkeychain`（Homebrew Git） |
| Keychain の GitHub 認証 | **未登録** |
| `~/.ssh/id_ed25519` 等 | **なし**（GitHub 用 SSH 鍵なし） |
| `git push` 時のエラー | `fatal: could not read Username for 'https://github.com': Device not configured` |

### なぜ認証画面が出ないか

1. **保存済み認証がない**  
   Keychain に GitHub のユーザー/トークンが無いため、`osxkeychain` は空を返す。

2. **GitHub はパスワード認証を廃止**  
   HTTPS では **Personal Access Token（PAT）** が必要。通常の GitHub ログインパスワードは使えない。

3. **非対話ターミナル**  
   Cursor のエージェント実行環境など、`stdin` が TTY でないと Git はユーザー名入力プロンプトを出せず、`Device not configured` になる。  
   **対話用の macOS「ターミナル」アプリ**から実行する必要がある。

---

## 解決方法（推奨順）

### 方法 1: SSH 鍵（推奨・一度設定すれば以降ラク）

**macOS の「ターミナル」**を開き、プロジェクトで:

```bash
cd /Users/masato/test_env
chmod +x scripts/setup-github-auth.sh
./scripts/setup-github-auth.sh
```

手順:

1. メールアドレス入力 → SSH 鍵作成
2. 表示された **公開鍵** をコピー
3. ブラウザで [SSH keys / New](https://github.com/settings/ssh/new) を開き貼り付け
4. スクリプトに戻り Enter → `git push`

手動で行う場合:

```bash
ssh-keygen -t ed25519 -C "your@email.com" -f ~/.ssh/id_ed25519_github -N ""
cat ~/.ssh/id_ed25519_github.pub
# → GitHub に登録

cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

ssh -T git@github.com
cd /Users/masato/test_env
git remote set-url origin git@github.com:okuson20-dev/testenv.git
git push -u origin main
```

成功時: `Hi okuson20-dev! You've successfully authenticated...`

---

### 方法 2: GitHub CLI（ブラウザでログイン）

```bash
brew install gh
gh auth login
# GitHub.com → HTTPS → Login with a web browser

gh auth setup-git
cd /Users/masato/test_env
git push -u origin main
```

`gh auth login` は **ブラウザ認証画面**を開くので、HTTPS で確実に通る。

---

### 方法 3: HTTPS + Personal Access Token

1. [Fine-grained または classic PAT](https://github.com/settings/tokens) を作成（`repo` 権限）
2. ターミナルで:

```bash
cd /Users/masato/test_env
git push -u origin main
```

| 入力 | 値 |
|------|-----|
| Username | `okuson20-dev` |
| Password | **PAT**（GitHub ログインパスワードではない） |

Keychain に保存され、次回から聞かれなくなる。

---

## どこで実行するか

| 実行場所 | 認証プロンプト |
|----------|----------------|
| macOS **ターミナル.app** | 出る（SSH / PAT / gh） |
| Cursor **統合ターミナル**（通常） | 出ることが多い |
| Cursor **エージェント / 自動実行** | **出ない**（TTY なし） |

push は **ご自身のターミナル**で実行してください。

---

## `lab.ps1 up` で「Python」とだけ表示される

**原因:** `WindowsApps\python.exe` の **Microsoft Store スタブ** が PATH より先に見つかり、実体の Python が動いていない。

**対処:**

1. [python.org](https://www.python.org/downloads/) から Python 3 をインストール（**Add to PATH** にチェック）
2. **設定 → アプリ → 詳細設定 → アプリ実行エイリアス** で `python.exe` / `python3.exe` を **オフ**
3. 新しい PowerShell で確認:

```powershell
py -3 --version
.\scripts\lab.ps1 up
```

成功時は `Using Python: py -3` のあと compose 生成が進みます。

---

## よくあるエラー

| メッセージ | 原因 | 対処 |
|------------|------|------|
| `Device not configured` | 非対話環境 | ターミナル.app から実行 |
| `Authentication failed` | PAT 未使用 / 期限切れ | PAT 再発行または SSH へ切替 |
| `Permission denied (publickey)` | SSH 鍵未登録 | 公開鍵を GitHub に追加 |
| `Repository not found` | 権限なし / URL 誤り | `okuson20-dev/testenv` の書き込み権限を確認 |

---

## リポジトリ URL

- HTTPS: `https://github.com/okuson20-dev/testenv.git`
- SSH: `git@github.com:okuson20-dev/testenv.git`
