from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage,
    ButtonsTemplate, DatetimePickerTemplateAction, PostbackEvent
)
from sqlalchemy import create_engine, Column, Integer, String, DateTime, and_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from datetime import datetime, timedelta,timezone
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

    # If the user asks for schedule confirmation
    if user_message == "予定確認":
        # Calculate datetime values
        JST = timezone(timedelta(hours=9))
        now_jst = datetime.now(JST)

        today = now_jst
        initial_date = today.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M")

        # 1年前と1年後の日時
        min_date = (today - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年前
        max_date = (today + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年後

        # Show datetime picker for user to select a date
        datetime_picker_action = DatetimePickerTemplateAction(
            label="日付を選択",
            data=f"action=check_schedule&user_id={user_id}",
            mode="datetime",
            initial=initial_date,
            max=max_date,
            min=min_date
        )

        template_message = TemplateSendMessage(
            alt_text="日時選択メッセージ",
            template=ButtonsTemplate(
                text="確認したい日のスケジュールを選んでください",
                actions=[datetime_picker_action]
            )
        )

        try:
            line_bot_api.push_message(user_id, template_message)
        except Exception as e:
            print(f"Error while sending datetime picker message: {e}")
    
    else:
        # Handle other messages (e.g., schedule input)
        # Your input handling logic goes here
        pass

# Handle Postback events
@handler.add(PostbackEvent)
def handle_postback(event):
    if "action=check_schedule" in event.postback.data:
        # Extract the specified date
        specified_date = event.postback.params.get('datetime', '不明')

        if specified_date != '不明':
            # Retrieve schedules for the specified date
            schedules = session.query(Schedule).filter(
                and_(
                    Schedule.scheduled_datetime >= datetime.fromisoformat(specified_date),
                    Schedule.scheduled_datetime < datetime.fromisoformat(specified_date) + timedelta(days=1)
                )
            ).all()

            # If there are schedules for that day
            if schedules:
                schedule_text = "\n".join([f"{s.message} - {s.scheduled_datetime.strftime('%Y-%m-%d %H:%M')}" for s in schedules])
                confirmation_message = TextSendMessage(
                    text=f"指定された日にちのスケジュール:\n{schedule_text}"
                )
            else:
                confirmation_message = TextSendMessage(
                    text="指定された日にちのスケジュールはありません。"
                )
        else:
            confirmation_message = TextSendMessage(
                text="無効な日時が選択されました。"
            )

        try:
            line_bot_api.reply_message(event.reply_token, confirmation_message)
        except Exception as e:
            print(f"Error while sending confirmation message: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
