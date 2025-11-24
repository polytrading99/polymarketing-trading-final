# VPS Configuration Summary

## Changes Made for VPS Deployment (51.38.126.98)

### ✅ Files Updated

1. **`app/api/main.py`**
   - Added VPS IP support in CORS configuration
   - Automatically adds VPS origins when `VPS_IP` environment variable is set
   - Added port 8000 to VPS origins for API access

2. **`docker-compose.yml`**
   - Added default VPS_IP: `51.38.126.98`
   - Added default CORS_ORIGINS for VPS
   - Updated web service to use `NEXT_PUBLIC_API_URL` from environment

3. **`docker/web.Dockerfile`**
   - Already supports `NEXT_PUBLIC_API_URL` build argument
   - Can be set via environment variable or build arg

### ✅ New Files Created

1. **`setup_vps.sh`**
   - Automated VPS setup script
   - Configures .env file with VPS settings
   - Rebuilds web container with correct API URL
   - Restarts all services

2. **`VPS_SETUP.md`**
   - Complete VPS deployment guide
   - Step-by-step instructions
   - Troubleshooting guide

## Quick Start on VPS

### Option 1: Use Setup Script (Recommended)

```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker
./setup_vps.sh
```

This will:
- Configure `.env` with VPS settings
- Rebuild web container
- Restart all services

### Option 2: Manual Setup

1. **Edit `.env` file**:
```bash
VPS_IP=51.38.126.98
CORS_ORIGINS=http://51.38.126.98:3000,http://51.38.126.98:3001
NEXT_PUBLIC_API_URL=http://51.38.126.98:8000
```

2. **Rebuild web container**:
```bash
docker compose build --build-arg NEXT_PUBLIC_API_URL=http://51.38.126.98:8000 web
```

3. **Restart services**:
```bash
docker compose up -d
```

## Environment Variables for VPS

Add these to your `.env` file:

```bash
# VPS Configuration
VPS_IP=51.38.126.98
CORS_ORIGINS=http://51.38.126.98:3000,http://51.38.126.98:3001
NEXT_PUBLIC_API_URL=http://51.38.126.98:8000

# Your wallet (REQUIRED)
PK=your_private_key
BROWSER_ADDRESS=0xYourWalletAddress

# Database (default)
DATABASE_URL=postgresql+asyncpg://poly:poly@postgres:5432/poly
REDIS_URL=redis://redis:6379/0
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Access Points

After setup, access at:

- **Dashboard**: http://51.38.126.98:3000
- **API**: http://51.38.126.98:8000
- **API Docs**: http://51.38.126.98:8000/docs
- **Grafana**: http://51.38.126.98:3001
- **Prometheus**: http://51.38.126.98:9090

## Firewall Configuration

Make sure these ports are open:

```bash
sudo ufw allow 3000/tcp  # Dashboard
sudo ufw allow 8000/tcp  # API
sudo ufw allow 3001/tcp  # Grafana
sudo ufw allow 9090/tcp  # Prometheus
```

## Verification

```bash
# Check services
docker compose ps

# Test API
curl http://51.38.126.98:8000/health/

# Check CORS in backend logs
docker compose logs backend | grep -i cors
```

## What Changed

### CORS Configuration
- Backend now automatically includes VPS IP in allowed origins
- Can be overridden with `CORS_ORIGINS` environment variable
- Supports both localhost and VPS IP access

### Frontend API URL
- Web container now uses VPS IP for API calls
- Set via `NEXT_PUBLIC_API_URL` environment variable
- Rebuild required after changing

### Default Values
- `docker-compose.yml` now has VPS IP as default
- Can be overridden in `.env` file
- Makes deployment easier

---

**Status**: ✅ Ready for VPS deployment at 51.38.126.98

