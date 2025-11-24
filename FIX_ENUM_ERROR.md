# Fix Database Enum Error

## Problem

The error `column "status" is of type bot_run_status but expression is of type character varying` occurs because:

1. **Database**: Has `bot_run.status` as PostgreSQL ENUM type (`bot_run_status`)
2. **Code**: Model uses `String(32)` type
3. **Mismatch**: Code tries to insert string `'running'` but database expects enum value

## Solution

A migration has been created to change the column from enum to VARCHAR.

### Step 1: Run Migration

**On your VPS, run:**

```bash
# Navigate to project directory
cd ~/poly-maker/polymarketing-trading-final

# Run the migration
docker compose exec backend uv run alembic upgrade head
```

This will:
1. Convert `bot_run.status` from enum to VARCHAR(32)
2. Drop the unused enum type
3. Keep existing data (all enum values become strings)

### Step 2: Verify Migration

```bash
# Check column type changed
docker compose exec postgres psql -U poly -d poly -c \
  "\d bot_run" | grep status

# Should show: status | character varying(32) | not null | default: 'running'::character varying
```

### Step 3: Test Endpoint

```bash
# Test bot start endpoint
curl -X POST http://localhost:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start \
     -H "Content-Type: application/json" \
     -d '{}'
```

Should return success response without enum error.

## Alternative: Quick SQL Fix (If Migration Fails)

If migration has issues, you can manually fix:

```bash
# Connect to database
docker compose exec postgres psql -U poly -d poly

# Run SQL commands:
ALTER TABLE bot_run ALTER COLUMN status TYPE VARCHAR(32) USING status::text;
DROP TYPE IF EXISTS bot_run_status;

# Exit
\q
```

## Verification

After migration, check:

1. **Column type is VARCHAR:**
   ```bash
   docker compose exec postgres psql -U poly -d poly -c \
     "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'bot_run' AND column_name = 'status';"
   ```

2. **Existing data preserved:**
   ```bash
   docker compose exec postgres psql -U poly -d poly -c \
     "SELECT id, status FROM bot_run LIMIT 5;"
   ```

3. **Endpoint works:**
   ```bash
   curl -X POST http://localhost:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start \
        -H "Content-Type: application/json" \
        -d '{}'
   ```

## What Changed

- **Migration file**: `alembic/versions/20241120_0002_change_bot_run_status_to_varchar.py`
- **Converts**: `bot_run.status` from enum to VARCHAR(32)
- **Preserves**: All existing data
- **Removes**: Unused `bot_run_status` enum type

Run the migration and the error will be fixed!

