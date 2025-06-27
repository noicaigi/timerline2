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
    res2 =  await db.initialize_boss_respawns()
    if not res1 or not res2:
        backend_logger.error(f"Lỗi: không thể khởi tạo cơ sở dữ liệu")


async def calculate_respawn_datetime(kill_datetime, now, boss_name, is_new_epoch: bool = False):
    if kill_datetime > now:  # Nếu thời điểm giết boss là ngày hôm qua
        kill_datetime -= timedelta(days=1)

    if is_new_epoch:
        interval_raw = respawn_intervals[boss_name][1]
    else:
        interval_raw = respawn_intervals[boss_name][0]
    interval = timedelta(hours=interval_raw)
    respawn_datetime = kill_datetime + interval
    return respawn_datetime, interval


async def set_timer(
        chat_id: str,
        boss_name: str,
        kill_time_str: str | None,
        user_id: str,
        event,
        is_new_epoch: bool = False,
    ):
    if boss_name not in respawn_intervals:
        await event.reply(f"❌ Boss **{boss_name}** không được tìm thấy.")
        backend_logger.error(
            f"Trong chat {chat_id} người dùng {user_id} dùng sai lệnh "
            f"`{event.message.message}`. "
            f"Lỗi: tên boss không tồn tại"
        )
        return

    if kill_time_str is None:
        now = vietnam_tz.localize(datetime.now())
        kill_datetime = now
    else:
        try:
            kill_time = datetime.strptime(kill_time_str, "%H:%M").time()
        except ValueError:
            await event.reply("❌ Định dạng thời gian không đúng. Hãy dùng HH:MM.")
            backend_logger.error(
                f"Trong chat {chat_id} người dùng {user_id} dùng sai lệnh "
                f"`{event.message.message}`. "
                f"Lỗi: định dạng thời gian sai"
            )
            return
        else:
            now = vietnam_tz.localize(datetime.now())
            kill_datetime = user_to_system_tz(datetime.combine(now.date(), kill_time))

    respawn_datetime, interval = await calculate_respawn_datetime(
        kill_datetime,
        now,
        boss_name,
        is_new_epoch,
    )

    if respawn_datetime < now:
        await event.reply(
            f"❌ Boss **{boss_name}** đã hồi sinh, nhanh lên đi đánh!"
        )
        backend_logger.error(
            f"Trong chat {chat_id} người dùng {user_id} cố tạo timer đã hết hạn"
        )
        return

    timer = await db.add_timer(
        user_id=user_id,
        chat_id=chat_id,
        boss_name=boss_name,
        respawn_time=respawn_datetime
    )
    if not timer:
        await event.reply("❌ Lỗi truy cập cơ sở dữ liệu")
        backend_logger.error(
            "Lỗi khi thêm timer vào cơ sở dữ liệu trong hàm 'add_timer'"
        )
        return
    backend_logger.success(
        f"Trong chat {chat_id} người dùng {user_id} đã tạo timer {timer.timer_id}"
    )

    remaining_time = respawn_datetime - now
    wait_seconds = remaining_time.total_seconds()
    remaining_formatted_time = seconds_to_hh_mm(wait_seconds)

    if is_new_epoch:
        await asyncio.sleep(wait_seconds)
        if not await db._get_timer(timer):
            backend_logger.info(f"Timer {timer.timer_id} đã bị xoá từ trước")
            return

        await event.reply(f"✅ Boss **{boss_name}** đã hồi sinh, mau đi đánh nhé!")
        backend_logger.success(
            f"Trong chat {chat_id} người dùng {user_id} nhận thông báo "
            f"từ timer {timer.timer_id}"
        )

        timer_id = timer.timer_id
        res = await db.delete_timer(
            user_id=user_id,
            timer_id=timer_id,
        )
        if not res:
            await event.reply("❌ Lỗi truy cập cơ sở dữ liệu")
            backend_logger.error(
                "Lỗi khi xoá timer trong hàm 'set_timer' với is_new_epoch"
            )
            return

        backend_logger.success(
            f"Trong chat {chat_id} người dùng {user_id} tự động xoá timer {timer_id}"
        )
        return

    while True:
        await event.reply(
            f"✅ Đã thiết lập timer:\n{system_to_user_tz(timer.respawn_time)} — "
            f"**{timer.boss_name}** ({remaining_formatted_time}) — `{timer.timer_id}`\n"
        )

        await asyncio.sleep(wait_seconds)
        if not await db._get_timer(timer):
            backend_logger.info(f"Timer {timer.timer_id} đã bị xoá từ trước")
            return

        await event.reply(f"✅ Boss **{boss_name}** đã hồi sinh, mau đi đánh nhé!")
        backend_logger.success(
            f"Trong chat {chat_id} người dùng {user_id} nhận thông báo "
            f"từ timer {timer.timer_id}"
        )
        await asyncio.sleep(300)
        if not await db._get_timer(timer):
            backend_logger.info(f"Timer {timer.timer_id} đã bị xoá từ trước")
            return

        respawn_datetime += interval + timedelta(seconds=300)
        timer = await db.update_timer(timer, respawn_datetime)
        if not timer:
            await event.reply("❌ Lỗi truy cập cơ sở dữ liệu")
            backend_logger.error(
                "Lỗi khi cập nhật timer trong hàm 'add_timer'"
            )
            return

        backend_logger.success(
            f"Trong chat {chat_id} người dùng {user_id} tự động cập nhật timer {timer.timer_id}"
        )
        wait_seconds = interval.total_seconds()
        remaining_formatted_time = seconds_to_hh_mm(wait_seconds)