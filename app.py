from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage,
    ButtonsTemplate, DatetimePickerTemplateAction, PostbackEvent
)
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Get environment variables
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# Initialize Flask app
app = Flask(__name__)

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("Missing LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    if not signature:
        abort(400, "Missing X-Line-Signature header")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400, "Invalid signature")

    return 'OK'

# Handle TextMessage events
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id
    datetime_picker_action = DatetimePickerTemplateAction(
        label="Select date",
        data="action=schedule&datetime",
        mode="datetime",
        initial="2024-12-25T00:00",
        max="2025-01-01T23:59",
        min="2024-12-25T00:00"
    )

    template_message = TemplateSendMessage(
        alt_text="日時選択メッセージ",
        template=ButtonsTemplate(
            text="日時を選んでください",
            actions=[datetime_picker_action]
        )
    )

    try:
        line_bot_api.push_message(user_id, template_message)
    except Exception as e:
        print(f"Error while sending datetime picker message: {e}")

# Handle Postback events
@handler.add(PostbackEvent)
def handle_postback(event):
    if "action=schedule" in event.postback.data:
        schedule_datetime = event.postback.params.get('datetime', '不明')
        message = TextSendMessage(text=f"あなたが選択した日時は {schedule_datetime} です。")

        try:
            line_bot_api.reply_message(event.reply_token, message)
        except Exception as e:
            print(f"Error while sending confirmation message: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
