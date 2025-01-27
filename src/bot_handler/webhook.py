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
from aws_resources.dynamodb import AsyncDynamoDBClient

# Configure logging
logger = Logger()

# Conversation states
ASK_MOOD, ASK_NOTES = range(2)

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Telegram bot setup
application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# Setup AsyncDynamoDB client
async_dynamodb_client = AsyncDynamoDBClient(DYNAMODB_TABLE)


# ----- Main Menu -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with persistent keyboard"""
    logger.info("User started EquilibriumLife Telegram bot")
    reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)

    await update.message.reply_text(
        WELCOME_TEXT,
        reply_markup=reply_markup
    )


# ----- Mood Logging Flow -----
async def log_mood_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start mood logging flow"""
    logger.info("Start user mood logging")
    markup = InlineKeyboardMarkup(MOOD_BUTTONS)

    await update.message.reply_text(
        ASK_MOOD_TEXT,
        reply_markup=markup
    )
    return ASK_MOOD


async def handle_mood_logging(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle mood selection and request notes"""
    logger.info("Handling user logged mood")
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
    logger.info("Saving user notes for logged mood")
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
    logger.info("User preferred to skip notes for mood logging")
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


async def log_mood_to_dynamodb(user_id: int, mood: int, notes: str) -> None:
    """Async function to save mood entry to DynamoDB"""
    logger.info("Log user mood to DynamoDB")
    timestamp = datetime.now().timestamp()
    user_mood_record = {
        "userId": f"telegram_{user_id}",
        "sk": f"mood#{timestamp}",
        "moodValue": mood,
        "notes": notes,
        "type": MOOD_PARAMETER,
    }
    await async_dynamodb_client.put_item(user_mood_record)


async def cancel(update: Update) -> int:
    logger.info("Cancel conversation")
    await update.message.reply_text(CANCEL_CONVERSATION_TEXT)
    return ConversationHandler.END


async def get_ai_tip(mood: int) -> str:
    """Get AI-generated wellness tip"""
    try:
        logger.info("Get AI tip for logged mood")
        ai_tip_response = await openai_client.chat.completions.create(
            model=GPT_MODEL,
            messages=[{
                "role": GPT_MESSAGE_ROLE,
                "content": GPT_MESSAGE_CONTENT_TEMPLATE.substitute(mood=mood)
            }]
        )
        return ai_tip_response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI Error occurred for getting AI tip for mood logging: {str(e)}")
        return AI_TIP_FAILURE_TEXT


async def show_main_menu(message):
    """Show persistent main menu"""
    logger.info("Show main menu")
    main_menu_reply_markup = ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD, resize_keyboard=True)
    await message.reply_text(END_CONVERSATION_TEXT, reply_markup=main_menu_reply_markup)


def setup_handlers():
    try:
        logger.info("Setup handlers")
        conversation_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(rf"^{LOG_MOOD_TEXT}$"), log_mood_start)],
            states={
                ASK_MOOD: [CallbackQueryHandler(handle_mood_logging, pattern=SELECTED_MOOD_REGEX)],
                ASK_NOTES: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_notes),
                    CallbackQueryHandler(skip_notes, pattern=SKIP_NOTES_REGEX),
                ],
            },
            fallbacks=[CommandHandler(CANCEL_COMMAND_TEXT, cancel)],
        )

        application.add_handler(CommandHandler(START_COMMAND_TEXT, start))
        application.add_handler(MessageHandler(filters.Regex(rf"^{MOOD_HISTORY_TEXT}$"), show_history))
        application.add_handler(conversation_handler)
    except Exception as error:
        logger.error(f"Error: {error}", exc_info=True)
        raise error


async def async_lambda_handler(event):
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
    return asyncio.run(async_lambda_handler(event))
