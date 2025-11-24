# VPS Setup Guide - Quick Configuration

This guide helps you configure the project to run on your VPS at **51.38.126.98**.

## Quick Setup (3 Steps)

### Step 1: Configure Environment Variables

Create or edit your `.env` file:

```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker
nano .env
```

Add these VPS-specific variables:

```bash
# VPS Configuration
VPS_IP=51.38.126.98
CORS_ORIGINS=http://51.38.126.98:3000,http://51.38.126.98:3001
NEXT_PUBLIC_API_URL=http://51.38.126.98:8000

# Your wallet credentials (REQUIRED)
PK=your_private_key_without_0x
BROWSER_ADDRESS=0xYourWalletAddress

# Database and Redis (already configured for Docker)
DATABASE_URL=postgresql+asyncpg://poly:poly@postgres:5432/poly
REDIS_URL=redis://redis:6379/0

# Application settings
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Step 2: Rebuild Web Container with VPS URL

The web container needs to be rebuilt with the VPS API URL:

```bash
# Set the API URL environment variable
export NEXT_PUBLIC_API_URL=http://51.38.126.98:8000

# Rebuild web container
docker compose build web

# Restart all services
docker compose up -d
```

Or set it in your `.env` file and rebuild:

```bash
docker compose build --build-arg NEXT_PUBLIC_API_URL=http://51.38.126.98:8000 web
docker compose up -d
```

### Step 3: Verify Configuration

```bash
# Check services are running
docker compose ps

# Check backend logs for CORS configuration
docker compose logs backend | grep -i cors

# Test API accessibility
curl http://localhost:8000/health/

# Test from external (if firewall allows)
curl http://51.38.126.98:8000/health/
```

## Access Your Services

After setup, access your services at:

- **Dashboard**: http://51.38.126.98:3000
- **API Docs**: http://51.38.126.98:8000/docs
- **Health Check**: http://51.38.126.98:8000/health/
- **Grafana**: http://51.38.126.98:3001
- **Prometheus**: http://51.38.126.98:9090

## Firewall Configuration

Make sure your VPS firewall allows these ports:

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 3000/tcp  # Web dashboard
sudo ufw allow 8000/tcp  # API
sudo ufw allow 3001/tcp  # Grafana
sudo ufw allow 9090/tcp  # Prometheus

# Or allow all if needed
sudo ufw allow 3000:9090/tcp
```

## CORS Configuration

The backend automatically adds VPS origins when `VPS_IP` is set in `.env`. 

You can also manually specify CORS origins:

```bash
# In .env file
CORS_ORIGINS=http://51.38.126.98:3000,http://51.38.126.98:3001,http://yourdomain.com
```

## Troubleshooting

### CORS Errors

If you see CORS errors in the browser console:

1. **Check VPS_IP is set**:
   ```bash
   grep VPS_IP .env
   ```

2. **Check backend logs**:
   ```bash
   docker compose logs backend | grep -i cors
   ```

3. **Restart backend**:
   ```bash
   docker compose restart backend
   ```

### Frontend Can't Connect to API

1. **Check API URL**:
   - Verify `NEXT_PUBLIC_API_URL` in `.env`
   - Rebuild web container after changing it

2. **Check API is accessible**:
   ```bash
   curl http://51.38.126.98:8000/health/
   ```

3. **Check firewall**:
   ```bash
   sudo ufw status
   ```

### Services Not Starting

1. **Check logs**:
   ```bash
   docker compose logs
   ```

2. **Check ports are available**:
   ```bash
   sudo netstat -tulpn | grep -E '3000|8000|3001|9090'
   ```

3. **Restart services**:
   ```bash
   docker compose down
   docker compose up -d
   ```

## Quick Reference

```bash
# Set VPS IP in .env
echo "VPS_IP=51.38.126.98" >> .env
echo "CORS_ORIGINS=http://51.38.126.98:3000,http://51.38.126.98:3001" >> .env
echo "NEXT_PUBLIC_API_URL=http://51.38.126.98:8000" >> .env

# Rebuild and restart
docker compose build web
docker compose up -d

# Verify
curl http://51.38.126.98:8000/health/
```

---

**That's it!** Your project should now be accessible at http://51.38.126.98:3000

