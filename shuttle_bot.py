import logging
import sqlite3
from datetime import datetime, timezone
from telegram import Update, ForceReply, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext, CallbackQueryHandler
from telegram.error import BadRequest
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

# Define the group chat IDs
DRIVERS_GROUP_CHAT_ID = -XXXXXXXXXX
STUDENTS_GROUP_CHAT_ID = -XXXXXXXXXX

def is_allowed_group(update: Update) -> bool:
    """Check if the message is from an allowed group."""
    chat_id = str(update.effective_chat.id)
    return chat_id in ALLOWED_GROUP_CHAT_IDS

# Initialize the scheduler
scheduler = AsyncIOScheduler()

# Define job IDs for easier management
driver_start_job_id = 'workday_start_notification_drivers'
driver_end_job_id = 'workday_end_notification_drivers'
student_start_job_id = 'workday_start_notification_students'
student_end_job_id = 'workday_end_notification_students'

# Function to enable or disable jobs based on the current day
def manage_weekend_jobs():
    current_day = datetime.now().weekday()  # Monday is 0, Sunday is 6

    if current_day in [5, 6]:  # If it's Saturday (5) or Sunday (6)
        # Disable the jobs
        scheduler.pause_job(driver_start_job_id)
        scheduler.pause_job(driver_end_job_id)
        scheduler.pause_job(student_start_job_id)
        scheduler.pause_job(student_end_job_id)
    else:
        # Enable the jobs
        scheduler.resume_job(driver_start_job_id)
        scheduler.resume_job(driver_end_job_id)
        scheduler.resume_job(student_start_job_id)
        scheduler.resume_job(student_end_job_id)

async def clear_messages():
    for chat_id in ALLOWED_GROUP_CHAT_IDS:
        try:
            message_ids = []
            async for message in bot.get_chat_history(chat_id):
                message_ids.append(message.message_id)
                if len(message_ids) % 100 == 0:  # Clear in chunks of 100
                    for message_id in message_ids:
                        try:
                            await bot.delete_message(chat_id, message_id)
                            print("Messages cleared successfully.")
                        except BadRequest as e:
                            print(f"Failed to delete message {message_id} in chat {chat_id}: {e}")
                    message_ids.clear()

            # Clear remaining messages
            for message_id in message_ids:
                try:
                    await bot.delete_message(chat_id, message_id)
                    print("All messages cleared successfully.")
                except BadRequest as e:
                    print(f"Failed to delete message {message_id} in chat {chat_id}: {e}")

        except Exception as e:
            print(f"Error clearing messages in chat {chat_id}: {e}")

# Schedule workday start and end notifications for drivers
scheduler.add_job(
    notifications.notify_workday_start_drivers,
    trigger='cron',
    hour=6,  # Adjust the hour as per your requirement (e.g., 6 AM)
    minute=0,  # Adjust the minute as per your requirement
    id=driver_start_job_id
)

scheduler.add_job(
    notifications.notify_workday_end_drivers,
    trigger='cron',
    hour=20,  # Adjust the hour as per your requirement (e.g., 8 PM)
    minute=30,  # Adjust the minute as per your requirement
    id=driver_end_job_id
)

# Schedule workday start and end notifications for students
scheduler.add_job(
    notifications.notify_workday_start_students,
    trigger='cron',
    hour=6,  # Adjust the hour as per your requirement (e.g., 6 AM)
    minute=0,  # Adjust the minute as per your requirement
    id=student_start_job_id
)

scheduler.add_job(
    notifications.notify_workday_end_students,
    trigger='cron',
    hour=20,  # Adjust the hour as per your requirement (e.g., 8 PM)
    minute=30,  # Adjust the minute as per your requirement
    id=student_end_job_id
)

# Schedule the weekend management job to run daily at midnight
scheduler.add_job(
    manage_weekend_jobs,
    trigger='cron',
    hour=0,
    minute=0,
    id='manage_weekend_jobs'
)

