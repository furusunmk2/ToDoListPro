from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, TemplateSendMessage, ButtonsTemplate, DatetimePickerTemplateAction
import os
from dotenv import load_dotenv

# Google Generative AI（Gemini）ライブラリのインポート
try:
    import google.generativeai as genai
    genai_available = True
except ImportError as e:
    print(f"Google Generative AI module not found: {e}")
    genai_available = False

# Load .env file
load_dotenv()

# Get environment variables
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Initialize Google Generative AI (Gemini)
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

    print(f"Request body: {body}")
    print(f"X-Line-Signature: {signature}")

    if not signature:
        abort(400, "Missing X-Line-Signature header")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("InvalidSignatureError: Invalid signature")
        abort(400, "Invalid signature")

    return 'OK'

# Handle TextMessage events
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text.strip()
    user_id = event.source.user_id  # ユーザーIDを取得
    response_text = ""

    # プロンプトの設定（敬語変換）
    prompt = f"""以下の文章を敬語表現に変換してください。
元の文章:
{user_message}
敬語表現:
"""
    print(f"Generated Prompt: {prompt}")

    # Google Generative AIを使用して応答を生成
    try:
        if gemini_pro:
            response = gemini_pro.generate_content(prompt)
            print(f"GenerateContentResponse: {response}")

            if response and response.candidates:
                response_text = response.candidates[0]["output"]  # 最初の候補のテキスト
            else:
                response_text = "敬語変換ができませんでした。"
        else:
            response_text = "AIサービスが利用できません。"
    except Exception as e:
        print(f"Error during AI content generation: {e}")
        response_text = f"エラーが発生しました: {str(e)}"

    # 応答をユーザーに送信
    print(f"Final Response Text: {response_text}")
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=response_text)
    )

    # ユーザーに日時選択ボタンを送信
    send_datetimepicker_message(user_id)

# Send a datetime picker message
def send_datetimepicker_message(user_id):
    # DatetimePickerアクションの作成
    datetime_picker_action = DatetimePickerTemplateAction(
        label="Select date",
        data="storeId=12345",
        mode="datetime",
        initial="2017-12-25T00:00",
        max="2018-01-24T23:59",
        min="2017-12-25T00:00"
    )

    # ボタンテンプレートメッセージの作成
    template_message = TemplateSendMessage(
        alt_text="日時選択メッセージ",
        template=ButtonsTemplate(
            text="日時を選んでください",
            actions=[datetime_picker_action]
        )
    )

    # メッセージを送信
    try:
        line_bot_api.push_message(user_id, template_message)
        print(f"Datetime picker message sent to user: {user_id}")
    except Exception as e:
        print(f"Error while sending datetime picker message: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
