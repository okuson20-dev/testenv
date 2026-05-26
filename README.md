# Network Lab (Docker)

Windows など任意の端末で、**LAN 上の複数セグメント + インフラサービス**を Docker だけで再現するラボ環境です。

1 台の PC（Windows + Docker Desktop）に LAN ケーブルを接続する想定の**論理トポロジ**として、セグメントごとにブリッジネットワークを分け、ルータコンテナでセグメント間を接続します。

## 含まれるサービス

| 種別 | デフォルトポート | 設定例での台数 |
|------|------------------|----------------|
| NTP  | UDP 123          | 2            |
| DNS  | TCP/UDP 53       | 2            |
| DHCP | UDP 67           | 1            |
| Syslog | TCP/UDP 514  | 1            |
| SNMP | UDP 161          | 1            |

各サービスは `config/lab.yaml` の `enabled: true/false` で **ON/OFF** できます。  
`ip` は必須、`port` は省略時に上記デフォルトを使用します。

## 前提

- [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)（WSL2 バックエンド推奨）
- Python 3.9+（compose 生成用）
- 管理者権限は **DHCP のホスト公開 (67/udp)** を使う場合のみ必要なことがあります

**初回のインストールから起動確認まで:** [docs/起動手順書.md](docs/起動手順書.md)

## Git から取得（推奨）

リモートに push 済みの場合、各 PC では clone / pull だけで揃えられます。

```powershell
git clone https://github.com/<組織またはユーザー>/network-lab.git
cd network-lab
copy config\lab.json.example config\lab.json
.\scripts\lab.ps1 up
```

更新時:

```powershell
git pull
.\scripts\lab.ps1 restart
```

