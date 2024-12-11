from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage,
    ButtonsTemplate, DatetimePickerTemplateAction, PostbackEvent
)
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import os

# Load .env file
load_dotenv()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///schedule.db")
engine = create_engine(DATABASE_URL)
Base = declarative_base()

class Schedule(Base):
    __tablename__ = 'schedules'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    message = Column(String, nullable=False)
    scheduled_datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# LINE setup
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
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

    # Calculate datetime values
    # 現在の日時（分は00に設定）
    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)

    today = now_jst
    initial_date = today.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M")

    # 1年前と1年後の日時
    min_date = (today - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年前
    max_date = (today + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年後


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
        # Extract user message and datetime
        data_parts = event.postback.data.split("&")
        user_message = None
        for part in data_parts:
            if part.startswith("user_message="):
                user_message = part.split("=")[-1]
        schedule_datetime = event.postback.params.get('datetime', '不明')

        # Save to database
        if user_message and schedule_datetime != '不明':
            try:
                schedule = Schedule(
                    user_id=event.source.user_id,
                    message=user_message,
                    scheduled_datetime=datetime.fromisoformat(schedule_datetime)
                )
                session.add(schedule)
                session.commit()
                confirmation_message = TextSendMessage(
                    text=f"{user_message} を {schedule_datetime} に保存しました。"
                )
            except Exception as e:
                session.rollback()
                confirmation_message = TextSendMessage(
                    text=f"データベース保存中にエラーが発生しました: {e}"
                )
        else:
            confirmation_message = TextSendMessage(
                text="無効なデータが入力されました。"
            )

        try:
            line_bot_api.reply_message(event.reply_token, confirmation_message)
        except Exception as e:
            print(f"Error while sending confirmation message: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
