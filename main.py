import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

from notion_api import fetch_due_cards, update_card
from srs_engine import calculate_sm2

from datetime import datetime, timezone

load_dotenv()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fetch data across your databases
    db_ids = [os.getenv("NOTION_ISM_DB_ID"), os.getenv("NOTION_FIL_DB_ID"), os.getenv("NOTION_CLOSED_DB_ID")]
    master_queue = []
    
    await update.message.reply_text("Fetching your due Arabic vocabulary...")
    
    for db_id in db_ids:
        if db_id:
            master_queue.extend(fetch_due_cards(db_id))
            
    context.user_data['queue'] = master_queue
    
    if not master_queue:
        await update.message.reply_text("Your queue is empty. You're done for today!")
        return

    keyboard = [[InlineKeyboardButton("Start Review", callback_data="next_card")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Initialize analytics trackers
    context.user_data['start_time'] = datetime.now(timezone.utc)
    context.user_data['reviewed_uuids'] = set()
    context.user_data['grades'] = {1: 0, 2: 0, 3: 0, 4: 0}

    await update.message.reply_text(f"Queue loaded: {len(master_queue)} cards due.", reply_markup=reply_markup)

async def send_next_card(query, context: ContextTypes.DEFAULT_TYPE):
    queue = context.user_data.get('queue', [])
    
    if not queue:
        keyboard = [[InlineKeyboardButton("Start New Session", callback_data="start_session")]]
        await query.edit_message_text("Session complete! All cards reviewed.")
        return
        
    current_card = queue[0] # Look at the first card
    
    keyboard = [[
        InlineKeyboardButton("Reveal Answer", callback_data="reveal"),
        InlineKeyboardButton("End Session", callback_data="end_session")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # English prompt only
    prompt_text = f"Translate:\n\n{current_card['meaning']}"
    await query.edit_message_text(prompt_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Acknowledge the button press
    
    data = query.data
    queue = context.user_data.get('queue', [])
    
    if data == "end_session":
        context.user_data['queue'] = []
        keyboard = [[InlineKeyboardButton("Start New Session", callback_data="start_session")]]
        await query.edit_message_text(generate_stats_message(context))
        return

    if data == "start_session":
        # Remove the inline keyboard from the stats message to lock it in history
        await query.edit_message_reply_markup(reply_markup=None)

        # Send a brand new message to the chat and save it as a variable
        status_msg = await context.bot.send_message(
            chat_id=query.message.chat_id, 
            text="Fetching your due Arabic vocabulary..."
        )

        # Replicates the /start command logic inside the callback
        db_ids = [os.getenv("NOTION_ISM_DB_ID"), os.getenv("NOTION_FIL_DB_ID"), os.getenv("NOTION_CLOSED_DB_ID")]
        master_queue = []
                
        for db_id in db_ids:
            if db_id:
                master_queue.extend(fetch_due_cards(db_id))
                
        context.user_data['queue'] = master_queue

        # Initialize analytics trackers
        context.user_data['start_time'] = datetime.now(timezone.utc)
        context.user_data['reviewed_uuids'] = set()
        context.user_data['grades'] = {1: 0, 2: 0, 3: 0, 4: 0}

        if not master_queue:
            keyboard = [[InlineKeyboardButton("Check Again", callback_data="start_session")]]
            await status_msg.edit_message_text("Your queue is empty. You're done for today!", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        keyboard = [[InlineKeyboardButton("Start Review", callback_data="next_card")]]       
        await status_msg.edit_message_text(f"Queue loaded: {len(master_queue)} cards due.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
        
    if data == "next_card":
        await send_next_card(query, context)
        return
        
    if data == "reveal":
        current_card = queue[0]
        
        # 4 Grade buttons
        keyboard = [
            [
                InlineKeyboardButton("Again", callback_data="grade_1"),
                InlineKeyboardButton("Hard", callback_data="grade_2"),
                InlineKeyboardButton("Good", callback_data="grade_3"),
                InlineKeyboardButton("Easy", callback_data="grade_4")
            ],
            [InlineKeyboardButton("End Session", callback_data="end_session")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Placing Arabic on a new line triggers RTL alignment
        reveal_text = f"{current_card['meaning']}\n\n{current_card['lemma']}"
        await query.edit_message_text(reveal_text, reply_markup=reply_markup)
        return
        
    if data.startswith("grade_"):
        grade = int(data.split("_")[1])
        current_card = queue.pop(0) # Remove card from queue

        # Log the analytics
        context.user_data['reviewed_uuids'].add(current_card['uuid'])
        context.user_data['grades'][grade] += 1
        
        # Calculate new spacing
        new_interval, new_ease, next_date = calculate_sm2(
            grade, 
            current_card['interval'], 
            current_card['ease']
        )
        
        # Patch to Notion
        update_card(current_card['uuid'], next_date, new_interval, new_ease)
        
        # If user pressed Again (1), push it back to the end of the session queue
        if grade == 1:
            # Temporarily reset its interval in memory so it doesn't skip days when reviewed again
            current_card['interval'] = new_interval
            current_card['ease'] = new_ease
            queue.append(current_card)
            
        # Move immediately to the next card
        await send_next_card(query, context)

# Helper function to generate stats at end of session
def generate_stats_message(context):
    start_time = context.user_data.get('start_time', datetime.now(timezone.utc))
    duration = datetime.now(timezone.utc) - start_time
    mins, secs = divmod(duration.seconds, 60)
    
    unique_cards = len(context.user_data.get('reviewed_uuids', set()))
    grades = context.user_data.get('grades', {1: 0, 2: 0, 3: 0, 4: 0})
    
    return (
        f"🏁 Session Complete!\n\n"
        f"⏱️ Duration: {mins}m {secs}s\n"
        f"🃏 Unique Cards: {unique_cards}\n\n"
        f"📊 Grade Breakdown:\n"
        f"Again (1): {grades[1]}\n"
        f"Hard (2): {grades[2]}\n"
        f"Good (3): {grades[3]}\n"
        f"Easy (4): {grades[4]}"
    )

# Test function for data retrieval from Notion dbs
def main():
    # Load all three database IDs
    db_ids = [
        os.getenv("NOTION_ISM_DB_ID"),
        os.getenv("NOTION_FIL_DB_ID"),
        os.getenv("NOTION_CLOSED_DB_ID")
    ]
    
    master_queue = []
    
    print("Fetching due cards from Notion...")
    
    for db_id in db_ids:
        if db_id: # Ensure the ID exists in the .env file
            cards = fetch_due_cards(db_id)
            master_queue.extend(cards)
    
    print(f"Found {len(master_queue)} cards due for review.")
    for card in master_queue:
        print(f"Lemma: {card['lemma']} | Meaning: {card['meaning']} | Interval: {card['interval']} | Ease: {card['ease']}")

if __name__ == "__main__":
    # main()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(bot_token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Arabic SRS Bot is running...")
    app.run_polling()