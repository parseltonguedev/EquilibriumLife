from string import Template

from telegram import InlineKeyboardButton

# ========================
# Telegram Commands
# ========================
START_COMMAND_TEXT = "start"
CANCEL_COMMAND_TEXT = "cancel"

# ========================
# UI Text and Labels
# ========================
LOG_MOOD_TEXT = "😊 Log Mood"
MOOD_HISTORY_TEXT = "📊 Mood History"
SETTINGS_TEXT = "⚙️ Settings"
HELP_TEXT = "ℹ️ Help"
WELCOME_TEXT = (
    "🌟 Welcome to Equilibrium!\n"
    "Your AI-powered wellness companion.\n\n"
    "Choose an action below:"
)
ASK_MOOD_TEXT = "How are you feeling today?"
SAVE_MOOD_FAILURE_TEXT = "⚠️ Failed to save mood. Please try again."
AI_TIP_FAILURE_TEXT = "💡 Couldn't fetch a tip. Try again later."
CANCEL_CONVERSATION_TEXT = "Conversation canceled. Goodbye!"
END_CONVERSATION_TEXT = "What would you like to do next?"

MOOD_HISTORY_NOT_FOUND_TEXT = "📭 No mood history found. Start tracking with /logmood"
MOOD_HISTORY_LAST_30_DAYS_TEXT = "📈 Your Mood History (Last 30 days)"
MOOD_HISTORY_GENERATION_FAILURE_TEXT = "⚠️ Failed to generate history. Please try again."

# ========================
# Templates
# ========================
SELECTED_MOOD_TEMPLATE = Template("Selected mood: $mood/5\nWant to add any notes? (e.g. 'Great workout today!')")
SAVE_MOOD_SUCCESS_TEMPLATE = Template("✅ Mood $mood logged!")
AI_TIP_MESSAGE_TEMPLATE = Template("\n\n💡 AI Tip: $tip")

# ========================
# Keyboards and Buttons
# ========================
MAIN_MENU_KEYBOARD = [
    [LOG_MOOD_TEXT, MOOD_HISTORY_TEXT],
    [SETTINGS_TEXT, HELP_TEXT]
]
MOOD_BUTTONS = [
    [
        InlineKeyboardButton("😢 1", callback_data="1"),
        InlineKeyboardButton("😞 2", callback_data="2"),
        InlineKeyboardButton("😐 3", callback_data="3"),
        InlineKeyboardButton("😊 4", callback_data="4"),
        InlineKeyboardButton("😄 5", callback_data="5")
    ]
]
SKIP_MOOD_NOTES_BUTTON = [[InlineKeyboardButton("Skip Notes ❌", callback_data="skip_notes")]]

# ========================
# GPT Configuration
# ========================
GPT_MODEL = "gpt-3.5-turbo"
GPT_MESSAGE_ROLE = "system"
GPT_MESSAGE_CONTENT_TEMPLATE = Template("User reported mood $mood/5. Give one short, actionable tip.")

# ========================
# Regex Patterns
# ========================
SELECTED_MOOD_REGEX = "^[1-5]$"
SKIP_NOTES_REGEX = "^skip_notes$"

# ========================
# Request parameters constants
# ========================
MOOD_PARAMETER = "mood"