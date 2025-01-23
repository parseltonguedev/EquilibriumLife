import asyncio
import os
import logging
from typing import Dict, Any
import json

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
)
import aioboto3
from openai import AsyncOpenAI

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Telegram bot setup
application = (
    ApplicationBuilder()
    .token(os.getenv("TELEGRAM_TOKEN"))
    .build()
)


async def log_mood_to_dynamodb(user_id: int, mood: int, notes: str) -> None:
    """Async function to save mood entry to DynamoDB"""
    session = aioboto3.Session()
    async with session.resource('dynamodb', region_name='eu-central-1') as dynamodb:
        table = await dynamodb.Table(os.getenv("DYNAMODB_TABLE"))

        await table.put_item(
            Item={
                "userId": f"telegram_{user_id}",
                "sk": f"mood#{asyncio.get_event_loop().time()}",
                "moodValue": mood,
                "notes": notes,
                "type": "mood",
            }
        )


async def get_ai_tip(mood: int) -> str:
    """Get mood-specific tip from OpenAI"""
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": f"User reported mood {mood}/5. Give one short, actionable tip."
            }]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error: {str(e)}")
        return ""


# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user = update.effective_user
    await update.message.reply_text(
        f"🌟 Welcome {user.first_name}!\n"
        "I'm Equilibrium, your wellness companion.\n\n"
        "Track your mood: /logmood [1-5]\n"
        "View history: /history"
    )


async def log_mood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /logmood command"""
    try:
        user_id = update.effective_user.id
        args = context.args

        if not args or not args[0].isdigit():
            raise ValueError("Invalid format")

        mood = int(args[0])
        if not 1 <= mood <= 5:
            raise ValueError("Mood out of range")

        notes = " ".join(args[1:]) if len(args) > 1 else ""

        # Async write to DynamoDB
        await log_mood_to_dynamodb(user_id, mood, notes)

        response = f"✅ Mood {mood} logged!"
        # Get AI tip
        tip = await get_ai_tip(mood)
        if tip:
            response += f"\n\n💡 Tip: {tip}"

        await update.message.reply_text(response)

    except ValueError as e:
        await update.message.reply_text(
            "⚠️ Please use: /logmood [1-5] (e.g., /logmood 4 Great day!)"
        )
    except Exception as e:
        logger.error(f"Log mood error: {str(e)}")
        await update.message.reply_text("😢 Something went wrong. Please try again.")


async def async_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """Lambda entry point"""
    try:
        # Process Telegram update
        async with application:
            await application.process_update(
                Update.de_json(json.loads(event["body"]), application.bot)
            )

        return {"statusCode": 200, "body": "OK"}

    except Exception as e:
        logger.error(f"Lambda error: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": "Internal Server Error"}


# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("logmood", log_mood))


def lambda_handler(event: dict, context: dict) -> dict:
    """Sync wrapper for async handler"""
    return asyncio.run(async_handler(event))
