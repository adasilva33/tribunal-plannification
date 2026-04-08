# Deployment Guide — Tribunal Planning

## What you need
- A VPS — Hetzner CX22 (~4 €/month) or DigitalOcean Droplet (~6 $/month)
- OS: **Ubuntu 24.04**
- A domain name (optional, e.g. `planning.votretribunal.fr`)

---

## Step 1 — Create the VPS

Sign up at Hetzner or DigitalOcean, create the smallest Ubuntu 24.04 server,
and add your SSH public key during setup.

---

## Step 2 — Connect and install dependencies

```bash
ssh root@<YOUR_SERVER_IP>

apt update && apt upgrade -y
apt install -y python3-pip python3-venv nginx git
```

---

## Step 3 — Deploy the app

```bash
# Create a dedicated user (safer than root)
adduser tribunal
su - tribunal

# Upload your files (from your Mac, run this outside the SSH session):
#   scp -r /Users/dasilvaa/Documents/coding/tribunal_plannification tribunal@<IP>:~/
# OR clone from git if you push the repo:
#   git clone https://github.com/YOUR_USERNAME/tribunal_plannification.git

cd tribunal_plannification

# Virtual environment + dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# Initialize the database (Ctrl+C after it starts)
python app.py
```

---

## Step 4 — Set a production SECRET_KEY

In `app.py` line ~19, replace the secret key with a long random string.

Generate one on the server:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Then edit `app.py`:
```python
app.config['SECRET_KEY'] = '<paste the generated value here>'
```

---

## Step 5 — Create a systemd service (auto-start on reboot)

Exit back to root (`exit`), then:

```bash
nano /etc/systemd/system/tribunal.service
```

Paste:
```ini
[Unit]
Description=Tribunal Planning Flask App
After=network.target

[Service]
User=tribunal
WorkingDirectory=/home/tribunal/tribunal_plannification
Environment="PATH=/home/tribunal/tribunal_plannification/venv/bin"
ExecStart=/home/tribunal/tribunal_plannification/venv/bin/gunicorn -w 2 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable tribunal
systemctl start tribunal
systemctl status tribunal   # should show "active (running)"
```

---

## Step 6 — Configure Nginx

```bash
nano /etc/nginx/sites-available/tribunal
```

Paste (replace `YOUR_DOMAIN_OR_IP`):
```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/tribunal /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

The app is now live at `http://YOUR_SERVER_IP`.

---

## Step 7 — HTTPS with Let's Encrypt (free, takes 1 minute)

Only if you have a domain pointed at the server IP:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d YOUR_DOMAIN.fr
```

The certificate auto-renews.

---

## Step 8 — Firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

---

## Step 9 — After going live

1. Log in as `admin@tribunal.fr` / `admin123`
2. Go to **Configuration → Juges → Administrateur** and change the password
3. Set up a daily database backup (run as root):

```bash
crontab -e
# Add this line:
0 3 * * * cp /home/tribunal/tribunal_plannification/instance/tribunal.db /home/tribunal/tribunal_plannification/instance/tribunal.db.bak
```

---

## Useful commands (maintenance)

```bash
# Restart the app after code changes
systemctl restart tribunal

# View app logs
journalctl -u tribunal -f

# Upload updated files from your Mac
scp -r /Users/dasilvaa/Documents/coding/tribunal_plannification/* tribunal@<IP>:~/tribunal_plannification/
```

---

## Default credentials (change after first login!)

| Field    | Value               |
|----------|---------------------|
| Email    | admin@tribunal.fr   |
| Password | admin123            |
