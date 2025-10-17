
# 🐳 Docker Deployment Guide

Run your entire trading app in Docker containers with one command.

---

## 🚀 Quick Start (30 Seconds)

```bash
# 1. Make sure you have Docker installed
docker --version
docker-compose --version

# 2. Build and start everything
cd /Users/natewier/Projects/trading-app
docker-compose up -d

# 3. Access dashboard
open http://localhost:5000

# That's it! ✅
```

---

## 📦 What Gets Deployed

### Container 1: `trading-app`
- **Purpose**: Main web application
- **Port**: 5000
- **What it does**:
  - Runs Flask dashboard
  - Serves API endpoints
  - Displays trading signals
  - Portfolio management

### Container 2: `data-collector`
- **Purpose**: Automated data collection
- **What it does**:
  - Runs every 24 hours automatically
  - Collects Finnhub + OpenInsider data
  - Generates fresh signals
  - Updates database

### Optional Container 3: `postgres`
- **Purpose**: Production database
- **Port**: 5432
- **What it does**:
  - Replaces SQLite with PostgreSQL
  - Better for concurrent access
  - More scalable

---

## 🛠️ Installation

### Prerequisites
```bash
# Install Docker Desktop (macOS)
# Download from: https://www.docker.com/products/docker-desktop

# Or use Homebrew:
brew install --cask docker

# Verify installation:
docker --version
docker-compose --version
```

### Initial Setup
```bash
cd /Users/natewier/Projects/trading-app

# Make sure .env file exists with your API keys
ls .env

# Build containers (first time only, takes 2-3 minutes)
docker-compose build

# Start everything
docker-compose up -d

# Check status
docker-compose ps
```

---

## 📋 Common Commands

### Start/Stop
```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart everything
docker-compose restart

# Stop without removing containers
docker-compose stop
```

### View Logs
```bash
# View all logs
docker-compose logs

# Follow logs in real-time
docker-compose logs -f

# View specific service logs
docker-compose logs trading-app
docker-compose logs data-collector

# Last 50 lines
docker-compose logs --tail=50 trading-app
```

### Check Status
```bash
# List running containers
docker-compose ps

# Check health
docker ps

# View resource usage
docker stats
```

### Execute Commands Inside Containers
```bash
# Run data collection manually
docker-compose exec trading-app python scripts/run_ingestion.py --source all --days 7

# Generate signals manually
docker-compose exec trading-app python scripts/generate_signals.py --portfolio-value 100000

# Access Python shell
docker-compose exec trading-app python

# Access bash shell
docker-compose exec trading-app bash
```

### Database Management
```bash
# Backup database
docker-compose exec trading-app cp /app/data/trading_app.db /app/data/backup_$(date +%Y%m%d).db

# View database stats
docker-compose exec trading-app python -c "
from src.database import get_session, Trade
with get_session() as session:
    print(f'Total trades: {session.query(Trade).count()}')
"
```

---

## 🔧 Configuration

### Environment Variables

Edit `.env` file before starting:
```bash
# Required
FINNHUB_API_KEY=your_key

# Optional (adds more data)
ALPHA_VANTAGE_API_KEY=your_key
TIINGO_API_KEY=your_key
POLYGON_API_KEY=your_key
# ... etc
```

### Ports

Change ports in `docker-compose.yml`:
```yaml
ports:
  - "8080:5000"  # Run on port 8080 instead of 5000
```

### Resource Limits

Add to `docker-compose.yml` under each service:
```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 1G
    reservations:
      memory: 512M
```

---

## 🌐 Production Deployment

### Deploy to Cloud (AWS, Google Cloud, Azure)

#### 1. Build and push image
```bash
# Tag image
docker build -t your-registry/trading-app:latest .

# Push to registry
docker push your-registry/trading-app:latest
```

#### 2. Deploy on cloud server
```bash
# SSH into server
ssh user@your-server.com

# Pull image
docker pull your-registry/trading-app:latest

# Run with docker-compose
docker-compose up -d
```

### Using PostgreSQL for Production

Uncomment the postgres service in `docker-compose.yml`:
```yaml
postgres:
  image: postgres:15-alpine
  container_name: trading-postgres
  environment:
    POSTGRES_USER: trading_user
    POSTGRES_PASSWORD: change_this_password
    POSTGRES_DB: trading_db
  volumes:
    - postgres_data:/var/lib/postgresql/data
  ports:
    - "5432:5432"
  networks:
    - trading-network
  restart: unless-stopped
```

Then update `.env`:
```bash
DATABASE_URL=postgresql://trading_user:your_password@postgres:5432/trading_db
```

---

## 🔄 Updates and Maintenance

### Update Application Code
```bash
# Pull latest code
git pull origin main

# Rebuild containers
docker-compose build

# Restart with new code
docker-compose up -d
```

### Update Dependencies
```bash
# Edit requirements.txt
nano requirements.txt

# Rebuild
docker-compose build --no-cache

# Restart
docker-compose up -d
```

### Clean Up Old Images
```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Full cleanup
docker system prune -a
```

---

## 📊 Monitoring

