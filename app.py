from sqlalchemy import and_

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

        # Save to database if valid datetime
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

        # Handle schedule summary
        if "action=check_schedule" in event.postback.data:
            # Extract the specified date
            date_parts = event.postback.data.split("&")
            specified_date = None
            for part in date_parts:
                if part.startswith("specified_date="):
                    specified_date = part.split("=")[-1]

            if specified_date:
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
            
        try:
            line_bot_api.reply_message(event.reply_token, confirmation_message)
        except Exception as e:
            print(f"Error while sending confirmation message: {e}")
