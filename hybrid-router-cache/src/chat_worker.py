import sys
import os
import time
import json
from datetime import datetime

# Adjust Python path to allow running directly from src/ or project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.cache.firestore_client import get_db
from src.pipeline import run_pipeline

# Record the start time so we don't reply to old messages that are fetched on startup
START_TIME = int(time.time() * 1000)

def handle_message(event):
    """
    Callback for changes in the /messages node.
    event.event_type can be 'put' or 'patch'.
    event.path is the relative path from /messages.
    event.data is the new data.
    """
    # If the path is "/", it's the initial load of all messages (or a reset)
    if event.path == "/":
        return

    # event.path will look like "/chatId/messageId" for a new message
    path_parts = [p for p in event.path.split("/") if p]
    if len(path_parts) != 2:
        return
    
    chat_id, msg_id = path_parts[0], path_parts[1]
    msg = event.data

    if not isinstance(msg, dict):
        return

    # Skip our own messages
    if msg.get("senderId") == "bot":
        return
    
    # Skip old messages
    msg_timestamp = msg.get("timestamp", 0)
    if msg_timestamp < START_TIME:
        return
    
    text = msg.get("text", "").strip()
    if not text:
        return

    print(f"\n[worker] Received new message in chat '{chat_id}': {text}")
    print("[worker] Running pipeline...")
    
    try:
        # Run the AI pipeline
        result = run_pipeline(text)
        
        # Format the response
        goal_routes = result.get("routing", {}).get("goal", [])
        plan_routes = result.get("routing", {}).get("plan", [])
        goal_route = goal_routes[-1]["tier"] if goal_routes else "cache/local"
        plan_route = plan_routes[-1]["tier"] if plan_routes else "cache/local"

        formatted_response = (
            f"**Goal Understood:**\n```json\n{json.dumps(result['goal'], indent=2)}\n```\n\n"
            f"**Task Plan:**\n```json\n{json.dumps(result['tasks'], indent=2)}\n```\n\n"
            f"---\n"
            f"*Metrics: Cache (Goal: {result['cache_hits']['goal']}, Plan: {result['cache_hits']['plan']}) | "
            f"Fireworks Tokens: {result.get('fireworks_tokens', 0)} | "
            f"Route (Goal: {goal_route}, Plan: {plan_route}) | "
            f"Tokens: {result['tokens_used']} | Latency: {result['latency_sec']}s*"
        )
        
        bot_msg = {
            "text": formatted_response,
            "senderId": "bot",
            "senderName": "AMD Bot",
            "senderAvatarColor": "from-emerald-500 to-teal-500",
            "timestamp": int(time.time() * 1000)
        }
        
        # Write back to Firebase
        db = get_db()
        db.child(f"messages/{chat_id}").push(bot_msg)
        print("[worker] Replied successfully.")
        
    except Exception as e:
        print(f"[worker] Error processing message: {e}")
        error_msg = {
            "text": f"Sorry, I encountered an error: {str(e)}",
            "senderId": "bot",
            "senderName": "AMD Bot",
            "senderAvatarColor": "from-red-500 to-rose-500",
            "timestamp": int(time.time() * 1000)
        }
        get_db().child(f"messages/{chat_id}").push(error_msg)

def main():
    print("Starting AMD Chat Worker...")
    try:
        db = get_db()
        messages_ref = db.child("messages")
        print("Listening for new messages on /messages...")
        
        # Start listening (runs in a background thread)
        listener = messages_ref.listen(handle_message)
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down worker...")
            listener.close()
            
    except Exception as e:
        print(f"Failed to start worker: {e}")

if __name__ == "__main__":
    main()
