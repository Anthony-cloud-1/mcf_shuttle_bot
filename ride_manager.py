import sqlite3
from datetime import datetime, timedelta
import logging

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
conn = sqlite3.connect('rides.db', check_same_thread=False)
c = conn.cursor()

def save_ride_request(user_id, location, destination, time, purpose):
    if not user_can_book_ride(user_id, time):
        return None
    c.execute('''
        INSERT INTO ride_requests (user_id, location, destination, time, purpose)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, location, destination, time, purpose))
    conn.commit()
    logger.info(f'Saved ride request: user_id={user_id}, location={location}, destination={destination}, time={time}, purpose={purpose}')
    return c.lastrowid

def get_ride_status(ride_id):
    c.execute('SELECT * FROM ride_requests WHERE id = ?', (ride_id,))
    return c.fetchone()

def get_pending_ride_requests():
    current_time = datetime.now().time().strftime('%H:%M')
    next_departure_times = ['07:15', '09:15', '11:15', '13:15', '15:15', '17:15', '19:15']  # Add more as needed
    
    logger.debug(f"Current time: {current_time}")

    # Find the next departure time
    for departure_time in next_departure_times:
        if current_time < departure_time:
            # Get pending requests before the next departure time
            c.execute('''
                SELECT * FROM ride_requests
                WHERE status = 'pending'
                AND time <= ?
                ORDER BY time ASC
            ''', (departure_time,))
            return c.fetchall()
    
    return []

def user_can_book_ride(user_id, time):
    c.execute('''
        SELECT * FROM ride_requests
        WHERE user_id = ? AND time = ? AND status = 'pending'
    ''', (user_id, time))
    return c.fetchone() is None

def get_user_pending_rides(user_id):
    c.execute('''
        SELECT * FROM ride_requests
        WHERE user_id = ? AND status = 'pending'
        ORDER BY time DESC
    ''', (user_id,))
    return c.fetchall()

def cancel_ride(ride_id):
    c.execute('''
        DELETE FROM ride_requests
        WHERE id = ?
    ''', (ride_id,))
    conn.commit()

def mark_ride_completed(ride_id):
    c.execute('UPDATE ride_requests SET status = ? WHERE id = ?', ('completed', ride_id))
    conn.commit()

def auto_complete_rides():
    now = datetime.now()
    current_time_str = now.strftime('%H:%M')
    next_departure_times = ['07:15', '09:15', '11:15', '13:15', '15:15', '17:15', '19:15']  # Add more as needed

    # Find the previous departure time
    previous_departure_time = '00:00'
    for departure_time in next_departure_times:
        if current_time_str < departure_time:
            break
        previous_departure_time = departure_time

    cutoff_time = (now - timedelta(minutes=40)).strftime('%H:%M')
    
    c.execute('''
        UPDATE ride_requests
        SET status = 'completed'
        WHERE status = 'pending'
        AND time <= ?
        AND time >= ?
    ''', (cutoff_time, previous_departure_time))
    conn.commit()

def auto_complete_rides_wrapper(context: CallbackContext):
    auto_complete_rides()
