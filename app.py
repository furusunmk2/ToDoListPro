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
            return response.candidates[0].text.strip()
        return "AIからの応答が生成されませんでした。"
    except Exception as e:
        logger.error(f"AI生成中にエラー: {e}")
        return f"AI生成中にエラーが発生しました: {e}"

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

# TextMessageイベントの処理
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
        datetime_picker_action = DatetimePickerTemplateAction(
            label="日時を選ぶにゃ",
            data=f"action=schedule&user_message={user_message}",
            mode="datetime",
            initial=initial_date,
            max=max_date,
            min=min_date
        )
        template_message = TemplateSendMessage(
            alt_text="予定日時選択メッセージ",
            template=ButtonsTemplate(
                text="その予定はいつの予定だにゃ？",
                actions=[datetime_picker_action]
            )
        )
        try:
            line_bot_api.push_message(user_id, template_message)
        except Exception as e:
            logger.error(f"日時選択メッセージの送信エラー: {e}")

# Postbackイベントの処理
@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    user_id = event.source.user_id
    if "action=schedule" in data:
        user_message = [part.split("=")[1] for part in data.split("&") if part.startswith("user_message=")][0]
        schedule_datetime = event.postback.params.get('datetime', '不明')

        if user_message and schedule_datetime != '不明':
            with Session() as session:
                try:
                    schedule = Schedule(
                        user_id=user_id,
                        message=user_message,
                        scheduled_datetime=datetime.fromisoformat(schedule_datetime)
                    )
                    session.add(schedule)
                    session.commit()
                    confirmation_message = TextSendMessage(
                        text=f"{user_message} の予定を {schedule_datetime} に保存しました。"
                    )
                except Exception as e:
                    session.rollback()
                    confirmation_message = TextSendMessage(
                        text=f"データベース保存中にエラーが発生しました: {e}"
                    )
        else:
            confirmation_message = TextSendMessage(text="無効なデータが入力されました。")

        try:
            line_bot_api.reply_message(event.reply_token, confirmation_message)
        except Exception as e:
            logger.error(f"確認メッセージ送信時のエラー: {e}")

    if "action=check_schedule" in data or "action=generate_report" in data:
        selected_date_str = event.postback.params.get('datetime', '不明')
        if selected_date_str != '不明':
            selected_date = datetime.fromisoformat(selected_date_str).date()

            with Session() as session:
                schedules = session.query(Schedule).filter(
                    Schedule.scheduled_datetime >= selected_date,
                    Schedule.scheduled_datetime < selected_date + timedelta(days=1)
                ).order_by(Schedule.scheduled_datetime).all()

            if "action=check_schedule" in data:
                schedule_text = "\n".join(
                    [f"{schedule.scheduled_datetime.strftime('%H:%M')} - {schedule.message}" for schedule in schedules]
                ) or "その日に予定はありません。"
                response_message = f"📅 {selected_date.strftime('%Y年%m月%d日')} の予定一覧:\n{schedule_text}"
            else:
                report_text = "\n".join(
                    [f"{schedule.scheduled_datetime.strftime('%H:%M')} - {schedule.message}" for schedule in schedules]
                ) or f"{selected_date.strftime('%Y年%m月%d日')} に予定がないため、日報を生成できません。"
                if gemini_pro:
                    prompt = f"日報生成プロンプト: {report_text}"
                    response_message = generate_report_with_ai(prompt, gemini_pro)
                else:
                    response_message = report_text

            confirmation_message = TextSendMessage(text=response_message)
        else:
            confirmation_message = TextSendMessage(text="日付の取得に失敗しました。")

        try:
            line_bot_api.reply_message(event.reply_token, confirmation_message)
        except Exception as e:
            logger.error(f"確認メッセージ送信時のエラー: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)