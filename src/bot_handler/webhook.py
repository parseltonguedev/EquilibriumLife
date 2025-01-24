import os
import json
import asyncio

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
import aioboto3
from openai import AsyncOpenAI
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

from bot_handler.mood_history import show_history

# Configure logging
logger = Logger()

# Conversation states
ASK_MOOD, ASK_NOTES = range(2)

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Telegram bot setup
application = ApplicationBuilder().token(os.getenv("TELEGRAM_TOKEN")).build()


# ----- Main Menu -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with persistent keyboard"""
    keyboard = [
        ["😊 Log Mood", "📊 Mood History"],
        ["⚙️ Settings", "ℹ️ Help"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "🌟 Welcome to Equilibrium!\n"
        "Your AI-powered wellness companion.\n\n"
        "Choose an action below:",
        reply_markup=reply_markup
    )


# ----- Mood Logging Flow -----
async def log_mood_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start mood logging flow"""
    logger.info("Asking how user feeling today")
    buttons = [
        [
            InlineKeyboardButton("😢 1", callback_data="1"),
            InlineKeyboardButton("😞 2", callback_data="2"),
            InlineKeyboardButton("😐 3", callback_data="3"),
            InlineKeyboardButton("😊 4", callback_data="4"),
            InlineKeyboardButton("😄 5", callback_data="5")
        ]
    ]
    markup = InlineKeyboardMarkup(buttons)


    await update.message.reply_text(
        "How are you feeling today?",
        reply_markup=markup
    )
    return ASK_MOOD


async def mood_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle mood selection and request notes"""
    query = update.callback_query
    await query.answer()

    mood = query.data
    logger.info(f"User query data mood: {mood=}")
    context.user_data["mood"] = mood

    buttons = [[InlineKeyboardButton("Skip Notes ❌", callback_data="skip_notes")]]

    await query.edit_message_text(
        f"Selected mood: {mood}/5\n"
        "Want to add any notes? (e.g. 'Great workout today!')",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    return ASK_NOTES


async def save_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save mood with optional notes to DynamoDB"""
    user_id = update.effective_user.id
    mood = context.user_data["mood"]
    notes = update.message.text

    logger.info(f"Saving notes for {user_id=}, {mood=}, {notes=}")

    # Save to DynamoDB
    try:
        await log_mood_to_dynamodb(user_id, mood, notes)
    except Exception as e:
        logger.error(f"DynamoDB Error: {str(e)}")
        await update.message.reply_text("⚠️ Failed to save mood. Please try again.")
        return ConversationHandler.END

    # Get AI tip
    try:
        tip = await get_ai_tip(mood)
    except Exception as e:
        logger.error(f"OpenAI Error: {str(e)}")
        tip = ""

    # Send confirmation
    response = f"✅ Mood {mood} logged!"
    if tip:
        response += f"\n\n💡 AI Tip: {tip}"

    await update.message.reply_text(response)
    await show_main_menu(update.message)
    return ConversationHandler.END


async def skip_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle skip notes button"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    mood = context.user_data["mood"]

    logger.info(f"Skipping notes for {user_id} mood is {mood}.")

    try:
        logger.info(f"Logging mood to DynamoDB")
        await log_mood_to_dynamodb(user_id, mood, "")
    except Exception as e:
        logger.error(f"DynamoDB Error: {str(e)}")
        await query.edit_message_text("⚠️ Failed to save mood. Please try again.")
        return ConversationHandler.END

    # Get AI tip
    try:
        tip = await get_ai_tip(mood)
    except Exception as e:
        logger.error(f"OpenAI Error: {str(e)}")
        tip = ""

    response = f"✅ Mood {mood} logged!"
    if tip:
        response += f"\n\n💡 AI Tip: {tip}"

    await query.edit_message_text(response)
    await show_main_menu(query.message)
    return ConversationHandler.END


# ----- Helper Functions -----
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


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Conversation canceled. Goodbye!")
    return ConversationHandler.END


async def get_ai_tip(mood: int) -> str:
    """Get AI-generated wellness tip"""
    try:
        logger.info(f"Sending request to get AI tip..")
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "system",
                "content": f"User reported mood {mood}/5. Give one short, actionable tip."
            }]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI Error: {str(e)}")
        return ""


async def show_main_menu(message):
    """Show persistent main menu"""
    keyboard = [
        ["😊 Log Mood", "📊 Mood History"],
        ["⚙️ Settings", "ℹ️ Help"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await message.reply_text("What would you like to do next?", reply_markup=reply_markup)


# ----- Setup Handlers -----
def setup_handlers():
    # Start command
    try:
        application.add_handler(CommandHandler("start", start))

        # Main menu interactions
        application.add_handler(MessageHandler(filters.Regex(r"^📊 Mood History$"), show_history))

        # Mood logging conversation
        conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(r"^😊 Log Mood$"), log_mood_start)],
            states={
                ASK_MOOD: [CallbackQueryHandler(mood_selected, pattern="^[1-5]$")],
                ASK_NOTES: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_notes),
                    CallbackQueryHandler(skip_notes, pattern="^skip_notes$"),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        application.add_handler(conv_handler)
    except Exception as error:
        logger.error(f"Error: {error}", exc_info=True)
        raise error


async def async_handler(event):
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


@logger.inject_lambda_context
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Sync Lambda entry point"""
    setup_handlers()
    return asyncio.run(async_handler(event))
