# Production VPS Deployment Guide — Astrology WhatsApp Platform

This guide provides an end-to-end, production-grade deployment runbook for hosting the Astrology WhatsApp AI Platform on an Ubuntu LTS Virtual Private Server (VPS) with Docker, PostgreSQL (`pgvector`), and Nginx reverse proxy with Let's Encrypt TLS.

---

## 1. Recommended Architecture & Hardware Specifications

```
                       Internet
                          │
                          ▼
            [ UFW Firewall: 22, 80, 443 ]
                          │
                          ▼
                 [ Nginx Reverse Proxy ]
               (Port 80/443, Let's Encrypt SSL)
                          │
            ┌─────────────┴─────────────┐
            │ Proxy: 127.0.0.1:8000     │
            ▼                           ▼
    [ FastAPI API Container ]   [ Static Admin Assets ]
      (Port 8000, Non-Root)        (/admin/assets/*)
            │
            │ Internal Docker Network (astrology_internal_net)
            ▼
    [ PostgreSQL 16 + pgvector ]
       (Volume: postgres_data)
     (No Host Port Exposure)
```

### VPS Sizing Specifications

| Component | Minimum Specification | Recommended Specification |
|---|---|---|
| **Operating System** | Ubuntu 22.04 / 24.04 LTS (64-bit) | Ubuntu 24.04 LTS (x86_64) |
| **CPU** | 1 vCPU | 2 vCPUs |
| **RAM** | 2 GB | 4 GB |
| **Storage** | 25 GB NVMe / SSD | 50 GB NVMe / SSD |
| **Network** | 1 Gbps port, static IPv4 | Static IPv4, DDoS protection |

---

## 2. DNS Configuration (Prerequisite)

Before deploying SSL certificates, configure your domain's DNS records at your domain registrar:

| Type | Host / Name | Value / Destination | TTL |
|---|---|---|---|
| **A** | `astrology` (or `@` for root) | `<YOUR_VPS_PUBLIC_IP>` | 300 / 1 hour |

Verify propagation from your local terminal before proceeding:
```bash
dig +short astrology.yourdomain.com
# Should return your VPS Public IP
```

---

## 3. Server Provisioning & Initial Hardening

Connect to your VPS via SSH as `root`:
```bash
ssh root@<YOUR_VPS_PUBLIC_IP>
```

### Step 3.1: Update Packages & Create Non-Root Deployer
```bash
apt update && apt upgrade -y
apt install -y curl ufw git htop fail2ban certbot python3-certbot-nginx

# Create deployer user
adduser deployer
usermod -aG sudo deployer

# Copy authorized SSH keys from root to deployer
mkdir -p /home/deployer/.ssh
cp /root/.ssh/authorized_keys /home/deployer/.ssh/
chown -R deployer:deployer /home/deployer/.ssh
chmod 700 /home/deployer/.ssh
chmod 600 /home/deployer/.ssh/authorized_keys
```

### Step 3.2: Configure UFW Firewall
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose
```

---

## 4. Install Docker Engine & Docker Compose

Log in as `deployer`:
```bash
su - deployer
```

Install official Docker repository:
```bash
# Add Docker's official GPG key:
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update

# Install Docker packages:
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow deployer user to manage Docker without sudo:
sudo usermod -aG docker deployer
newgrp docker
docker --version
docker compose version
```

---

## 5. Clone Repository & Setup Environment

```bash
sudo mkdir -p /opt/astrology
sudo chown -R deployer:deployer /opt/astrology
cd /opt/astrology

# Clone your repository
git clone https://github.com/Manish-10275/astrology-whatsapp.git .
git checkout main
```

### Step 5.1: Generate Production Environment Secrets
Create `.env` from template:
```bash
cp .env.example .env
chmod 600 .env
```

Generate production secrets securely:
```bash
# 1. Database Password:
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"

# 2. Field-Level AES-256-GCM Key (64 hex characters):
python3 -c "import secrets; print('ENCRYPTION_PRIMARY_KEY=' + secrets.token_hex(32))"

# 3. Phone Hash Salt:
python3 -c "import secrets; print('PHONE_HASH_SALT=' + secrets.token_hex(32))"

# 4. JWT Signing Key:
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))"

# 5. Dedicated Scheduler Secret:
python3 -c "import secrets; print('SCHEDULER_SECRET_TOKEN=' + secrets.token_hex(32))"
```

Edit `/opt/astrology/.env` and paste these generated values:
```bash
nano .env
```
Ensure:
- `ENVIRONMENT=production`
- `POSTGRES_PASSWORD` matches the generated password.
- `ENCRYPTION_PRIMARY_KEY` is recorded securely (cannot be changed once data is stored).
- OpenAI and WhatsApp variables can remain empty for now (safe fallback is active).

---

## 6. Obtain Let's Encrypt SSL Certificate

Stop any running process on port 80 and request the certificate:
```bash
sudo certbot certonly --standalone \
  -d astrology.yourdomain.com \
  --agree-tos \
  --email your-admin-email@yourdomain.com \
  --non-interactive