# Schedule the job to clear messages in both groups after midnight
scheduler.add_job(
    clear_messages,
    trigger='cron',
    hour=0,
    minute=1,  # Run slightly after midnight to avoid timing issues
    id='clear_messages_job'
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
async def manage_notifications_based_on_hours():
    global notifications_paused

    while True:
        now = datetime.now(timezone.utc).time()
        current_day = datetime.now(timezone.utc).weekday()
        start_time = time(20, 0)
        end_time = time(6, 0)
        
        logger.info(f"[DEBUG] Now: {now}")
        logger.info(f"[DEBUG] Current day: {current_day}")
        logger.info(f"[DEBUG] Start time: {start_time}")
        logger.info(f"[DEBUG] End time: {end_time}")

        # Check if today is Saturday (5) or Sunday (6)
        if current_day in [5, 6]:
            if not notifications_paused:
                logger.info(f"[DEBUG] Pausing notifications for weekend: Current day: {current_day}")
                notifications_paused = True

        else: 
            if start_time <= now or now < end_time:
                if not notifications_paused:
                    logger.info(f"[DEBUG] Transitioning to paused state: Current time: {now}, Start time: {start_time}, End time: {end_time}")
                    notifications_paused = True
            else:
                if notifications_paused:
                    logger.info(f"[DEBUG] Transitioning to active state: Current time: {now}, Start time: {start_time}, End time: {end_time}")
                    notifications_paused = False

        logger.info(f"[DEBUG] Current time: {now}, Start time: {start_time}, End time: {end_time}, Notifications paused: {notifications_paused}")
        await asyncio.sleep(60)  # Check every minute

# Start the coroutine for managing notifications
async def start_tasks():
    await manage_notifications_based_on_hours()

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

@workday_check
async def ride_for(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed_group(update):
        await update.message.reply_text('This bot is restricted to specific groups.')
        return

    try:
        details = context.args
        if len(details) < 5:
            await update.message.reply_text('Usage: /ride_for [Name] [Location] [Destination] [Time] [Purpose (class/switch/closed/other)]')
            return
        
        name = details[0]
        location = details[1]
        destination = details[2]
        time = details[3]
        purpose = details[4].lower()

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
        ride_id = rm.save_ride_request(name, location, destination, time, purpose)

        if ride_id:
            await update.message.reply_text(f'Ride requested from {location} to {destination} at {time} for {purpose} on behalf of {name}. Your ride ID is {ride_id}.')
        else:
            await update.message.reply_text(f'{name} already has a ride booked for {time}. Please cancel the current request before booking a new one.')
    except IndexError:
        await update.message.reply_text('Usage: /ride_for [Name] [Location] [Destination] [Time] [Purpose (class/switch/closed/other)]')

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
            await context.bot.send_message(DRIVERS_GROUP_CHAT_ID, message)

            # Update the previous message
            previous_message = message
        else:
            message = "No ride requests available."
            await context.bot.send_message(DRIVERS_GROUP_CHAT_ID, message)
            print("No pending ride requests.")
        
        # Update the previous pending requests state
        previous_pending_requests = current_pending_requests
    else:
        # Only send "No new ride requests" if there are actually no pending requests
        if not current_pending_requests:
            message = "No ride requests available."
            await context.bot.send_message(DRIVERS_GROUP_CHAT_ID, message)
            print("No pending ride requests.")
        else:
            # Send the previous message along with the "No new ride requests" note
            if previous_message:
                message = previous_message + "\n\nNo new ride requests."
            else:
                message = "No new ride requests."

            await context.bot.send_message(DRIVERS_GROUP_CHAT_ID, message)
            print("No change in pending ride requests.")

@workday_check
async def complete_ride_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed_group(update):
        await update.message.reply_text('This bot is restricted to specific groups.')
        return

    user_id = update.effective_user.id

    if context.args:
        try:
            ride_id = int(context.args[0])  # Assuming RideID is an integer
            logger.info(f'User {user_id} is attempting to complete ride ID: {ride_id}')

            # Retrieve ride data
            ride = rm.get_ride_status(ride_id)
            
            if ride is None:
                await update.message.reply_text(f'No such ride ID {ride_id} exists.')

            else:
                try:
                    if int(ride[1]) == user_id:
                        if ride[6] == 'completed':
                            await update.message.reply_text(f'Ride request {ride_id} has already been marked as completed.')
                        else:
                            rm.mark_ride_completed(ride_id)
                            await update.message.reply_text(f'Ride request {ride_id} has been marked as completed.')
                    else:
                        await update.message.reply_text(f'No such ride ID {ride_id} exists or it does not belong to you.')
                except ValueError:
                    # Handle case where ride[1] is not an integer (i.e., booked on behalf of someone else)
                    keyboard = [
                        [
                            InlineKeyboardButton("Yes", callback_data=f'complete_ride_confirm_{ride_id}'),
                            InlineKeyboardButton("No", callback_data=f'complete_ride_cancel_{ride_id}')
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(f'This ride was booked on behalf of {ride[1]}. Do you want to complete it?', reply_markup=reply_markup)
        except (IndexError, ValueError):
            await update.message.reply_text('Usage: /complete [RideID] or /complete')
    else:
        pending_rides = rm.get_user_pending_rides(user_id)
        
        if pending_rides:
            most_recent_ride = pending_rides[0]  # Get the most recent pending ride
            ride_id = most_recent_ride[0]
            rm.mark_ride_completed(ride_id)
            await update.message.reply_text(f'Your most recent ride request (ID: {ride_id}) has been marked as completed.')
        else:
            await update.message.reply_text('You have no pending ride requests to complete.')

@workday_check
async def complete_ride_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    ride_id = int(query.data.split('_')[-1])

    ride = rm.get_ride_status(ride_id)
    if ride[6] != 'completed':
        rm.mark_ride_completed(ride_id)
        await query.edit_message_text(f'Ride request {ride_id} has been marked as completed.')
    else:
        await query.edit_message_text(f'Ride request {ride_id} is already completed.')

@workday_check
async def complete_ride_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.edit_message_text('Action canceled.')

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
                try:
                    if int(ride[1]) == user_id:  # Check if the ride belongs to the user
                        if ride[6] == 'completed':  # Check if the ride is already completed
                            await update.message.reply_text(f'Ride request {ride_id} has been completed already hence it cannot be canceled.')
                        else:
                            rm.cancel_ride(ride_id)
                            await update.message.reply_text(f'Ride request (ID: {ride_id}) has been canceled.')
                    else:
                        await update.message.reply_text(f'No such ride ID {ride_id} exists or it does not belong to you.')
                except ValueError:
                        # Check if the ride was booked for someone else
                        keyboard = [
                            [
                                InlineKeyboardButton("Yes", callback_data=f'cancel_ride_confirm_{ride_id}'),
                                InlineKeyboardButton("No", callback_data=f'cancel_ride_cancel_{ride_id}')
                            ]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await update.message.reply_text(f'This ride was booked on behalf of {ride[1]}. Do you want to cancel it?', reply_markup=reply_markup)
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
async def cancel_ride_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    ride_id = int(query.data.split('_')[-1])

    ride = rm.get_ride_status(ride_id)
    if ride and ride[6] == 'completed':
        await query.edit_message_text(f'Ride request {ride_id} has been completed already hence it cannot be canceled.')
    else:
        rm.cancel_ride(ride_id)
        await update.message.reply_text(f'Ride request (ID: {ride_id}) has been canceled.')

@workday_check
async def cancel_ride_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.edit_message_text('Action canceled.')

@workday_check
async def bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Fetch the user's rides from the database
    pending_rides = rm.get_user_pending_rides(user_id)
    completed_rides = rm.get_user_completed_rides(user_id)

    # Format the message
    message = "🚗 Your Ride Bookings:\n\n"

    if pending_rides:
        message += "📅 Pending Rides:\n"
        for idx, ride in enumerate(pending_rides, 1):
            location = ride[2]  # Location is the third column
            destination = ride[3]  # Destination is the fourth column
            ride_id = ride[0]  # Ride_id is the first column
            time = datetime.strptime(ride[4], '%H:%M').strftime("%H:%M")  # Time is the fifth column
            purpose = ride[5]
            message += f"{idx}. From {location} to {destination} at {time} for {purpose} (ID: {ride_id})\n"
    else:
        message += "📅 Pending Rides:\nNone\n"

    if completed_rides:
        message += "\n✅ Completed Rides:\n"
        for idx, ride in enumerate(completed_rides, 1):
            location = ride[2]  # Location is the third column
            destination = ride[3]  # Destination is the fourth column
            ride_id = ride[0]  # Ride_id is the first column
            time = datetime.strptime(ride[4], '%H:%M').strftime("%H:%M")  # Time is the fifth column
            purpose = ride[5]
            message += f"{idx}. From {location} to {destination} at {time} for {purpose} (ID: {ride_id})\n"
    else:
        message += "\n✅ Completed Rides:\nNone\n"

    # Send the message to the user
    await update.message.reply_text(message)

# Define the group chat IDs
DRIVERS_GROUP_CHAT_ID = -XXXXXXXXXX
STUDENTS_GROUP_CHAT_ID = -XXXXXXXXXX

# Function to check if there are pending ride requests
def has_pending_rides() -> bool:
    pending_requests = rm.get_pending_ride_requests()
    return len(pending_requests) > 0

# Handler for note_requests command
@workday_check
async def note_requests(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.id != DRIVERS_GROUP_CHAT_ID:
        await update.message.reply_text("This command can only be used by drivers.")
        return
    
    if not has_pending_rides():
        await update.message.reply_text("No pending ride requests to notify.")
        return
    
    # Notify the students group
    await context.bot.send_message(STUDENTS_GROUP_CHAT_ID, "All ride requests have been noted.")
    await update.message.reply_text("Notified the students group that all ride requests have been noted.")

# Handler for en_route command
@workday_check
async def en_route(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.id != DRIVERS_GROUP_CHAT_ID:
        await update.message.reply_text("This command can only be used by drivers.")
        return
    
    if not has_pending_rides():
        await update.message.reply_text("No pending ride requests to notify.")
        return
    
    # Notify the students group
    await context.bot.send_message(STUDENTS_GROUP_CHAT_ID, "The bus is now en route.")
    await update.message.reply_text("Notified the students group that the bus is en route.")

@workday_check
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed_group(update):
        await update.message.reply_text('This bot can only be used in specific groups.')
        return

    help_text = (
        "Hi! I'm the Shuttle Bot. Here's how you can use me:\n\n"
        "/start - Start the bot and see the welcome message.\n"
        "/ride [Location] [Destination] [Time] [Purpose] - Request a shuttle ride. Example: /ride Library Dormitory 14:00 class\n"
        "/ride_for [Name] [Location] [Destination] [Time] [Purpose] - Request a shuttle ride on behalf of a colleague. Example: /ride_for Anthony CCB MCF 14:00 class\n"
        "/cancel [RideID] (optional) - Cancel your most recent ride or a specific ride by ID. Example: /cancel or /cancel 123\n"
        "/complete [RideID] (optional) - Manually mark a ride as completed. Example: /complete or /complete 123\n"
        "/noted - For drivers use only.\n"
        "/en_route - For drivers use only.\n"
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
    application.add_handler(CallbackQueryHandler(cancel_ride_confirm, pattern='^cancel_ride_confirm_'))
    application.add_handler(CallbackQueryHandler(cancel_ride_cancel, pattern='^cancel_ride_cancel_'))
    application.add_handler(CommandHandler("complete", complete_ride_command))
    application.add_handler(CallbackQueryHandler(complete_ride_confirm, pattern='^complete_ride_confirm_'))
    application.add_handler(CallbackQueryHandler(complete_ride_cancel, pattern='^complete_ride_cancel_'))
    application.add_handler(CommandHandler("bookings", bookings))
    application.add_handler(CommandHandler("noted", note_requests))
    application.add_handler(CommandHandler("en_route", en_route))
    application.add_handler(CommandHandler("help", help_command))

    # Schedule job to notify drivers periodically
    application.job_queue.run_repeating(notify_drivers, interval=900, first=0)  # Every 15 mins
    # application.job_queue.run_repeating(lambda context: rm.auto_complete_rides(), interval=300, first=0)  # Every 5 mins
    application.job_queue.run_repeating(rm.auto_complete_rides_wrapper, interval=300, first=0)
    # Error handler registration
    application.add_error_handler(error_handler)

    # Start the coroutine for managing notifications
    loop = asyncio.get_event_loop()
    loop.create_task(start_tasks())
    
    # Start the Bot
    
    # Polling method
    # application.run_polling()

    # Webhook method
    application.run_webhook(
        listen="0.0.0.0",
        port=int(PORT),
        url_path=bot_token,
        webhook_url=f'https://your_heroku_app_name.herokuapp.com/{bot_token}'
    )

if __name__ == '__main__':
    main()
