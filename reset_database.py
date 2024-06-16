import asyncio
import sqlite3
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler

def reset_database():
    conn = sqlite3.connect('rides.db')
    c = conn.cursor()
    
    # Drop existing tables if they exist
    c.execute('DROP TABLE IF EXISTS ride_requests')
    
    # Recreate the table
    c.execute('''
        CREATE TABLE ride_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            location TEXT NOT NULL,
            destination TEXT NOT NULL,
            time TEXT NOT NULL,
            purpose TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database reset successfully.")

async def reset_database_daily():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(reset_database, 'cron', hour=0, minute=0)
    scheduler.start()
    
    print("Database reset scheduled daily after midnight.")
    
    # Keep the scheduler running in the background
    try:
        while True:
            await asyncio.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        print("Stopping the scheduler.")
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(reset_database_daily())
