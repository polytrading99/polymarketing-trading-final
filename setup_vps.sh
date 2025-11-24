#!/bin/bash
# VPS Setup Script for Poly-Maker
# This script configures the project for VPS deployment

VPS_IP="51.38.126.98"

echo "=== VPS Setup for Poly-Maker ==="
echo "VPS IP: $VPS_IP"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cat > .env << EOF
# VPS Configuration
VPS_IP=$VPS_IP
CORS_ORIGINS=http://$VPS_IP:3000,http://$VPS_IP:3001
NEXT_PUBLIC_API_URL=http://$VPS_IP:8000

# Wallet Configuration (REQUIRED - Update these!)
PK=your_private_key_here
BROWSER_ADDRESS=0xYourWalletAddress

# Database and Redis
DATABASE_URL=postgresql+asyncpg://poly:poly@postgres:5432/poly
REDIS_URL=redis://redis:6379/0

# Application Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF
    echo "✅ Created .env file. Please edit it and add your wallet credentials!"
    echo ""
else
    echo "✅ .env file exists"
    
    # Update VPS configuration in .env
    if grep -q "VPS_IP=" .env; then
        sed -i "s|VPS_IP=.*|VPS_IP=$VPS_IP|" .env
    else
        echo "VPS_IP=$VPS_IP" >> .env
    fi
    
    if grep -q "CORS_ORIGINS=" .env; then
        sed -i "s|CORS_ORIGINS=.*|CORS_ORIGINS=http://$VPS_IP:3000,http://$VPS_IP:3001|" .env
    else
        echo "CORS_ORIGINS=http://$VPS_IP:3000,http://$VPS_IP:3001" >> .env
    fi
    
    if grep -q "NEXT_PUBLIC_API_URL=" .env; then
        sed -i "s|NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://$VPS_IP:8000|" .env
    else
        echo "NEXT_PUBLIC_API_URL=http://$VPS_IP:8000" >> .env
    fi
    
    echo "✅ Updated VPS configuration in .env"
fi

echo ""
echo "=== Rebuilding Web Container ==="
echo "Building web container with VPS API URL..."

# Rebuild web container with VPS API URL
docker compose build --build-arg NEXT_PUBLIC_API_URL=http://$VPS_IP:8000 web

echo ""
echo "=== Restarting Services ==="
docker compose up -d

echo ""
echo "=== Verification ==="
echo "Waiting 5 seconds for services to start..."
sleep 5

# Check services
echo ""
echo "Service Status:"
docker compose ps

echo ""
echo "Testing API health endpoint..."
curl -s http://localhost:8000/health/ || echo "⚠️  API not responding yet"

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Access your services at:"
echo "  Dashboard:  http://$VPS_IP:3000"
echo "  API Docs:   http://$VPS_IP:8000/docs"
echo "  Health:     http://$VPS_IP:8000/health/"
echo "  Grafana:    http://$VPS_IP:3001"
echo ""
echo "⚠️  Don't forget to:"
echo "  1. Edit .env and add your PK and BROWSER_ADDRESS"
echo "  2. Configure firewall to allow ports 3000, 8000, 3001, 9090"
echo "  3. Restart services after updating .env: docker compose restart"
echo ""