```

Verify certificate issuance:
```bash
sudo ls -l /etc/letsencrypt/live/astrology.yourdomain.com/
# Should contain fullchain.pem and privkey.pem
```

---

## 7. Configure Nginx Reverse Proxy

### Step 7.1: Install & Deploy Nginx Site Configuration
```bash
sudo apt install -y nginx

# Copy configuration template
sudo cp /opt/astrology/deploy/nginx/astrology.conf /etc/nginx/sites-available/astrology.conf

# Replace placeholder with your real domain:
sudo sed -i 's/astrology.yourdomain.com/YOUR_REAL_DOMAIN.COM/g' /etc/nginx/sites-available/astrology.conf

# Enable site and disable default site
sudo ln -sf /etc/nginx/sites-available/astrology.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration syntax
sudo nginx -t
sudo systemctl enable --now nginx
```

---

## 8. Build Image, Initialize Database & Apply Migrations

### Step 8.1: Build Application Image
```bash
cd /opt/astrology
docker compose build
```

### Step 8.2: Start PostgreSQL Container
```bash
docker compose up -d db

# Wait until database is healthy:
docker compose ps
# Ensure astrology_postgres shows (healthy)
```

### Step 8.3: Run Database Migrations
Run Alembic migrations inside the container:
```bash
docker compose run --rm --no-deps api python -m alembic upgrade head
```
Expected output:
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> fda0947e6030, initial_schema
INFO  [alembic.runtime.migration] Running upgrade fda0947e6030 -> 2c5e3354b756, add_conversations_and_messages
INFO  [alembic.runtime.migration] Running upgrade 2c5e3354b756 -> 4a7b9c1d2e3f, add_horoscope_scheduling_preferences
INFO  [alembic.runtime.migration] Running upgrade 4a7b9c1d2e3f -> 7e2c9a4b6d10, add_astrology_knowledge_rag
```

### Step 8.4: Provision Initial Super Administrator Account
```bash
docker compose run --rm api python deploy/scripts/seed_admin.py
```
Follow the interactive prompts to enter:
- Admin Username
- Admin Email
- Admin Password (minimum 12 characters, hashed with Argon2id)

---

## 9. Launch Application & Verify Services

```bash
# Start all containers in background:
docker compose up -d

# Verify container statuses:
docker compose ps
```

### Step 9.1: Health Check Verification
```bash
# 1. Liveness probe:
curl -i http://127.0.0.1:8000/health/live
# Expected: HTTP/1.1 200 OK -> {"status":"live"}

# 2. Readiness probe (checks DB connectivity):
curl -i http://127.0.0.1:8000/health/ready
# Expected: HTTP/1.1 200 OK -> {"status":"ready","database":"connected"}

# 3. Public HTTPS check:
curl -i https://YOUR_REAL_DOMAIN.COM/health/ready
```

### Step 9.2: Verify Admin Dashboard Access
Open your web browser and navigate to:
```
https://YOUR_REAL_DOMAIN.COM/admin
```
- Sign in with the super administrator credentials created in Step 8.4.
- Verify all 7 sections (Overview, Users, Conversations, Horoscopes, Compatibility, Diagnostics, Settings) render cleanly.

---

## 10. Automated Nightly Database Backups

Create a dedicated backup directory and schedule automated nightly backups:
```bash
sudo mkdir -p /var/backups/astrology
sudo chown deployer:deployer /var/backups/astrology

chmod +x /opt/astrology/deploy/scripts/backup-db.sh
chmod +x /opt/astrology/deploy/scripts/restore-db.sh

# Test a backup immediately:
/opt/astrology/deploy/scripts/backup-db.sh
ls -lh /var/backups/astrology/
```

Add a daily cron job (runs every day at 02:00 AM UTC):
```bash
crontab -e
```
Add line:
```cron
0 2 * * * /opt/astrology/deploy/scripts/backup-db.sh >> /var/log/astrology-backup.log 2>&1
```

---

## 11. Upgrades & Rollback Procedures

### Standard Application Upgrade Procedure
```bash
cd /opt/astrology

# 1. Fetch latest verified commit from main
git fetch origin
git checkout main
git pull origin main

# 2. Rebuild container image
docker compose build api

# 3. Run pending database migrations
docker compose run --rm --no-deps api python -m alembic upgrade head

# 4. Restart container with zero/minimal downtime
docker compose up -d --no-deps api

# 5. Verify system health
curl -f http://127.0.0.1:8000/health/ready
```

### Emergency Rollback Procedure
If a defect is detected post-deployment:
```bash
cd /opt/astrology

# 1. Revert Git commit to previous stable release
git checkout <PREVIOUS_STABLE_COMMIT_HASH>

# 2. (If needed) Downgrade database schema by 1 revision
docker compose run --rm --no-deps api python -m alembic downgrade -1

# 3. Rebuild and restart API container
docker compose build api
docker compose up -d --no-deps api

# 4. (If database data corruption occurred) Restore from last night's backup
/opt/astrology/deploy/scripts/restore-db.sh /var/backups/astrology/astrology_YYYYMMDD_HHMMSS.sql.gz
```
