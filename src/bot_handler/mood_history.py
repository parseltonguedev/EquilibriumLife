import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import aioboto3
from aws_lambda_powertools import Logger

from shared.constants import MOOD_HISTORY_NOT_FOUND_TEXT, MOOD_HISTORY_LAST_30_DAYS_TEXT, MOOD_HISTORY_GENERATION_FAILURE_TEXT
from shared.config import DYNAMODB_TABLE

logger = Logger()


async def show_history(update, context) -> None:
    """Display mood history as a chart"""
    user_id = update.effective_user.id
    user_key = f"telegram_{user_id}"

    try:
        # Fetch mood history from DynamoDB
        moods = await get_mood_history(user_key)
        if not moods:
            await update.message.reply_text(MOOD_HISTORY_NOT_FOUND_TEXT)
            return

        # Generate chart
        chart_buffer = await generate_mood_chart(moods)

        # Send as photo
        await update.message.reply_photo(
            photo=chart_buffer,
            caption=MOOD_HISTORY_LAST_30_DAYS_TEXT,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"History error: {str(e)}", exc_info=True)
        await update.message.reply_text(MOOD_HISTORY_GENERATION_FAILURE_TEXT)


async def get_mood_history(user_key: str) -> list:
    """Query DynamoDB for mood entries"""
    session = aioboto3.Session()
    async with session.resource('dynamodb') as dynamodb:
        table = await dynamodb.Table(DYNAMODB_TABLE)

        response = await table.query(
            KeyConditionExpression="userId = :uid AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":uid": user_key,
                ":prefix": "mood#"
            },
            ScanIndexForward=False,  # Newest first
            Limit=30  # Last 30 entries
        )

        return response.get("Items", [])


async def generate_mood_chart(mood_data):
    # Convert timestamps and prepare data
    timestamps = []
    mood_values = []

    # Sort data by timestamp
    sorted_data = sorted(mood_data, key=lambda x: float(x['sk'].split('#')[1]))

    for entry in sorted_data:
        timestamp_str = entry['sk'].split('#')[1]
        timestamp = datetime.fromtimestamp(float(timestamp_str))
        timestamps.append(mdates.date2num(timestamp))  # Convert datetime to matplotlib format
        mood_values.append(int(entry['moodValue']))

    # Set style
    plt.style.use('bmh')

    # Create figure with white background
    fig, ax = plt.subplots(figsize=(12, 6), facecolor='white')
    ax.set_facecolor('white')

    # Create the main plot
    plt.plot(timestamps, mood_values,
             marker='o',
             linestyle='-',
             color='#4CAF50',
             linewidth=2,
             markersize=8,
             markerfacecolor='white',
             markeredgecolor='#4CAF50',
             markeredgewidth=2)

    # Format the date axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())

    # Customize the plot
    plt.grid(True, linestyle='--', alpha=0.3, color='gray')
    plt.title('Mood Timeline', fontsize=16, pad=20, color='#333333')
    plt.ylabel('Mood Level', fontsize=12, color='#333333')
    plt.xlabel('Time', fontsize=12, color='#333333')

    # Set y-axis limits and ticks
    plt.ylim(0.5, 5.5)
    plt.yticks(range(1, 6))

    # Rotate and align the tick labels so they look better
    plt.gcf().autofmt_xdate()

    # Add subtle spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cccccc')
    ax.spines['bottom'].set_color('#cccccc')

    # Adjust layout
    plt.tight_layout()

    # Save plot to buffer
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
    buffer.seek(0)
    plt.close()  # Close the figure to free memory

    return buffer
