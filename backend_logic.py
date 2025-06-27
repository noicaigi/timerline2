import asyncio
from datetime import datetime, timedelta
from itertools import groupby, tee

import pytz
from tzlocal import get_localzone

from database.db_logic import DataBaseAPI
from intervals import respawn_intervals
from utils.time_helper import user_to_system_tz, system_to_user_tz, seconds_to_hh_mm
from utils.logger import backend_logger

db = DataBaseAPI()
vietnam_tz = pytz.timezone("Asia/Ho_Chi_Minh")
system_tz = vietnam_tz


async def init_db():
    res1 = await db.create_tables()
    res2 = await db.initialize_boss_respawns()
    if not res1 or not res2:
        backend_logger.error(f"Lỗi: không thể khởi tạo cơ sở dữ liệu")


async def calculate_respawn_datetime(kill_datetime, now, boss_name, is_new_epoch: bool = False):
    if kill_datetime > now:
        kill_datetime -= timedelta(days=1)

    interval_raw = respawn_intervals[boss_name][1] if is_new_epoch else respawn_intervals[boss_name][0]
    interval = timedelta(hours=interval_raw)
    respawn_datetime = kill_datetime + interval
    return respawn_datetime, interval


async def set_timer(chat_id: str, boss_name: str, kill_time_str: str | None, user_id: str, event, is_new_epoch: bool = False):
    if boss_name not in respawn_intervals:
        await event.reply(f"❌ Boss **{boss_name}** không tồn tại.")
        backend_logger.error(f"Trong chat {chat_id} Người dùng {user_id} nhập sai tên boss.")
        return

    now = system_tz.localize(datetime.now())
    kill_datetime = now if not kill_time_str else user_to_system_tz(datetime.combine(now.date(), datetime.strptime(kill_time_str, "%H:%M").time()))

    respawn_datetime, interval = await calculate_respawn_datetime(kill_datetime, now, boss_name, is_new_epoch)

    if respawn_datetime < now:
        await event.reply(f"❌ Boss **{boss_name}** đã hồi sinh rồi, nhanh tay tiêu diệt đi!")
        return

    timer = await db.add_timer(user_id=user_id, chat_id=chat_id, boss_name=boss_name, respawn_time=respawn_datetime)
    if not timer:
        await event.reply("❌ Lỗi cơ sở dữ liệu khi lưu hẹn giờ")
        return

    remaining_time = respawn_datetime - now
    wait_seconds = remaining_time.total_seconds()
    time_to_notification = wait_seconds - 180
    remaining_formatted_time = seconds_to_hh_mm(wait_seconds)

    if is_new_epoch:
        await asyncio.sleep(time_to_notification)
        if not await db._get_timer(timer): return
        await event.reply(f"‼️ Boss **{boss_name}** sẽ hồi sinh trong 3 phút, chuẩn bị nhé!")
        await asyncio.sleep(180)
        if not await db._get_timer(timer): return
        await event.reply(f"✅ Boss **{boss_name}** đã hồi sinh!")
        await db.delete_timer(user_id=user_id, timer_id=timer.timer_id)
        return

    while True:
        await event.reply(f"✅ Đã đặt hẹn giờ:\n{system_to_user_tz(timer.respawn_time)} — **{timer.boss_name}** ({remaining_formatted_time}) — `{timer.timer_id}`")
        if time_to_notification > 0:
            await asyncio.sleep(time_to_notification)
            if not await db._get_timer(timer): return
            await event.reply(f"‼️ Boss **{boss_name}** sẽ hồi sinh trong 3 phút!")
            await asyncio.sleep(180)
        else:
            await asyncio.sleep(wait_seconds)
        if not await db._get_timer(timer): return
        await event.reply(f"✅ Boss **{boss_name}** đã hồi sinh!")
        respawn_datetime += interval + timedelta(seconds=60)
        timer = await db.update_timer(timer, respawn_datetime)
        if not timer:
            await event.reply("❌ Lỗi cập nhật hẹn giờ")
            return
        wait_seconds = interval.total_seconds()
        time_to_notification = wait_seconds - 180
        remaining_formatted_time = seconds_to_hh_mm(wait_seconds)


async def get_bosses(chat_id: str, user_id: str, event):
    text_strings = ["Danh sách tất cả boss:\n"]
    for boss in respawn_intervals:
        text_strings.append(f"`{boss:<20}` | {respawn_intervals[boss][0]} giờ")
    await event.reply("\n".join(text_strings))


async def delete_timer(user_id: str, chat_id: str, timer_id: str, event):
    res = await db.delete_timer(user_id, timer_id)
    if res == 'alien':
        await event.reply("❌ Không thể xóa hẹn giờ của người khác")
        return
    if not res:
        await event.reply("❌ Lỗi truy cập cơ sở dữ liệu")
        return
    await event.reply(f"✅ Đã xóa hẹn giờ ID {timer_id}")


async def delete_all_timers(chat_id: str, user_id: str, event):
    res = await db.delete_all_timers_in_chat(chat_id)
    if res == 'no_timers':
        await event.reply("❌ Không có hẹn giờ nào để xóa")
        return
    if not res:
        await event.reply("❌ Lỗi cơ sở dữ liệu khi xóa tất cả")
        return
    await event.reply("✅ Đã xóa tất cả hẹn giờ")


async def get_chat_timers(chat_id: str, timer_numbers: int, user_id: str, event):
    user_info = await db.get_userinfo(user_id)
    nickname, firstname = user_info
    timers = await db.get_all_chat_timers(user_id, chat_id) if timer_numbers < 1 else await db.get_chat_timers(user_id, chat_id, timer_numbers)

    if timers is False:
        await event.reply("❌ Lỗi truy cập cơ sở dữ liệu")
        return
    if not timers:
        await event.reply("Hiện tại không có hẹn giờ nào")
        return

    now = system_tz.localize(datetime.now())
    text_strings = ["**Boss sắp xuất hiện:**\n"]
    for timer in timers:
        remaining_time = (timer.respawn_time - now).total_seconds()
        remaining_formatted_time = seconds_to_hh_mm(remaining_time)
        text_strings.append(f"{system_to_user_tz(timer.respawn_time)} — **{timer.boss_name}** ({remaining_formatted_time}) — `{timer.timer_id}`")
    await event.reply("\n".join(text_strings))


async def epochs_timers_start(chat_id: str, user_id: str, event):
    bosses = await db.get_all_boss_respawns(user_id=user_id)
    if bosses is False:
        await event.reply("❌ Lỗi truy cập cơ sở dữ liệu")
        return

    tasks = [asyncio.create_task(set_timer(chat_id=chat_id, boss_name=boss.boss_name, kill_time_str=None, user_id=user_id, event=event, is_new_epoch=True)) for boss in bosses]

    await event.reply("✅ Đã đặt hẹn giờ cho tất cả boss. Sử dụng /get để xem thông tin.")
    await asyncio.gather(*tasks)


async def start_chat(chat_id: str, chat, participants, event):
    for p in participants:
        user_id, nickname, firstname = str(p.id), p.username, p.first_name
        await db.add_userinfo(user_id, nickname, firstname)

    await event.reply("Xin chào! Tôi sẽ giúp bạn không bỏ lỡ thời gian xuất hiện của boss. Dùng /help để xem các lệnh hỗ trợ.")
