# Shuttle Bot

This is a Telegram bot that allows users to request shuttle rides and manage their bookings. It also includes features like notifications for drivers and students, and automatic completion of rides.

## Features

- Request a shuttle ride
- Cancel a ride request
- Complete a ride
- Get notified about workday start and end times
- Automatic completion of rides

## Usage

To use the bot, simply start a conversation with it on Telegram and use the following commands:

- `/start`: Start the bot and see the welcome message.
- `/ride [Location] [Destination] [Time] [Purpose]`: Request a shuttle ride. Example: `/ride Library Dormitory 14:00 class`
- `/cancel_ride [RideID] (optional)`: Cancel your most recent ride or a specific ride by ID. Example: `/cancel` or `/cancel 123`
- `/complete [RideID]`: Manually mark a ride as completed. Example: `/complete 123`
- `/help`: Show this help message.

## Notes

- The purpose can be one of the following: class, switch, closed, other.
- The bot uses a webhook method for deployment.
- The bot includes a database reset scheduler that runs daily after midnight.
- The bot includes a notification scheduler for drivers and students.
- The bot includes a ride auto-completion feature.

## License

This project is free.
