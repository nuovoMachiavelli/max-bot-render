import asyncio
from datetime import datetime
from google_sheets import async_open, async_worksheet, async_get_all_values, async_append_rows, async_batch_update
from max_api import MaxClient
from config import MAIN_SHEET_ID, MANAGER_SHEETS, ADMIN_USER_ID

max_client = MaxClient()

def normalize_phone(raw):
    if not raw:
        return None
    s = ''.join(filter(str.isdigit, str(raw).strip()))
    if len(s) == 11 and s.startswith('8'):
        s = '7' + s[1:]
    elif len(s) == 10:
        s = '7' + s
    return s if len(s) == 11 and s.startswith('7') else None

# ---------- Привязка пользователя ----------
async def process_phone(phone_norm: str, user_id: int, message_text_callback=None):
    """
    Ищет номер в таблицах менеджеров, затем в Clients.
    Если находит в менеджерах – обновляет/добавляет в Clients с привязкой.
    """
    print(f"\n=== DEBUG ПРИВЯЗКА ===\nНомер: {phone_norm} | MAX User ID: {user_id}")
    try:
        spreadsheet = await async_open(MAIN_SHEET_ID)
        clients_ws = await async_worksheet(spreadsheet, "Clients")
        clients_values = await async_get_all_values(clients_ws)

        # Поиск в таблицах менеджеров
        found_in = None
        region = ""
        client_name = ""
        for idx, sid in enumerate(MANAGER_SHEETS, 1):
            try:
                s = await async_open(sid)
                sheet = await async_worksheet(s, "Общий")
                data = await async_get_all_values(sheet)
                for row in data[1:]:
                    if not isinstance(row, (list, tuple)) or len(row) < 6:
                        continue
                    phone_raw = str(row[4]) if len(row) > 4 else ""
                    if normalize_phone(phone_raw) == phone_norm:
                        found_in = f"Таблица {idx}"
                        region = str(row[1]).strip() if len(row) > 1 else ""
                        client_name = str(row[5]).strip() if len(row) > 5 else ""
                        break
                if found_in:
                    break
            except Exception as e:
                print(f"Ошибка в таблице {idx}: {e}")
                continue

        # Поиск в Clients
        row_index = None
        for i, row in enumerate(clients_values[1:], start=2):
            if isinstance(row, (list, tuple)) and len(row) > 0 and normalize_phone(row[0]) == phone_norm:
                row_index = i
                break

        if found_in:
            if row_index:
                # Обновляем существующую строку: B (user_id), C (имя), D (статус), E (источник), F (регион)
                await async_batch_update(clients_ws, [
                    {"range": f"B{row_index}", "values": [[user_id]]},
                    {"range": f"C{row_index}", "values": [[client_name]]},
                    {"range": f"D{row_index}", "values": [["привязан"]]},
                    {"range": f"E{row_index}", "values": [[found_in]]},
                    {"range": f"F{row_index}", "values": [[region]]}
                ])
                await max_client.send_message(user_id, "✅ Вы успешно привязаны! Данные обновлены.")
            else:
                # Добавляем новую строку
                await async_append_rows(clients_ws, [[
                    phone_norm, user_id, client_name, "привязан", found_in, region
                ]])
                await max_client.send_message(user_id, "✅ Вы успешно привязаны!")
            return
        else:
            await max_client.send_message(user_id, "❌ К сожалению, ваш номер не найден в базе.")
    except Exception as e:
        print(f"CRITICAL ERROR в process_phone: {e}")
        await max_client.send_message(user_id, "❌ Ошибка при обработке номера.")

