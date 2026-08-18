#!/usr/bin/env python3
"""
Quantum Flex — Database Partition Migration
============================================
Migrates memory_logs, sentinel_ledger, and telemetry_log to partitioned tables.
"""

import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv(Path(__file__).resolve().parent / ".env")

DB_CONFIG = {
    "dbname": "telemetry",
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "host": os.environ["DB_HOST"],
    "port": os.environ["DB_PORT"],
}

def migrate_table(cur, table_name, schema_creation_sql):
    print(f"Migrating {table_name}...")
    
    # 1. Rename existing table
    cur.execute(f"ALTER TABLE IF EXISTS {table_name} RENAME TO {table_name}_old")
    
    # 2. Create the partitioned table
    cur.execute(schema_creation_sql)
    
    # 3. Create partitions for the past week, today, and next 2 days
    now = datetime.now()
    for i in range(-7, 3):
        dt = now + timedelta(days=i)
        start_ts = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end_ts = start_ts + timedelta(days=1)
        suffix = start_ts.strftime("%Y_%m_%d")
        
        start_str = start_ts.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_ts.strftime("%Y-%m-%d %H:%M:%S")
        
        cur.execute(f"CREATE TABLE IF NOT EXISTS {table_name}_p{suffix} PARTITION OF {table_name} FOR VALUES FROM ('{start_str}') TO ('{end_str}')")
        
    # 4. Migrate data
    cur.execute(f"INSERT INTO {table_name} SELECT * FROM {table_name}_old")
    print(f"Migration for {table_name} complete.")


def run_migration():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # memory_logs schema
        # We assume it has id (serial), agent_id, action_taken, outcome, timestamp
        # The primary key must include the partition key (timestamp)
        mem_schema = """
        CREATE TABLE memory_logs (
            id SERIAL,
            agent_id VARCHAR(255),
            action_taken TEXT,
            outcome TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, timestamp)
        ) PARTITION BY RANGE (timestamp);
        """
        
        # sentinel_ledger schema
        sent_schema = """
        CREATE TABLE sentinel_ledger (
            id SERIAL,
            cpu_usage FLOAT,
            mem_usage FLOAT,
            io_wait FLOAT,
            hash_penalty FLOAT,
            drive_score FLOAT,
            status VARCHAR(50),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, timestamp)
        ) PARTITION BY RANGE (timestamp);
        """
        
        # telemetry_log schema (if it exists)
        tel_schema = """
        CREATE TABLE telemetry_log (
            id SERIAL,
            node_id VARCHAR(255),
            cpu FLOAT,
            ram FLOAT,
            io FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, timestamp)
        ) PARTITION BY RANGE (timestamp);
        """
        
        tables = [
            ("memory_logs", mem_schema),
            ("sentinel_ledger", sent_schema)
        ]
        
        for name, sql in tables:
            try:
                migrate_table(cur, name, sql)
            except Exception as e:
                print(f"Skipping/Failed migration for {name}: {e}")
                conn.rollback()
                continue
                
        try:
            migrate_table(cur, "telemetry_log", tel_schema)
        except Exception:
            print("telemetry_log not found or failed, skipping.")
            conn.rollback()

        conn.commit()
        cur.close()
        conn.close()
        print("All migrations completed.")
        
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    run_migration()
