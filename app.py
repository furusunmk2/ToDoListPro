from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage,
    ButtonsTemplate, DatetimePickerTemplateAction, PostbackEvent
)
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

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

    # ISO8601 形式の日付を計算
    today = datetime.now()
    initial_date = today.strftime("%Y-%m-%dT%H:%M")
    max_date = (today + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")
    min_date = today.strftime("%Y-%m-%dT%H:%M")

    datetime_picker_action = DatetimePickerTemplateAction(
        label="Select date",
        data=f"action=schedule&user_message={user_message}",
        mode="datetime",
        initial=initial_date,
        max=max_date,
        min=min_date
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
        # ポストバックデータからメッセージと日時を取得
        data_parts = event.postback.data.split("&")
        user_message = None
        for part in data_parts:
            if part.startswith("user_message="):
                user_message = part.split("=")[-1]
        schedule_datetime = event.postback.params.get('datetime', '不明')

        # 予約確認メッセージを作成
        if user_message:
            message_text = f"{user_message} を {schedule_datetime} に予約しました。"
        else:
            message_text = f"選択した日時は {schedule_datetime} です。"

        message = TextSendMessage(text=message_text)

        try:
            line_bot_api.reply_message(event.reply_token, message)
        except Exception as e:
            print(f"Error while sending confirmation message: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
