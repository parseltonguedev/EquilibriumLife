# src/bot_handler/reminders.py
import os
import logging
import aioboto3
from telegram import Bot
from telegram.error import TelegramError
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


async def get_users_with_reminders_enabled() -> list:
    """Fetch all users who have opted into reminders"""
    dynamodb = aioboto3.resource("dynamodb")
    table = await dynamodb.Table(os.getenv("DYNAMODB_TABLE"))

    try:
        # Scan for users with reminder preference
        # For POC: Assume all users with at least one mood log want reminders
        response = await table.scan(
            ProjectionExpression="userId",
            FilterExpression="begins_with(sk, :prefix)",
            ExpressionAttributeValues={":prefix": "mood#"}
        )

        # Extract unique user IDs
        users = list({item["userId"] for item in response.get("Items", [])})
        return users

    except Exception as e:
        logger.error(f"DynamoDB scan error: {str(e)}")
        return []


async def send_reminder(user_id: str, bot: Bot) -> bool:
    """Send reminder message to a single user"""
    try:
        # Extract numeric ID from "telegram_12345" format
        telegram_id = int(user_id.split("_")[1])
        await bot.send_message(
            chat_id=telegram_id,
            text="🌞 Good morning! How are you feeling today?\n"
                 "Use /logmood [1-5] to track your mood."
        )
        return True
    except (ValueError, IndexError, TelegramError) as e:
        logger.warning(f"Failed to send to {user_id}: {str(e)}")
        return False


async def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler"""
    bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
    try:
        # Get users to notify
        users = await get_users_with_reminders_enabled()
        if not users:
            logger.info("No users to remind")
            return {"statusCode": 200, "body": "No users found"}

        # Send reminders in parallel
        results = await asyncio.gather(
            *[send_reminder(user_id, bot) for user_id in users]
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
    finally:
        await bot.close()
