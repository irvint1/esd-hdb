# Multi-Machine Flat Allocation Setup

If you are running the Flat Allocation service on a different machine (Machine B), and this machine (Machine A) needs to connect to it, follow these steps:

1. **On Machine B (the one running Flat Allocation):**
    - Unzip this folder anywhere on Machine B.
    - Open CMD and run:
       ```
       ipconfig
       ```
    - Look for `IPv4 Address` under the active WiFi adapter. It will look like `10.43.13.132` or `192.168.1.45`. Write it down — you'll give this to Machine A.
    - Start Docker in the backend folder:
       ```
       docker compose up --build -d
       ```
    - Wait for all containers to start (about 1–2 minutes).
    - Run:
       ```
       docker compose ps
       ```
    - All services should show `Up` or `healthy`.

2. **On Machine A (this machine):**
    - Open `backend/.env` in any text editor.
    - Find this line:
       ```
       FLAT_ALLOCATION_URL=http://<OLD_IP>:5016
       ```
    - Replace `<OLD_IP>` with the IPv4 address of Machine B from above, e.g.:
       ```
       FLAT_ALLOCATION_URL=http://10.43.13.132:5016
       ```

Now, Machine A will connect to the Flat Allocation service running on Machine B.

---
# Backend Setup Guide

Complete step-by-step guide to set up and run the ESD HDB backend services from scratch.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Account Signup & Credentials](#account-signup--credentials)
- [Step 1: Configure Environment](#step-1-configure-environment)
- [Step 2: Start Services](#step-2-start-services)
- [Step 3: Initialize Kong](#step-3-initialize-kong)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before starting, ensure you have:
- **Docker Desktop** (with Docker Compose v2) - [Download](https://www.docker.com/products/docker-desktop)
- **Git** - [Download](https://git-scm.com/)
- **Git Bash** (Windows users) or WSL for running scripts
- **Python 3.8+** (for manual testing/debugging)

### Verify Installation
```bash
docker --version
docker compose version
git --version
```

---

## Account Signup & Credentials

⚠️ **You MUST create these accounts before running the backend:**

- [ ] **NETS** - Payment processing
- [ ] **SendGrid** - Email notifications  
- [ ] **Twilio** - SMS notifications
- [ ] **CloudAMQP** - Message queue

### 1. **NETS Payment Gateway** (Required for payment processing)

**Purpose:** Process credit card payments for BTO applications

**Steps:**
1. Go to [NETS Developer Portal](https://developer.nets.com.sg/)
2. Sign up for a developer account
3. Create a new app/project
4. Generate API credentials:
   - **API Key ID** → `NETS_API_KEY_ID`
   - **Secret Key** → `NETS_SECRET_KEY`
   - **Merchant ID (UMID)** → `NETS_MID`
5. Set environment to **UAT** for testing
6. Configure callback URLs in NETS dashboard:
   - **Server-to-Server (S2S):** `https://webhook.site/your-unique-url`
   - **Browser-to-Server (B2S):** `http://localhost:5003/payment/b2s-callback`

---

### 2. **SendGrid** (Required for email notifications)

**Purpose:** Send eligibility and notification emails to applicants

**Steps:**
1. Sign up at [SendGrid](https://sendgrid.com/)
2. Go to **Settings** → **API Keys**
3. Create a new API key (Full Access)
4. Copy the key → `SENDGRID_API_KEY`
5. Go to **Settings** → **Sender Authentication**
6. Verify a sender email → `SENDGRID_FROM_EMAIL`
7. Test by sending an email to `ADMIN_ALERT_EMAIL`

---

### 3. **Twilio** (Required for SMS notifications)

**Purpose:** Send SMS notifications to applicants

**Steps:**
1. Sign up at [Twilio](https://www.twilio.com/)
2. Create a new project
3. Go to **Account** → **API Keys & Tokens**
4. Copy:
   - **Account SID** → `TWILIO_ACCOUNT_SID`
   - **Auth Token** → `TWILIO_AUTH_TOKEN`
5. Go to **Phone Numbers** → **Manage Numbers**
6. Get your Twilio phone number → `TWILIO_FROM_NUMBER`
7. **⚠️ Trial account limitation:** You can only send SMS to verified phone numbers
   - Add verified phone numbers in the Twilio console first

---

### 4. **CloudAMQP** (Required for message queue)

**Sign up at [CloudAMQP](https://www.cloudamqp.com/)**
1. Create a free account
2. Create a new instance
3. Go to **Details**
4. Copy your connection details:
   - **Host** → `RABBITMQ_HOST`
   - **Port** → `RABBITMQ_PORT`
   - **Username** → `RABBITMQ_USERNAME`
   - **Password** → `RABBITMQ_PASSWORD`
   - **Vhost** → `RABBITMQ_VHOST`

---

## Step 1: Configure Environment

### Create .env file from template

```bash
cd backend
bash scripts/env-setup.sh
```

### Edit .env with testing credentials

**Open `backend/.env` and fill in with the provided testing credentials:**

```env
# ============================================
# NETS Payment (Testing Credentials)
# ============================================
NETS_API_KEY_ID=154eb31c-0f72-45bb-9249-84a1036fd1ca
NETS_SECRET_KEY=38a4b473-0295-439d-92e1-ad26a8c60279
NETS_MID=UMID_877772003
NETS_ENVIRONMENT=uat
NETS_CALLBACK_BASE=http://localhost:5003
NETS_S2S_CALLBACK_URL=https://webhook.site/your-unique-url
NETS_IP_ADDRESS=127.0.0.1
NETS_MERCHANT_TIMEZONE=+8:00
NETS_PAYMENT_MODE=CC
HDB_PORTAL_URL=http://localhost:5173

# ============================================
# SendGrid (Email) - Fill in your credentials
# ============================================
SENDGRID_API_KEY=SG.your-key
SENDGRID_FROM_EMAIL=noreply@example.com
ADMIN_ALERT_EMAIL=admin@example.com

# ============================================
# Twilio (SMS) - Fill in your credentials
# ============================================
TWILIO_ACCOUNT_SID=ACxxxxxx
TWILIO_AUTH_TOKEN=your-token
TWILIO_FROM_NUMBER=+1234567890
ADMIN_ALERT_MOBILE=+6591234567

# ============================================
# RabbitMQ - Fill in your credentials
# ============================================
RABBITMQ_HOST=your-rabbitmq-host
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=your-username
RABBITMQ_PASSWORD=your-password
RABBITMQ_VHOST=your-vhost
NOTIFICATION_QUEUE_NAME=hdb_notification_queue

# ============================================
# Database (Defaults)
# ============================================
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_ROOT_PASSWORD=root
```

---

## Step 2: Start Services

### Start all containers

```bash
# From backend/ directory
docker compose up --build -d
```

### Wait for services to be healthy

```bash
# Check status
docker compose ps

## Step 3: Initialize Kong

Kong needs to be configured with routes and plugins before the frontend can make API calls.

```bash
# From backend/ directory
bash scripts/kong-setup.sh
```

### Expected output:
```
Kong is ready.
==> Scenario 1: Apply for BTO
  Registering service: apply-bto...
  Registering route: /apply-bto/initiate...
...
==> Applying plugins
  Plugin: global cors
  Plugin: rate-limiting on apply-bto
  ...
==> Kong setup complete. Registered services and routes:
  Login entrypoint is: http://localhost:8000/singpass/auth/login
```
