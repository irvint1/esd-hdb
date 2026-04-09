# ESD HDB BTO Portal

Microservices-based HDB BTO application and ballot platform for managing HDB resale transactions.

---

## 🚀 Quick Start

### Prerequisites
- **Docker Desktop** with Compose v2
- **Node.js 18+**
- **Git** (Git Bash on Windows)
- **External Accounts:** NETS, SendGrid, Twilio, RabbitMQ (see [Backend README](./backend/README.md#account-signup--credentials))

### Setup (15 minutes)

```bash
# 1. Backend setup
cd backend
bash scripts/env-setup.sh
# Edit backend/.env with your credentials (NETS, SendGrid, Twilio, RabbitMQ)

# 2. Start backend services
docker compose up --build -d

# 3. Initialize Kong routes
bash scripts/kong-setup.sh

# 4. Frontend setup
cd ../frontend
npm install
npm run dev

# 5. Open browser
http://localhost:5173
```

**[Detailed setup guide →](./backend/README.md)**

---

## 📁 Repository Structure

```
esd-hdb/
├── backend/                          # Backend microservices
│   ├── docker-compose.yml            # Start all services
│   ├── .env.example                  # Configuration template
│   ├── scripts/
│   │   ├── env-setup.sh              # Environment initialization
│   │   └── kong-setup.sh             # Kong API Gateway setup
│   ├── application/                  # Application service
│   ├── apply_bto/                    # BTO application flow
│   ├── ballot/                       # Ballot service
│   ├── flat/                         # Flat inventory
│   ├── flat_selection/               # Flat queue management
│   ├── nets_payment/                 # Payment processing
│   ├── notification/                 # Notifications (email/SMS)
│   └── [other services]/             # Additional microservices
│
├── frontend/                         # Vue 3 + TypeScript application
│   ├── src/
│   │   ├── views/                   # Pages (Login, Application, Admin, etc.)
│   │   ├── components/              # Reusable components
│   │   ├── router/                  # Navigation routes
│   │   ├── stores/                  # State management
│   │   └── api/                     # API client
│   └── package.json
│
└── README.md                         # This file
```

---

## 🎯 Features

### User Features
- **Login:** Singpass-style authentication via MockPass
- **BTO Application:** Fill details → upload documents → process payment
- **Flat Selection:** Browse and select flats from available inventory
- **Eligibility Check:** Real-time eligibility validation
- **Application Tracking:** View application status through pipeline

### Admin Features
- **Ballot Management:** Trigger ballot runs and view results
- **Flat Queue Management:** Assign and manage flat queues
- **Audit Trail:** Track all ballot runs and changes

### System Capabilities
- **Notifications:** Email (SendGrid) and SMS (Twilio)
- **Payment Processing:** NETS credit card integration
- **Document Processing:** PDF upload with OCR
- **Microservices Architecture:** Scalable Flask services with Kong gateway
- **Database:** MySQL with multiple service databases
- **Message Queue:** RabbitMQ for async operations

---

## 📖 Documentation

For complete setup and troubleshooting:
- **[Backend Setup Guide](./backend/README.md)** - Account credentials, Docker details, troubleshooting
- **[Frontend Setup Guide](./frontend/README.md)** - Node.js, development server, build commands
