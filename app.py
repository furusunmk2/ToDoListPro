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
            candidate = response.candidates[0]
            report_text = candidate.get('text', '').strip()

            # アスタリスクを除去する処理を追加
            clean_report = report_text.replace("*", "")
            return clean_report
        else:
            return "AI応答が生成されませんでした。"
    except Exception as e:
        logger.error(f"AI生成中にエラー: {e}")
        return f"AI生成中にエラーが発生しました: {e}"

# 以下のコードは元のコードと同じです（省略）
