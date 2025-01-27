import json
import asyncio
from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
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
from shared.constants import MAIN_MENU_KEYBOARD, WELCOME_TEXT, MOOD_BUTTONS, ASK_MOOD_TEXT, SKIP_MOOD_NOTES_BUTTON, \
    SELECTED_MOOD_TEMPLATE, SAVE_MOOD_FAILURE_TEXT, SAVE_MOOD_SUCCESS_TEMPLATE, AI_TIP_MESSAGE_TEMPLATE, \
    AI_TIP_FAILURE_TEXT, CANCEL_CONVERSATION_TEXT, GPT_MODEL, GPT_MESSAGE_ROLE, GPT_MESSAGE_CONTENT_TEMPLATE, \
    END_CONVERSATION_TEXT, MOOD_HISTORY_TEXT, LOG_MOOD_TEXT, SELECTED_MOOD_REGEX, SKIP_NOTES_REGEX, \
    START_COMMAND_TEXT, CANCEL_COMMAND_TEXT, MOOD_PARAMETER
from shared.config import OPENAI_API_KEY, TELEGRAM_TOKEN, DYNAMODB_TABLE

# Configure logging
logger = Logger()

# Conversation states
ASK_MOOD, ASK_NOTES = range(2)

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Telegram bot setup
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()


# ----- Main Menu -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with persistent keyboard"""
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)

    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=reply_markup
    )


# ----- Mood Logging Flow -----
async def log_mood_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start mood logging flow"""
    markup = InlineKeyboardMarkup(MOOD_BUTTONS)

    await update.message.reply_text(
        ASK_MOOD_TEXT,
        reply_markup=markup
    )
    return ASK_MOOD


async def mood_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle mood selection and request notes"""
    query = update.callback_query
    await query.answer()

    mood = query.data
    context.user_data[MOOD_PARAMETER] = mood

    await query.edit_message_text(
        SELECTED_MOOD_TEMPLATE.substitute(mood=mood),
        reply_markup=InlineKeyboardMarkup(SKIP_MOOD_NOTES_BUTTON)
    )

    return ASK_NOTES


async def save_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save mood with optional notes to DynamoDB"""
    user_id = update.effective_user.id
    mood = context.user_data[MOOD_PARAMETER]
    notes = update.message.text

    # Save to DynamoDB
    try:
        await log_mood_to_dynamodb(user_id, mood, notes)
    except Exception as e:
        logger.error(f"DynamoDB Error: {str(e)}")
        await update.message.reply_text(SAVE_MOOD_FAILURE_TEXT)
        return ConversationHandler.END

    tip = await get_ai_tip(mood)

    # Send confirmation
    response = SAVE_MOOD_SUCCESS_TEMPLATE.substitute(mood=mood)
    if tip:
        response += AI_TIP_MESSAGE_TEMPLATE.substitute(tip=tip)

    await update.message.reply_text(response)
    await show_main_menu(update.message)
    return ConversationHandler.END


async def skip_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle skip notes button"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    mood = context.user_data[MOOD_PARAMETER]

    try:
        await log_mood_to_dynamodb(user_id, mood, "")
    except Exception as e:
        logger.error(f"DynamoDB Error: {str(e)}")
        await query.edit_message_text(SAVE_MOOD_FAILURE_TEXT)
        return ConversationHandler.END

    tip = await get_ai_tip(mood)

    response = SAVE_MOOD_SUCCESS_TEMPLATE.substitute(mood=mood)
    if tip:
        response += AI_TIP_MESSAGE_TEMPLATE.substitute(tip=tip)

    await query.edit_message_text(response)
    await show_main_menu(query.message)
    return ConversationHandler.END


# ----- Helper Functions -----
async def log_mood_to_dynamodb(user_id: int, mood: int, notes: str) -> None:
    """Async function to save mood entry to DynamoDB"""
    session = aioboto3.Session()
    async with session.resource('dynamodb') as dynamodb:
        table = await dynamodb.Table(DYNAMODB_TABLE)
        timestamp = datetime.now().timestamp()

        await table.put_item(
            Item={
                "userId": f"telegram_{user_id}",
                "sk": f"mood#{timestamp}",
                "moodValue": mood,
                "notes": notes,
                "type": MOOD_PARAMETER,
            }
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(CANCEL_CONVERSATION_TEXT)
    return ConversationHandler.END


async def get_ai_tip(mood: int) -> str:
    """Get AI-generated wellness tip"""
    try:
        response = await openai_client.chat.completions.create(
            model=GPT_MODEL,
            messages=[{
                "role": GPT_MESSAGE_ROLE,
                "content": GPT_MESSAGE_CONTENT_TEMPLATE.substitute(mood=mood)
            }]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI Error: {str(e)}")
        return AI_TIP_FAILURE_TEXT


async def show_main_menu(message):
    """Show persistent main menu"""
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    await message.reply_text(END_CONVERSATION_TEXT, reply_markup=reply_markup)


# ----- Setup Handlers -----
def setup_handlers():
    # Start command
    try:
        application.add_handler(CommandHandler(START_COMMAND_TEXT, start))

        # Main menu interactions
        application.add_handler(MessageHandler(filters.Regex(rf"^{MOOD_HISTORY_TEXT}$"), show_history))

        # Mood logging conversation
        conv_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(rf"^{LOG_MOOD_TEXT}$"), log_mood_start)],
            states={
                ASK_MOOD: [CallbackQueryHandler(mood_selected, pattern=SELECTED_MOOD_REGEX)],
                ASK_NOTES: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_notes),
                    CallbackQueryHandler(skip_notes, pattern=SKIP_NOTES_REGEX),
                ],
            },
            fallbacks=[CommandHandler(CANCEL_COMMAND_TEXT, cancel)],
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
