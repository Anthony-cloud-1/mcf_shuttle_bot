from telegram.ext import CallbackContext
from telegram import Bot
import os

# Initialize your bot with the token from environment variable
bot_token = os.getenv('BOT_TOKEN')
if not bot_token:
    raise RuntimeError('BOT_TOKEN environment variable is not set.')

bot = Bot(bot_token)

# Messages for notifications
START_WORKDAY_MESSAGE_DRIVERS = "🚗 Work day: Notification system started! Get ready for a productive day ahead. 🌟"
END_WORKDAY_MESSAGE_DRIVERS = "🌙 Job ended for today. Thank you for your hard work! See you tomorrow. 👋"

START_WORKDAY_MESSAGE_STUDENTS = "🚌 Shuttle service is now available! You can start requesting rides. 🌟"
END_WORKDAY_MESSAGE_STUDENTS = "🚌 Shuttle service has ended for today. See you again tomorrow! 👋"

drivers_group_chat_id = -1002232382285
pwd_group_chat_id = -1002248091028

async def notify_workday_start_drivers(context: CallbackContext) -> None:
    await context.bot.send_message(drivers_group_chat_id, START_WORKDAY_MESSAGE_DRIVERS)

async def notify_workday_end_drivers(context: CallbackContext) -> None:
    await context.bot.send_message(drivers_group_chat_id, END_WORKDAY_MESSAGE_DRIVERS)

async def notify_workday_start_students(context: CallbackContext) -> None:
    await context.bot.send_message(pwd_group_chat_id, START_WORKDAY_MESSAGE_STUDENTS)

async def notify_workday_end_students(context: CallbackContext) -> None:
    await context.bot.send_message(pwd_group_chat_id, END_WORKDAY_MESSAGE_STUDENTS)
