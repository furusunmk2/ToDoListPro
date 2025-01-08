from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage,
    ButtonsTemplate, DatetimePickerTemplateAction, PostbackEvent
)
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import logging
import os
import json

try:
    import google.generativeai as genai
    genai_available = True
except ImportError as e:
    print(f"Google Generative AI module not found: {e}")
    genai_available = False

# .envファイルの読み込み
load_dotenv()

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# データベースの設定
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///schedule.db")
JSON_FILE = "schedules.json"
engine = create_engine(DATABASE_URL)
Base = declarative_base()

# モデル定義
class Schedule(Base):
    __tablename__ = 'schedules'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    message = Column(String, nullable=False)
    scheduled_datetime = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
Session = scoped_session(sessionmaker(bind=engine))

# JSON保存と読み込み
def save_to_json():
    with Session() as session:
        schedules = session.query(Schedule).all()
        data = [
            {
                "id": schedule.id,
                "user_id": schedule.user_id,
                "message": schedule.message,
                "scheduled_datetime": schedule.scheduled_datetime.isoformat(),
                "created_at": schedule.created_at.isoformat()
            }
            for schedule in schedules
        ]
        with open(JSON_FILE, mode='w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)


def load_from_json():
    if not os.path.exists(JSON_FILE):
        return

    with open(JSON_FILE, mode='r', encoding='utf-8') as file:
        data = json.load(file)
        with Session() as session:
            for entry in data:
                schedule = Schedule(
                    id=entry['id'],
                    user_id=entry['user_id'],
                    message=entry['message'],
                    scheduled_datetime=datetime.fromisoformat(entry['scheduled_datetime']),
                    created_at=datetime.fromisoformat(entry['created_at'])
                )
                session.merge(schedule)
            session.commit()

# LINEの設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if genai_available and GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        gemini_pro = genai.GenerativeModel("gemini-pro")
        logger.info("Google Generative AI configured successfully.")
    except Exception as e:
        gemini_pro = None
        logger.error(f"Failed to configure Google Generative AI: {e}")
else:
    gemini_pro = None

app = Flask(__name__)

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN または LINE_CHANNEL_SECRET が設定されていません")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# アプリ起動時にJSONデータを読み込む
load_from_json()

def calculate_datetime_range():
    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)
    initial_date = now_jst.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M")
    min_date = (now_jst - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")
    max_date = (now_jst + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")
    return initial_date, min_date, max_date

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    if not signature:
        abort(400, "X-Line-Signature ヘッダーが欠けています")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400, "無効な署名です")

    return 'OK'

# メッセージイベントの処理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id
    initial_date, min_date, max_date = calculate_datetime_range()

    if user_message == "予定確認" or user_message == "日報作成":
        action_data = "check_schedule" if user_message == "予定確認" else "generate_report"
        datetime_picker_action = DatetimePickerTemplateAction(
            label="日付を選択", data=f"action={action_data}&user_id={user_id}", mode="datetime",
            initial=initial_date, max=max_date, min=min_date
        )
        template_message = TemplateSendMessage(
            alt_text="日時選択メッセージ",
            template=ButtonsTemplate(
                text="確認したい日を選んでください。", actions=[datetime_picker_action]
            )
        )
        line_bot_api.push_message(user_id, template_message)
    else:
        datetime_picker_action = DatetimePickerTemplateAction(
            label="日時を選択", data=f"action=schedule&user_message={user_message}", mode="datetime",
            initial=initial_date, max=max_date, min=min_date
        )
        template_message = TemplateSendMessage(
            alt_text="予定日時選択メッセージ",
            template=ButtonsTemplate(
                text="その予定の日時を選んでください。", actions=[datetime_picker_action]
            )
        )
        line_bot_api.push_message(user_id, template_message)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
