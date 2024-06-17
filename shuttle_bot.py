import logging
import sqlite3
from datetime import datetime, timezone
from telegram import Update, ForceReply, Bot
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext
import ride_manager as rm
import subprocess
import sys
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import notifications
import asyncio

# Get the path to the Python interpreter in your virtual environment
python_executable = sys.executable

# Start the database reset scheduler as a separate process using the virtual environment's Python interpreter
subprocess.Popen([python_executable, "reset_database.py"])

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
conn = sqlite3.connect('rides.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS ride_requests (
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

# Initialize your bot with the token from environment variable
bot_token = os.getenv('BOT_TOKEN')
if not bot_token:
    raise RuntimeError('BOT_TOKEN environment variable is not set.')

bot = Bot(bot_token)

PORT = int(os.getenv('PORT',8080))

# Define allowed group chat IDs
ALLOWED_GROUP_CHAT_IDS = ["-XXXXXXXXXX", "-XXXXXXXXXX"]

def is_allowed_group(update: Update) -> bool:
    """Check if the message is from an allowed group."""
    chat_id = str(update.effective_chat.id)
    return chat_id in ALLOWED_GROUP_CHAT_IDS

# Initialize the scheduler
scheduler = AsyncIOScheduler()

# Schedule workday start and end notifications for drivers
scheduler.add_job(
    notifications.notify_workday_start_drivers,
    trigger='cron',
    hour=6,  # Adjust the hour as per your requirement (e.g., 6 AM)
    minute=0,  # Adjust the minute as per your requirement
    id='workday_start_notification_drivers'
)

scheduler.add_job(
    notifications.notify_workday_end_drivers,
    trigger='cron',
    hour=21,  # Adjust the hour as per your requirement (e.g., 9 PM)
    minute=0,  # Adjust the minute as per your requirement
    id='workday_end_notification_drivers'
)

# Schedule workday start and end notifications for students
scheduler.add_job(
    notifications.notify_workday_start_students,
    trigger='cron',
    hour=6,  # Adjust the hour as per your requirement (e.g., 6 AM)
    minute=0,  # Adjust the minute as per your requirement
    id='workday_start_notification_students'
)

scheduler.add_job(
    notifications.notify_workday_end_students,
    trigger='cron',
    hour=21,  # Adjust the hour as per your requirement (e.g., 9 PM)
    minute=0,  # Adjust the minute as per your requirement
    id='workday_end_notification_students'
)

# Start the scheduler
scheduler.start()

# Global variable to control notification state
notifications_paused = False

# Manage notifications pause/resume based on driver's work hours
# Example logic: pause notifications from 9 PM to 6 AM next day
# async def manage_notifications_based_on_hours():
#     global notifications_paused
#     while True:
#         current_hour = datetime.now().hour
#         if current_hour >= 21 or current_hour < 6:
#             notifications_paused = True
#         else:
#             notifications_paused = False
#         await asyncio.sleep(60 * 30)  # Check every 30 minutes

# Manage notifications 
async def manage_notifications_based_on_hours(start_hour: int, start_minute: int, end_hour: int, end_minute: int):
    global notifications_paused
    while True:
        now = datetime.now(timezone.utc).time()
        current_day = datetime.now(timezone.utc).weekday()
        start_time = time(start_hour, start_minute)
        end_time = time(end_hour, end_minute)
        
        logger.info(f"[DEBUG] Now: {now}")
        logger.info(f"[DEBUG] Current time: {now}")
        logger.info(f"[DEBUG] Start time: {start_time}")
        logger.info(f"[DEBUG] End time: {end_time}")

        # Check if today is Saturday (5) or Sunday (6)
        if current_day in [5, 6]:
            if not notifications_paused:
                logger.info(f"[DEBUG] Pausing notifications for weekend: Current day: {current_day}")
                notifications_paused = True

        else: 
            if start_time <= now < end_time:
                if not notifications_paused:
                    logger.info(f"[DEBUG] Transitioning to paused state: Current time: {now}, Start time: {start_time}, End time: {end_time}")
                    notifications_paused = True
            else:
                if notifications_paused:
                    logger.info(f"[DEBUG] Transitioning to active state: Current time: {now}, Start time: {start_time}, End time: {end_time}")
                    notifications_paused = False

        logger.info(f"[DEBUG] Current time: {now}, Start time: {start_time}, End time: {end_time}, Notifications paused: {notifications_paused}")
        await asyncio.sleep(5)  # Check every minute


# Start the coroutine for managing notifications
async def start_tasks():
    await manage_notifications_based_on_hours(21, 0, 6, 0)

WORKDAY_ENDED_MESSAGE = "The workday has ended. Please note that requests will be processed during the next workday."
WEEKEND_MESSAGE = "Sorry! The bot does not process requests on weekends. 👌"

def workday_check(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        now = datetime.now()
        current_time = now.time()
        current_day = now.weekday()  # Monday is 0 and Sunday is 6

        start_time = time(21, 0)  # 21:00
        end_time = time(6, 0)     # 06:00

        # Check if today is Saturday (5) or Sunday (6)
        if current_day in [5, 6]:
            print(f"[DEBUG] Current day: {current_day}, Weekend restriction applied.")
            await update.message.reply_text(WEEKEND_MESSAGE)
        # Check if current time is within the restricted period
        elif start_time <= current_time or current_time < end_time:
            print(f"[DEBUG] Current time: {current_time}, Restriction applied.")
            await update.message.reply_text(WORKDAY_ENDED_MESSAGE)
        else:
            print(f"[DEBUG] Current time: {current_time}, No restriction.")
            await func(update, context, *args, **kwargs)

    return wrapper

# def workday_check(func):
#     async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
#         global notifications_paused
#         if notifications_paused:
#             await update.message.reply_text(WORKDAY_ENDED_MESSAGE)
#         else:
#             await func(update, context, *args, **kwargs)
#         return wrapper

@workday_check
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed_group(update):
        await update.message.reply_text('This bot is restricted to specific groups.')
        return

    user = update.effective_user
    await update.message.reply_html(
        rf'Hi {user.mention_html()}! Use /ride to request a shuttle. '
        '\n\nFormat: /ride [Location] [Destination] [Time] [Purpose (class/switch/closed/other)]',
        reply_markup=ForceReply(selective=True),
    )

@workday_check
async def ride(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed_group(update):
        await update.message.reply_text('This bot is restricted to specific groups.')
        return

    try:
        details = context.args
        location = details[0]
        destination = details[1]
        time = details[2]
        purpose = details[3].lower()

        if purpose not in ['class', 'switch', 'closed', 'other']:
            await update.message.reply_text('Purpose must be one of: class, switch, closed, other.')
            return

        # Parse the requested time
        try:
            requested_time = datetime.strptime(time, "%H:%M")
        except ValueError:
            await update.message.reply_text('Invalid time format. Please provide time in HH:MM format (e.g., 14:30).')
            return

        # Combine with current date and convert to UTC
        current_date = datetime.now().date()
        requested_datetime = datetime.combine(current_date, requested_time.time(), tzinfo=timezone.utc)

        # Get current time in UTC
        current_time_utc = datetime.now(timezone.utc)

        # Check if the requested time is in the past
        if requested_datetime < current_time_utc:
            await update.message.reply_text('You cannot request a ride in the past. Please provide a valid time.')
            return

        # Save the ride request to the database
        ride_id = rm.save_ride_request(update.effective_user.id, location, destination, time, purpose)

        if ride_id:
            await update.message.reply_text(f'Ride requested from {location} to {destination} at {time} for {purpose}. Your ride ID is {ride_id}.')
        else:
            await update.message.reply_text(f'You already have a ride booked for {time}. Please cancel the current request before booking a new one.')
    except IndexError:
        await update.message.reply_text('Usage: /ride [Location] [Destination] [Time] [Purpose (class/switch/closed/other)]')

# Track the state of pending ride requests
previous_pending_requests = set()
previous_message = ""

@workday_check
async def notify_drivers(context: CallbackContext) -> None:
    global notifications_paused
    if notifications_paused:
        return

    global previous_pending_requests
    global previous_message
    
    pending_requests = rm.get_pending_ride_requests()
    logger.debug(f"Pending requests: {pending_requests}")
    
    # Convert the list of pending requests to a set of request IDs for comparison
    current_pending_requests = set(request[0] for request in pending_requests)
    
    group_chat_id = -XXXXXXXXXX

    # Check if there is any change in the pending requests
    if current_pending_requests != previous_pending_requests:
        high_priority_requests = []
        medium_priority_requests = []
        low_priority_requests = []
        
        # Categorize pending requests
        for request in pending_requests:
            user_id = request[1]
            location = request[2]
            destination = request[3]
            time = request[4]
            purpose = request[5].lower()
            
            try:
                # Fetch user information from Telegram
                user = await context.bot.get_chat(int(user_id))
                user_name = user.first_name if user.first_name else "User"  # Use first name for simplicity
                
                if purpose in ['class', 'switch']:
                    high_priority_requests.append(f"- {user_name} needs to be picked up from {location} to {destination} at {time}")
                elif purpose == 'closed':
                    medium_priority_requests.append(f"- {user_name} needs to be picked up from {location} to {destination} at {time}")
                elif purpose == 'other':
                    low_priority_requests.append(f"- {user_name} needs to be picked up from {location} to {destination} at {time}")
            except Exception as e:
                logger.error(f"Error fetching user {user_id}: {e}")
                continue
        
        # Count total pending requests
        total_requests = len(pending_requests)
        
        # Compose message if there are pending requests
        if total_requests > 0:
            message = "High Priority:\n"
            message += "\n".join(high_priority_requests) + "\n\n" if high_priority_requests else "None\n\n"
            
            message += "Medium Priority:\n"
            message += "\n".join(medium_priority_requests) + "\n\n" if medium_priority_requests else "None\n\n"
            
            message += "Low Priority:\n"
            message += "\n".join(low_priority_requests) + "\n\n" if low_priority_requests else "None\n\n"
            
            message += f"Total number of requests: {total_requests}"
            
            # Send message to group chat
            await context.bot.send_message(group_chat_id, message)

            # Update the previous message
            previous_message = message
        else:
            message = "No ride requests available."
            await context.bot.send_message(group_chat_id, message)
            print("No pending ride requests.")
        
        # Update the previous pending requests state
        previous_pending_requests = current_pending_requests
    else:
        # Only send "No new ride requests" if there are actually no pending requests
        if not current_pending_requests:
            message = "No ride requests available."
            await context.bot.send_message(group_chat_id, message)
            print("No pending ride requests.")
        else:
            # Send the previous message along with the "No new ride requests" note
            if previous_message:
                message = previous_message + "\n\nNo new ride requests."
            else:
                message = "No new ride requests."

            await context.bot.send_message(group_chat_id, message)
            print("No change in pending ride requests.")

@workday_check
async def complete_ride_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed_group(update):
        await update.message.reply_text('This bot is restricted to specific groups.')
        return

    try:
        ride_id = int(context.args[0])  # Assuming RideID is an integer

        # Retrieve complete ride data
        ride = rm.get_ride_status(ride_id)
        
        if ride is None:
            await update.message.reply_text(f'No such ride ID {ride_id} exists.')
        elif ride[6] == 'completed':
            await update.message.reply_text(f'Ride request {ride_id} has already been marked as completed.')
        else:
            rm.mark_ride_completed(ride_id)
            await update.message.reply_text(f'Ride request {ride_id} has been marked as completed.')
    except (IndexError, ValueError):
        await update.message.reply_text('Usage: /complete [RideID]')

@workday_check
async def cancel_ride_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed_group(update):
        await update.message.reply_text('This bot can only be used in specific groups.')
        return

    user_id = update.effective_user.id

    if context.args:
        try:
            ride_id = int(context.args[0])
            logger.info(f'User {user_id} is attempting to cancel ride ID: {ride_id}')

            # Check if the ride exists and get its details
            ride = rm.get_ride_status(ride_id)
            if ride:
                logger.info(f'Ride found: {ride}')
                if int(ride[1]) == user_id:  # Check if the ride belongs to the user
                    if ride[6] == 'completed':  # Check if the ride is already completed
                        await update.message.reply_text(f'Ride request {ride_id} has been completed already hence it cannot be canceled.')
                    else:
                        rm.cancel_ride(ride_id)
                        await update.message.reply_text(f'Ride request (ID: {ride_id}) has been canceled.')
                else:
                    await update.message.reply_text(f'No such ride ID {ride_id} exists or it does not belong to you.')
            else:
                await update.message.reply_text(f'No such ride ID {ride_id} exists.')
        except ValueError:
            await update.message.reply_text('Invalid Ride ID. Please provide a valid ride ID to cancel.')
    else:
        pending_rides = rm.get_user_pending_rides(user_id)
        
        if pending_rides:
            most_recent_ride = pending_rides[0]  # Get the most recent pending ride
            ride_id = most_recent_ride[0]
            rm.cancel_ride(ride_id)
            await update.message.reply_text(f'Your most recent ride request (ID: {ride_id}) has been canceled.')
        else:
            await update.message.reply_text('You have no pending ride requests to cancel.')

@workday_check
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed_group(update):
        await update.message.reply_text('This bot can only be used in specific groups.')
        return

    help_text = (
        "Hi! I'm the Shuttle Bot. Here's how you can use me:\n\n"
        "/start - Start the bot and see the welcome message.\n"
        "/ride [Location] [Destination] [Time] [Purpose] - Request a shuttle ride. Example: /ride Library Dormitory 14:00 class\n"
        "/cancel_ride [RideID] (optional) - Cancel your most recent ride or a specific ride by ID. Example: /cancel or /cancel 123\n"
        "/complete [RideID] - Manually mark a ride as completed. Example: /complete 123\n"
        "/help - Show this help message.\n"
        "Note: The purpose can be one of the following: class, switch, closed, other.\n"
    )
    await update.message.reply_text(help_text)

async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f"Error: {context.error} occurred with update {update}")
    if update:
        await update.message.reply_text('An error occurred. Please try again later.')

def main() -> None:
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(bot_token).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ride", ride))
    application.add_handler(CommandHandler("cancel", cancel_ride_command))
    application.add_handler(CommandHandler("complete", complete_ride_command))
    application.add_handler(CommandHandler("help", help_command))

    # Schedule job to notify drivers periodically
    application.job_queue.run_repeating(notify_drivers, interval=900, first=0)  # Every 15 mins
    application.job_queue.run_repeating(lambda context: rm.auto_complete_rides(), interval=300, first=0)  # Every 5 mins
    # Error handler registration
    application.add_error_handler(error_handler)

    # Start the coroutine for managing notifications
    loop = asyncio.get_event_loop()
    loop.create_task(start_tasks())
    
    # Start the Bot
    # application.run_polling()
    application.run_webhook(
        listen="0.0.0.0",
        port=int(PORT),
        url_path=bot_token,
        webhook_url=f'https://your_heroku_app_name.herokuapp.com/{bot_token}'
    )

if __name__ == '__main__':
    main()
