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
Session = scoped_session(sessionmaker(bind=engine))

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

# ルート追加
@app.route("/")
def index():
    return "このサービスはLINEからのみ利用可能です。"

def calculate_datetime_range():
    """日時の初期値、最小値、最大値を計算する"""
    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)
    initial_date = now_jst.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M")
    min_date = (now_jst - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")
    max_date = (now_jst + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")
    return initial_date, min_date, max_date

def generate_report_with_ai(prompt, model):
    """Gemini APIを使用して日報を生成する"""
    try:
        response = model.generate_content(prompt)
        if response and hasattr(response, 'candidates') and len(response.candidates) > 0:
            return response.candidates[0].get('content', "生成エラー").strip()
        return "AI応答がありませんでした。"
    except Exception as e:
        logger.error(f"AI生成中にエラー: {e}")
        return "AI生成中にエラーが発生しました。"

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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id
    initial_date, min_date, max_date = calculate_datetime_range()

    if user_message == "予定確認" or user_message == "日報作成":
        action_data = "check_schedule" if user_message == "予定確認" else "generate_report"
        datetime_picker_action = DatetimePickerTemplateAction(
            label="日付を選ぶにゃ",
            data=f"action={action_data}&user_id={user_id}",
            mode="datetime",
            initial=initial_date,
            max=max_date,
            min=min_date
        )
        template_message = TemplateSendMessage(
            alt_text="日時選択メッセージ",
            template=ButtonsTemplate(
                text="確認したい日はいつだにゃ？" if user_message == "予定確認" else "いつの日報が必要だにゃ？",
                actions=[datetime_picker_action]
            )
        )
        try:
            line_bot_api.push_message(user_id, template_message)
        except Exception as e:
            logger.error(f"日時選択メッセージの送信エラー: {e}")
    else:
        template_message = TextSendMessage(text="無効なメッセージです。")
        try:
            line_bot_api.push_message(user_id, template_message)
        except Exception as e:
            logger.error(f"メッセージ送信エラー: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
