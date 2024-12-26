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

try:
    import google.generativeai as genai
    genai_available = True
except ImportError as e:
    print(f"Google Generative AI module not found: {e}")
    genai_available = False

# .envファイルの読み込み
load_dotenv()

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
Session = sessionmaker(bind=engine)
session = Session()

# LINEの設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if genai_available and GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        gemini_pro = genai.GenerativeModel("gemini-pro")
        print("Google Generative AI configured successfully.")
    except Exception as e:
        gemini_pro = None
        print(f"Failed to configure Google Generative AI: {e}")
else:
    gemini_pro = None

app = Flask(__name__)

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN または LINE_CHANNEL_SECRET が設定されていません")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

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

    # 予定確認の場合
    if user_message == "予定確認":
        # 日時の計算
        JST = timezone(timedelta(hours=9))
        now_jst = datetime.now(JST)
        today = now_jst
        initial_date = today.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M")

        # 1年前と1年後の日時を計算
        min_date = (today - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年前
        max_date = (today + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年後S

        # 日時選択のためのアクションを送信
        datetime_picker_action = DatetimePickerTemplateAction(
            label="日付を選ぶにゃ",
            data=f"action=check_schedule&user_id={user_id}",
            mode="datetime",
            initial=initial_date,
            max=max_date,
            min=min_date
        )
        template_message = TemplateSendMessage(
            alt_text="日時選択メッセージ",
            template=ButtonsTemplate(
                text="確認したい日はいつだにゃ？",
                actions=[datetime_picker_action]
            )
        )

        try:
            line_bot_api.push_message(user_id, template_message)
        except Exception as e:
            print(f"日時選択メッセージの送信エラー: {e}")
    elif user_message == "日報作成":
        # 日時の計算
        JST = timezone(timedelta(hours=9))
        now_jst = datetime.now(JST)
        today = now_jst
        initial_date = today.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M")

        # 1年前と1年後の日時を計算
        min_date = (today - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年前
        max_date = (today + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年後S

        # 日時選択のためのアクションを送信
        datetime_picker_action = DatetimePickerTemplateAction(
            label="日付を選ぶにゃ",
            data=f"action=generate_report&user_id={user_id}",
            mode="datetime",
            initial=initial_date,
            max=max_date,
            min=min_date
        )
        template_message = TemplateSendMessage(
            alt_text="日時選択メッセージ",
            template=ButtonsTemplate(
                text="いつの日報が必要だにゃ？",
                actions=[datetime_picker_action]
            )
        )

        try:
            line_bot_api.push_message(user_id, template_message)
        except Exception as e:
            print(f"日時選択メッセージの送信エラー: {e}")
    # 予定入力の場合
    else:
        # 日時の選択
        JST = timezone(timedelta(hours=9))
        now_jst = datetime.now(JST)
        today = now_jst
        initial_date = today.replace(minute=0, second=0).strftime("%Y-%m-%dT%H:%M")

        # 1年前と1年後の日時を計算
        min_date = (today - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年前
        max_date = (today + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M")  # 1年後

        # 日時選択のためのアクションを送信
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
            print(f"日時選択メッセージの送信エラー: {e}")

# Postbackイベントの処理
@handler.add(PostbackEvent)
def handle_postback(event):
    if "action=schedule" in event.postback.data:
       # ユーザーメッセージと日時を取得
        data_parts = event.postback.data.split("&")
        user_message = None
        for part in data_parts:
            if part.startswith("user_message="):
                user_message = part.split("=")[-1]
        schedule_datetime = event.postback.params.get('datetime', '不明')

        # データベースに保存
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
                    text=f"{user_message} の予定を {schedule_datetime} に保存しました。"
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
            print(f"確認メッセージ送信時のエラー: {e}")
    if "action=check_schedule" in event.postback.data:
        # ユーザーが選んだ日付を取得
        selected_date_str = event.postback.params.get('datetime', '不明')
        if selected_date_str != '不明':
            selected_date = datetime.fromisoformat(selected_date_str).date()

            # 予定をデータベースから取得し、選択した日付と一致するかチェック
            schedules = session.query(Schedule).filter(
                Schedule.scheduled_datetime >= selected_date,
                Schedule.scheduled_datetime < selected_date + timedelta(days=1)
            ).order_by(Schedule.scheduled_datetime).all()

            # 日付を上部に追加
            header_message = f"📅 {selected_date.strftime('%Y年%m月%d日')} の予定一覧:\n"

            if schedules:
                schedule_messages = [
                    f"{schedule.scheduled_datetime.strftime('%H:%M')} - {schedule.message}" for schedule in schedules
                ]
                response_message = header_message + "\n".join(schedule_messages)
            else:
                response_message = header_message + "その日に予定はありません。"

            confirmation_message = TextSendMessage(text=response_message)
        else:
            confirmation_message = TextSendMessage(text="日付の取得に失敗しました。")

        try:
            line_bot_api.reply_message(event.reply_token, confirmation_message)
        except Exception as e:
            print(f"確認メッセージ送信時のエラー: {e}")

    if "action=generate_report" in event.postback.data:

        # 日報作成処理
        selected_date_str = event.postback.params.get('datetime', '不明')
        if selected_date_str != '不明':
            selected_date = datetime.fromisoformat(selected_date_str).date()

            # その日のスケジュールを取得
            schedules = session.query(Schedule).filter(
                Schedule.scheduled_datetime >= selected_date,
                Schedule.scheduled_datetime < selected_date + timedelta(days=1)
            ).order_by(Schedule.scheduled_datetime).all()

            if schedules:
                # スケジュールを基に日報を生成
                schedule_text = "\n".join(
                    [f"{schedule.scheduled_datetime.strftime('%H:%M')} - {schedule.message}" for schedule in schedules]
                )
                report_text = f"{selected_date.strftime('%Y年%m月%d日')}の日報:\n\n" + schedule_text

                # Gemini API等を使用する場合はここで呼び出す
                # 例: report_text = gemini_generate_report(schedule_text)
            else:
                report_text = f"{selected_date.strftime('%Y年%m月%d日')} に予定がないため、日報を生成できません。"
            
            prompt = f"""

元の文章を参照して以下の形式で医療記録を生成してください。
'''
【食生活、清潔、排泄、睡眠、生活リズム、部屋の整頓等】
生成した文章
【精神状態】 
生成した文章 
【服薬等の状況】
生成した文章
【作業、対人関係について】 
生成した文章
【その他】※無い場合もあります
生成した文章  ※無い場合もあります
'''

利用者様は精神障害や発達障害を抱える方で障碍者向けグループホームに通いながら、平日は作業所へ通っています。
条件が5点あります。
"【】"で囲まれた文は変更しないでください。
その他の文は文意は変更せずに文章を変更してください。
２００文字程度ごとに誤字を作ってください
ですます調は絶対に使わず、語尾は体言止めか形容詞止めか『いる。』か『ある。』か『あり。』か『ない。』のみを使ってください。

元の文章:
{report_text}
生成した文章:
"""
            print(f"Generated Prompt: {prompt}")  # プロンプトをデバッグ出力

            try:
                # Google Generative AIで応答を生成
                model = genai.GenerativeModel('gemini-pro')
                response = model.generate_content(f"{prompt}")
                print(f"GenerateContentResponse: {response}")  # レスポンス全体をデバッグ出力
                    
                # レスポンスが存在し、候補が含まれている場合に処理を続行
                # 応答候補が存在する場合
                if response and response.candidates:
                    # 最初の候補のテキスト部分を取得
                    first_candidate = response.candidates[0]
                    response_text = first_candidate.content.parts[0].text  # ここで属性を利用
                    print(f"First Candidate: {first_candidate}")  # 候補を詳細にデバッグ
                    # parts配列から最初のテキストを取得
                    response_text = first_candidate.content.parts[0].text
                    print(f"Generated Text: {response_text}")  # 応答テキストをデバッグ出力
                else:
                    print("No candidates found in the response.")  # 応答が空の場合
                    response_text = "AIからの応答が生成されませんでした。"
            except AttributeError as e:
                print(f"AttributeError in response handling: {e}")
                response_text = "AI応答の処理中にエラーが発生しました。"
            except Exception as e:
                print(f"Unexpected error during AI content generation: {e}")
                response_text = f"AI応答の生成中にエラーが発生しました: {str(e)}"






            confirmation_message = TextSendMessage(text=report_text)
        else:
            confirmation_message = TextSendMessage(text="日付の取得に失敗しました。")

        try:
            line_bot_api.reply_message(event.reply_token, confirmation_message)
        except Exception as e:
            print(f"日報生成メッセージ送信時のエラー: {e}")

        
        
        
        

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