リポジトリの初回登録（管理者向け）は [docs/起動手順書.md](docs/起動手順書.md#11-git-リポジトリへの登録初回のみ) を参照。

## クイックスタート (Windows)

```powershell
cd C:\path\to\test_env
copy config\lab.json.example config\lab.json
.\scripts\lab.ps1 up
```

設定は **JSON**（Python 追加パッケージ不要）または **YAML**（`pip install -r requirements.txt` で PyYAML）のどちらでも使えます。

```powershell
.\scripts\lab.ps1 status
.\scripts\lab.ps1 down
```

Linux / macOS:

```bash
cp config/lab.yaml.example config/lab.yaml
pip install -r requirements.txt
chmod +x scripts/lab.sh
./scripts/lab.sh up
```

## 設定ファイル `config/lab.yaml`

### 物理 NIC のデフォルトゲートウェイを自動取得

`lab up` / `generate` のたびに、**Windows（または Linux/macOS）のルーティングテーブル**からデフォルト GW を読み取ります。

```yaml
host:
  gateway: from_host      # 物理NIC のデフォルトGWを検出
  interface: "Ethernet"   # 省略可。指定時はその NIC のデフォルトルートのみ

router:
  upstream_gateway: from_host   # 検出した GW をルータに渡す（外向きは Docker ホスト経由）
  upstream_via: auto
```

検出結果は `generated/host-network.json` に保存されます。事前確認:

```powershell
.\scripts\lab.ps1 detect-gateway
```

| キーワード | 意味 |
|------------|------|
| `from_host` / `physical` | OS から検出した物理NICのデフォルトGW |
| `auto` | セグメント内のラボ用GW（サブネットの `.1` = ルータ） |

**注意:** Docker セグメントの `gateway` は通常 `auto`（ラボ内）にしてください。`from_host` をセグメントに指定すると、物理LANのGWアドレスがブリッジ上に載り、多くの場合は動作しません。

DHCP でクライアントに物理GWを配りたい場合のみ:

```yaml
  dhcp-main:
    options:
      gateway: from_host
```

### セグメント

各 `segments` エントリが 1 つの LAN セグメント（Docker bridge）になります。

```yaml
segments:
  - name: segment-a
    subnet: 172.30.10.0/24
    gateway: auto   # 172.30.10.1（ルータのセグメント側IP）
```

### サービスの ON/OFF

```yaml
services:
  ntp-secondary:
    type: ntp
    enabled: false    # 起動しない
    segment: segment-a
    ip: 172.30.10.10
```

設定を変えたら必ず再生成・再起動します。

```powershell
.\scripts\lab.ps1 restart
```

### ポート

```yaml
  snmp-main:
    type: snmp
    enabled: true
    segment: segment-mgmt
    ip: 172.30.99.161
    port: 1161    # 省略時は 161
```

### ホストへのポート公開

複数サービスが同じポート（例: NTP 123）を使うため、デフォルトは **内部ネットワークのみ** です。

```yaml
publish_ports: false  # 推奨: セグメント内・ルータ経由で検証

publish_ports: true
services:
  ntp-primary:
    host_port: 1123   # ホスト 1123 → コンテナ 123（重複しないよう各サービスで指定）
    port: 123         # コンテナ内ポート（省略時はデフォルト）
```

## トポロジ（デフォルト例）

```
                    [ Windows PC + Docker ]
                              |
                    +---------+---------+
                    |   lab-router      |
                    | .10.1 / .20.1 /   |
                    |      .99.1        |
        +-----------+-----------+-----------+
        | segment-a | segment-b | segment-mgmt |
        | 172.30.10 | 172.30.20 | 172.30.99    |
        +-----------+-----------+-----------+
     ntp-secondary  dns-secondary  ntp-primary
     dns-primary    dhcp-main      syslog-main
                                     snmp-main
```

## 動作確認例

`publish_ports: true` のとき（ホストから）:

```powershell
# DNS
nslookup gateway.lab.local 127.0.0.1

# NTP (ntpdate があれば)
# w32tm は Windows 標準。コンテナ IP 向けは Docker ネットワーク内からが確実

# SNMP
snmpwalk -v2c -c public localhost 1.3.6.1.2.1.1
```

コンテナ内から（セグメント間ルーティング確認）:

```powershell
docker exec -it lab-router ping -c 2 172.30.99.10
docker exec -it lab-router ping -c 2 172.30.10.53
```

Syslog 送信テスト:

```powershell
docker run --rm --network network-lab_segment-mgmt alpine \
  sh -c "apk add -q netcat-openbsd && echo test | nc -u -w1 172.30.99.14 514"
docker exec lab-syslog-main tail /var/log/network-lab/messages.log
```

## 物理 LAN との接続について

このリポジトリは **Docker 内部のマルチセグメント**を再現します。  
実機スイッチ配下の物理セグメントと同一 L2 に載せるには、Docker Desktop の [Macvlan/IPvlan](https://docs.docker.com/network/drivers/macvlan/) や Hyper-V 外部 vSwitch など別途設計が必要です。

運用イメージ:

1. まず本ラボでサービス定義・クライアント検証を行う  
2. 必要に応じて物理 NIC ブリッジや実機への IP 移行を行う  

## ディレクトリ構成

```
docs/起動手順書.md       # 初回セットアップ～起動確認
config/lab.yaml          # 運用設定（gitignore 推奨）
config/lab.yaml.example  # サンプル
scripts/
  generate_compose.py    # lab.yaml → docker-compose.yml
  lab.ps1 / lab.sh       # 起動補助
services/                # 各サービスの Dockerfile
generated/               # DNS/SNMP 等の生成設定（自動）
```

## トラブルシュート

| 現象 | 対処 |
|------|------|
| ポート競合 (53, 67 等) | `publish_ports: false` にするか、`port` を変更 |
| DHCP がホストで起動しない | Windows で 67 は制限されがち。`publish_ports: false` で内部のみ利用 |
| 設定変更が反映されない | `.\scripts\lab.ps1 restart` で compose 再生成 |
| Python がない | `py -3` または python.org からインストール |

## ライセンス

MIT（プロジェクト利用に合わせて変更してください）
