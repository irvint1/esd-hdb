#!/bin/bash

# Setup environment file for backend services
# This script copies .env.example to .env if it doesn't exist

if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env from .env.example"
    echo ""
    echo "⚠️  NEXT STEP: Update .env with your credentials:"
    echo "   Edit backend/.env and fill in these required values:"
    echo "     - NETS_API_KEY_ID"
    echo "     - NETS_SECRET_KEY"
    echo "     - NETS_MID"
    echo "     - NETS_S2S_CALLBACK_URL"
    echo ""
    echo "   Then run: docker-compose up --build -d"
else
    echo "✅ .env already exists"
fi
