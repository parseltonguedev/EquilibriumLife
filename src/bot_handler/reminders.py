import asyncio
from telegram.error import TelegramError
from telegram.ext import ApplicationBuilder
from typing import Dict, Any

from aws_lambda_powertools import Logger

from shared.config import TELEGRAM_TOKEN, DYNAMODB_TABLE
from aws_resources.dynamodb import AsyncDynamoDBClient

# Configure logging
logger = Logger()

# Telegram bot setup
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

async_dynamodb_client = AsyncDynamoDBClient(DYNAMODB_TABLE)


async def get_users_with_reminders_enabled() -> set:
    """Fetch all users who have opted into reminders"""
    user_ids = set()
    try:
        # Scan for users with reminder preference
        # For POC: Assume all users with at least one mood log want reminders
        async for scanned_users_records_response in async_dynamodb_client.scan(projection_expression="userId",
                                                                               filter_expression="begins_with(sk, :prefix)",
                                                                               expression_attribute_values={
                                                                                   ":prefix": "mood#"}):
            user_ids.add(scanned_users_records_response["userId"])

        # Extract unique user IDs
        return user_ids

    except Exception as e:
        logger.error(f"DynamoDB scan error: {str(e)}")
        return user_ids


async def send_reminder(user_id: str) -> bool:
    """Send reminder message to a single user"""
    try:
        async with application:

            bot = application.bot
            # Extract numeric ID from "telegram_12345" format
            telegram_id = int(user_id.split("_")[1])
            await bot.send_message(
                chat_id=telegram_id,
                text="🌞 Hello! How are you feeling today?\n"
                     "Tracking your mood daily helps you notice patterns, understand what affects your well-being, and make positive changes.\n"
                     "Even small check-ins can improve self-awareness and mental health. 💙"
            )
        return True
    except (ValueError, IndexError, TelegramError) as e:
        logger.warning(f"Failed to send to {user_id}: {str(e)}")
        return False


async def async_lambda_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """Main Lambda handler"""
    try:
        # Get users to notify
        users = await get_users_with_reminders_enabled()
        if not users:
            logger.info("No users to remind")
            return {"statusCode": 200, "body": "No users found"}

        # Send reminders in parallel
        results = await asyncio.gather(
            *[send_reminder(user_id) for user_id in users]
        )

        success_count = sum(results)
        logger.info(f"Sent {success_count}/{len(users)} reminders successfully")
        return {
            "statusCode": 200,
            "body": f"Sent {success_count} reminders"
        }

    except Exception as e:
        logger.error(f"Reminder handler failed: {str(e)}")
        return {"statusCode": 500, "body": "Internal Server Error"}


@logger.inject_lambda_context
def lambda_handler(event: dict, context) -> dict:
    """Sync Lambda entry point"""
    return asyncio.run(async_lambda_handler(event))