### Health Checks

Built-in health checks monitor:
- Flask app responsiveness
- API endpoint availability
- Database connectivity

View health status:
```bash
docker ps

# HEALTHY = Good
# UNHEALTHY = Check logs
```

### View Metrics
```bash
# Real-time resource usage
docker stats

# Detailed container info
docker inspect trading-app
```

### Alerts (Optional)

Set up with monitoring tools:
- **Prometheus**: Container metrics
- **Grafana**: Dashboards
- **Uptime Robot**: External monitoring

---

## 🐛 Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose logs trading-app

# Common issues:
# 1. Port already in use
lsof -i :5000
# Kill process: kill -9 <PID>

# 2. Missing .env file
ls .env

# 3. Database locked
rm data/trading_app.db-shm data/trading_app.db-wal
```

### Data Not Collecting
```bash
# Check data-collector logs
docker-compose logs data-collector

# Run manually to test
docker-compose exec data-collector python scripts/run_ingestion.py --source finnhub --days 1

# Verify API keys
docker-compose exec trading-app printenv | grep API_KEY
```

### Dashboard Not Loading
```bash
# Check if app is running
curl http://localhost:5000/api/stats

# Restart Flask
docker-compose restart trading-app

# Check for errors
docker-compose logs --tail=50 trading-app
```

### Database Issues
```bash
# Backup current database
docker-compose exec trading-app cp /app/data/trading_app.db /app/data/backup.db

# Reset database (WARNING: Deletes all data!)
docker-compose down
rm data/trading_app.db
docker-compose up -d

# Re-collect data
docker-compose exec trading-app python scripts/run_ingestion.py --source all --days 90
```

---

## 🚀 Advanced: Multi-Server Deployment

### Docker Swarm
```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml trading

# Scale services
docker service scale trading_data-collector=3

# View services
docker service ls
```

### Kubernetes
```bash
# Convert docker-compose to k8s
kompose convert

# Deploy to k8s
kubectl apply -f trading-app-deployment.yaml
kubectl apply -f trading-app-service.yaml

# Check status
kubectl get pods
kubectl get services
```

---

## 📦 Backup and Restore

### Backup Everything
```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d)

# Backup database
docker-compose exec trading-app cp /app/data/trading_app.db /app/data/backup.db
cp data/trading_app.db backups/$(date +%Y%m%d)/

# Backup logs
cp -r logs backups/$(date +%Y%m%d)/

# Backup .env
cp .env backups/$(date +%Y%m%d)/
```

### Restore from Backup
```bash
# Stop containers
docker-compose down

# Restore database
cp backups/20251017/trading_app.db data/

# Start containers
docker-compose up -d
```

---

## 🔐 Security Best Practices

### 1. Secure API Keys
```bash
# Never commit .env to Git
echo ".env" >> .gitignore

# Use Docker secrets in production
docker secret create finnhub_key finnhub_key.txt
```

### 2. Network Isolation
```yaml
# In docker-compose.yml
networks:
  trading-network:
    driver: bridge
    internal: true  # Isolate from external
```

### 3. Read-Only Volumes
```yaml
volumes:
  - ./.env:/app/.env:ro  # ro = read-only
```

### 4. Non-Root User
Add to Dockerfile:
```dockerfile
RUN useradd -m -u 1000 trading && chown -R trading:trading /app
USER trading
```

---

## 📊 Performance Optimization

### 1. Use BuildKit
```bash
DOCKER_BUILDKIT=1 docker-compose build
```

### 2. Multi-Stage Builds
```dockerfile
# Builder stage
FROM python:3.11-slim as builder
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Runtime stage
FROM python:3.11-slim
COPY --from=builder /wheels /wheels
RUN pip install --no-cache /wheels/*
```

### 3. Layer Caching
```dockerfile
# Copy requirements first (changes rarely)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy code second (changes often)
COPY . .
```

---

## ✅ Verification Checklist

After deployment:

- [ ] Containers are running (`docker-compose ps`)
- [ ] Dashboard loads (http://localhost:5000)
- [ ] API returns data (`curl http://localhost:5000/api/stats`)
- [ ] Data collector runs (`docker-compose logs data-collector`)
- [ ] Logs are being created (`ls logs/`)
- [ ] Database has data (`docker-compose exec trading-app python -c "from src.database import get_session, Trade; print(get_session().query(Trade).count())"`)
- [ ] Health checks passing (`docker ps` shows HEALTHY)

---

## 🎯 Common Use Cases

### Development
```bash
# Mount code as volume for live reload
docker-compose -f docker-compose.dev.yml up
```

### Testing
```bash
# Run tests in container
docker-compose exec trading-app pytest tests/
```

### Production
```bash
# Use production compose file
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📚 Additional Resources

- **Docker Docs**: https://docs.docker.com/
- **Docker Compose**: https://docs.docker.com/compose/
- **Best Practices**: https://docs.docker.com/develop/dev-best-practices/

---

**Questions?** Check logs with `docker-compose logs -f`

**Working great?** Your app is now containerized and portable! 🐳✨

