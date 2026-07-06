import asyncio
from datetime import datetime

from google_sheets import (
    async_open,
    async_worksheet,
    async_get_all_values,
    async_append_rows,
    async_batch_update
)

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


# ---------- ПРИВЯЗКА ----------
async def process_phone(phone_norm: str, user_id: int, message_text_callback=None):
    print(f"\n=== DEBUG ПРИВЯЗКА ===\nНомер: {phone_norm} | MAX User ID: {user_id}")

    try:
        spreadsheet = await async_open(MAIN_SHEET_ID)
        clients_ws = await async_worksheet(spreadsheet, "Clients")
        clients_values = await async_get_all_values(clients_ws)

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

        row_index = None
        for i, row in enumerate(clients_values[1:], start=2):
            if isinstance(row, (list, tuple)) and len(row) > 0:
                if normalize_phone(row[0]) == phone_norm:
                    row_index = i
                    break

        if found_in:
            if row_index:
                await async_batch_update(clients_ws, [
                    {"range": f"B{row_index}", "values": [[user_id]]},
                    {"range": f"C{row_index}", "values": [[client_name]]},
                    {"range": f"D{row_index}", "values": [["привязан"]]},
                    {"range": f"E{row_index}", "values": [[found_in]]},
                    {"range": f"F{row_index}", "values": [[region]]}
                ])
                await max_client.send_message(user_id, "✅ Вы успешно привязаны! Данные обновлены.")
            else:
                await async_append_rows(clients_ws, [[
                    phone_norm, user_id, client_name, "привязан", found_in, region
                ]])
                await max_client.send_message(user_id, "✅ Вы успешно привязаны!")
        else:
            await max_client.send_message(user_id, "❌ К сожалению, ваш номер не найден в базе.")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        await max_client.send_message(user_id, "❌ Ошибка при обработке номера")


# ---------- SYNC ----------
async def sync_command(admin_id: int):
    try:
        await max_client.send_message(admin_id, "🔄 Синхронизация...")

        spreadsheet = await async_open(MAIN_SHEET_ID)
        clients_ws = await async_worksheet(spreadsheet, "Clients")
        clients_values = await async_get_all_values(clients_ws)

        existing = {}
        for i, row in enumerate(clients_values[1:], start=2):
            phone_norm = normalize_phone(row[0]) if len(row) > 0 else None
            if phone_norm:
                existing[phone_norm] = i

        new_rows = []
        batch_updates = []
        updated = 0
        added = 0

        for idx, sid in enumerate(MANAGER_SHEETS, 1):
            try:
                s = await async_open(sid)
                sheet = await async_worksheet(s, "Общий")
                data = await async_get_all_values(sheet)

                for row in data[1:]:
                    if len(row) < 6:
                        continue

                    phone_norm = normalize_phone(row[4])
                    if not phone_norm:
                        continue

                    region = str(row[1]).strip()
                    client_name = str(row[5]).strip()

                    if phone_norm in existing:
                        r = existing[phone_norm]
                        batch_updates.append({
                            "range": f"C{r}:F{r}",
                            "values": [[client_name, None, f"Таблица {idx}", region]]
                        })
                        updated += 1
                    else:
                        new_rows.append([
                            phone_norm, "", client_name, "не привязан", f"Таблица {idx}", region
                        ])
                        added += 1

            except Exception as e:
                await max_client.send_message(admin_id, f"Ошибка таблицы {idx}: {e}")

        if batch_updates:
            await async_batch_update(clients_ws, batch_updates)
        if new_rows:
            await async_append_rows(clients_ws, new_rows)

        await max_client.send_message(
            admin_id,
            f"Готово\nДобавлено: {added}\nОбновлено: {updated}"
        )

    except Exception as e:
        await max_client.send_message(admin_id, f"SYNC ERROR: {e}")


# ---------- BROADCAST ----------
async def broadcast_command(admin_id: int):
    await max_client.send_message(admin_id, "🚀 Запускаю рассылку...")

    try:
        spreadsheet = await async_open(MAIN_SHEET_ID)
        rassylka_ws = await async_worksheet(spreadsheet, "Рассылка")
        clients_ws = await async_worksheet(spreadsheet, "Clients")

        data = await async_get_all_values(rassylka_ws)
        clients_data = await async_get_all_values(clients_ws)

        phone_to_user = {}
        for row in clients_data[1:]:
            if len(row) > 1:
                phone_norm = normalize_phone(row[0])
                if phone_norm:
                    try:
                        phone_to_user[phone_norm] = int(row[1])
                    except:
                        pass

        status_updates = []
        time_updates = []

        sent = 0
        skipped = 0
        errors = 0

        for i, row in enumerate(data[1:], start=2):

            if len(row) < 10:
                continue

            status = str(row[9]).strip().lower()
            if status not in ("новый", ""):
                continue

            message_text = str(row[7]).strip()
            if not message_text:
                continue

            phone_norm = normalize_phone(row[2])
            if not phone_norm:
                continue

            user_id = phone_to_user.get(phone_norm)

            if not user_id:
                skipped += 1
                continue

            try:
                await max_client.send_message(user_id, message_text)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                status_updates.append({"range": f"J{i}", "values": [["отправлено"]]})
                time_updates.append({"range": f"K{i}", "values": [[now]]})

                sent += 1
                await asyncio.sleep(0.5)

            except Exception:
                errors += 1

        if status_updates:
            await async_batch_update(rassylka_ws, status_updates)
        if time_updates:
            await async_batch_update(rassylka_ws, time_updates)

        await max_client.send_message(
            admin_id,
            f"Готово\nОтправлено: {sent}\nОшибки: {errors}\nПропущено: {skipped}"
        )

    except Exception as e:
        await max_client.send_message(admin_id, f"BROADCAST ERROR: {e}")


# ---------- НОВАЯ КОМАНДА ----------
async def subscriptions_command(admin_id: int):
    try:
        data = await max_client.get_subscriptions()
        await max_client.send_message(admin_id, f"SUBSCRIPTIONS:\n{data}")
    except Exception as e:
        await max_client.send_message(admin_id, f"ERROR: {e}")