# ---------- Команда /sync (только админ) ----------
async def sync_command(admin_id: int):
    """Обновляет ФИО, регион, источник в Clients из таблиц менеджеров (batch_update)."""
    try:
        await max_client.send_message(admin_id, "🔄 Запускаю оптимизированную синхронизацию (batch_update)...")
        spreadsheet = await async_open(MAIN_SHEET_ID)
        clients_ws = await async_worksheet(spreadsheet, "Clients")
        clients_values = await async_get_all_values(clients_ws)

        # Собираем существующие телефоны и номера строк
        existing = {}
        for i, row in enumerate(clients_values[1:], start=2):
            phone_norm = normalize_phone(row[0]) if len(row) > 0 else None
            if phone_norm:
                existing[phone_norm] = i

        new_rows = []
        batch_updates = []  # для обновления C, E, F
        updated = 0
        added = 0

        for idx, sid in enumerate(MANAGER_SHEETS, 1):
            await max_client.send_message(admin_id, f"→ Проверяю таблицу менеджера {idx}/7...")
            try:
                s = await async_open(sid)
                sheet = await async_worksheet(s, "Общий")
                data = await async_get_all_values(sheet)
                for row in data[1:]:
                    if not isinstance(row, (list, tuple)) or len(row) < 6:
                        continue
                    phone_raw = str(row[4]) if len(row) > 4 else ""
                    region = str(row[1]).strip() if len(row) > 1 else ""
                    client_name = str(row[5]).strip() if len(row) > 5 else ""
                    phone_norm = normalize_phone(phone_raw)
                    if not phone_norm:
                        continue
                    if phone_norm in existing:
                        r = existing[phone_norm]
                        batch_updates.append({
                            "range": f"C{r}:F{r}",
                            "values": [[client_name, None, f"Таблица {idx}", region]]
                        })
                        updated += 1
                    else:
                        new_rows.append([phone_norm, "", client_name, "не привязан", f"Таблица {idx}", region])
                        added += 1
            except Exception as e:
                await max_client.send_message(admin_id, f"⚠️ Ошибка в таблице {idx}: {str(e)[:100]}")
                continue

        if batch_updates:
            await async_batch_update(clients_ws, batch_updates)
        if new_rows:
            await async_append_rows(clients_ws, new_rows)

        await max_client.send_message(admin_id, f"""✅ УМНАЯ СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА!
Добавлено новых: {added}
Обновлено ФИО/регион/источник: {updated}""")
    except Exception as e:
        print(f"SYNC ERROR: {e}")
        await max_client.send_message(admin_id, f"❌ Ошибка синхронизации: {str(e)}")

# ---------- Команда /broadcast (только админ) - ИСПРАВЛЕНА ----------
async def broadcast_command(admin_id: int):
    """Рассылка из листа 'Рассылка': текст сообщения берётся ТОЛЬКО из колонки H (индекс 7). Пустые сообщения пропускаются."""
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
            if len(row) < 9:
                continue
            status = str(row[8]).strip().lower() if len(row) > 8 else ""
            if status not in ("новый", ""):
                continue

            # ----- БЕРЁМ ТЕКСТ ТОЛЬКО ИЗ КОЛОНКИ H (индекс 7) -----
            message_text = str(row[7]).strip() if len(row) > 7 and row[7] else ""

            # Если текст пустой – пропускаем, ставим статус "нет текста"
            if not message_text:
                status_updates.append({"range": f"I{i}", "values": [["нет текста"]]})
                skipped_no_text += 1
                batch_counter += 1
                continue

            phone_raw = str(row[2]) if len(row) > 2 else ""
            phone_norm = normalize_phone(phone_raw)
            if not phone_norm:
                continue

            user_id = phone_to_user.get(phone_norm)
            if not user_id:
                status_updates.append({"range": f"I{i}", "values": [["нет MAX ID"]]})
                skipped_no_id += 1
                batch_counter += 1
            else:
                try:
                    await max_client.send_message(user_id, message_text)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    status_updates.append({"range": f"I{i}", "values": [["отправлено"]]})
                    time_updates.append({"range": f"J{i}", "values": [[now]]})
                    sent += 1
                    batch_counter += 2
                    await asyncio.sleep(0.5)
                except Exception as e:
                    err_text = str(e)[:80]
                    status_updates.append({"range": f"I{i}", "values": [[f"ошибка: {err_text}"]]})
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
