async def broadcast_command(admin_id: int):
    """Рассылка из листа 'Рассылка': текст из колонки H (сообщение). Статус в колонке J, время в K."""
    await max_client.send_message(admin_id, "🚀 Запускаю рассылку (только из колонки 'сообщение')...")
    try:
        spreadsheet = await async_open(MAIN_SHEET_ID)
        rassylka_ws = await async_worksheet(spreadsheet, "Рассылка")
        clients_ws = await async_worksheet(spreadsheet, "Clients")

        data = await async_get_all_values(rassylka_ws)
        clients_data = await async_get_all_values(clients_ws)

        # Маппинг телефон → max_user_id
        phone_to_user = {}
        for row in clients_data[1:]:
            if len(row) > 1:
                phone_norm = normalize_phone(row[0])
                if phone_norm:
                    user_id_str = str(row[1]).strip()
                    if user_id_str and user_id_str != "0":
                        try:
                            phone_to_user[phone_norm] = int(user_id_str)
                        except:
                            pass

        status_updates = []
        time_updates = []
        sent = 0
        skipped_no_text = 0
        skipped_no_id = 0
        errors = 0
        batch_counter = 0

        for i, row in enumerate(data[1:], start=2):
            # Проверяем, что строк достаточно (минимум до колонки J статус)
            if len(row) < 10:
                continue

            # Статус в колонке J (индекс 9)
            status = str(row[9]).strip().lower() if len(row) > 9 else ""
            if status not in ("новый", ""):
                continue

            # Текст сообщения из колонки H (индекс 7)
            message_text = str(row[7]).strip() if len(row) > 7 and row[7] else ""

            if not message_text:
                status_updates.append({"range": f"J{i}", "values": [["нет текста"]]})
                skipped_no_text += 1
                batch_counter += 1
                continue

            # Телефон в колонке C (индекс 2)
            phone_raw = str(row[2]) if len(row) > 2 else ""
            phone_norm = normalize_phone(phone_raw)
            if not phone_norm:
                continue

            user_id = phone_to_user.get(phone_norm)
            if not user_id:
                status_updates.append({"range": f"J{i}", "values": [["нет MAX ID"]]})
                skipped_no_id += 1
                batch_counter += 1
            else:
                try:
                    await max_client.send_message(user_id, message_text)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    status_updates.append({"range": f"J{i}", "values": [["отправлено"]]})
                    time_updates.append({"range": f"K{i}", "values": [[now]]})
                    sent += 1
                    batch_counter += 2
                    await asyncio.sleep(0.5)
                except Exception as e:
                    err_text = str(e)[:80]
                    status_updates.append({"range": f"J{i}", "values": [[f"ошибка: {err_text}"]]})
                    errors += 1
                    batch_counter += 1

            if batch_counter >= 50:
                if status_updates:
                    await async_batch_update(rassylka_ws, status_updates)
                    status_updates = []
                if time_updates:
                    await async_batch_update(rassylka_ws, time_updates)
                    time_updates = []
                batch_counter = 0
                await asyncio.sleep(1)

        if status_updates:
            await async_batch_update(rassylka_ws, status_updates)
        if time_updates:
            await async_batch_update(rassylka_ws, time_updates)

        await max_client.send_message(admin_id, f"""🎉 РАССЫЛКА ЗАВЕРШЕНА!
✅ Отправлено: {sent}
⏭ Пропущено (нет текста в H): {skipped_no_text}
⏭ Пропущено (нет MAX ID): {skipped_no_id}
❌ Ошибок: {errors}""")
    except Exception as e:
        print(f"BROADCAST ERROR: {e}")
        await max_client.send_message(admin_id, f"❌ Критическая ошибка рассылки: {str(e)}")
