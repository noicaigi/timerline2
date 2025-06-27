import asyncio
import signal
import sys

from telethon import events
from telethon.tl.functions.bots import SetBotCommandsRequest, SetBotMenuButtonRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault, BotMenuButtonCommands

from backend_logic import (
    set_timer, 
    init_db, 
    get_bosses, 
    delete_timer, 
    delete_all_timers,
    get_chat_timers,
    epochs_timers_start,
    start_chat,
)

from utils.logger import backend_logger
from utils.get_client import get_client


async def shutdown(signal_name):
    backend_logger.info(f"Nhận tín hiệu thoát {signal_name}")
    tasks = [t for t in asyncio.all_tasks() if not t.done() and t is not asyncio.current_task()]

    backend_logger.info("Đang hủy tất cả các tác vụ đang chờ...")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    backend_logger.info("Tất cả các tác vụ đã bị hủy")

    backend_logger.info("Đang tắt vòng lặp sự kiện...")
    loop = asyncio.get_running_loop()
    loop.stop()


async def main():
    try:
        client = await get_client(as_bot=True)
        backend_logger.success("Bot khởi động thành công")

        async def set_bot_commands():
            commands = [
                BotCommand(command="start", description="Bắt đầu bot"),
                BotCommand(command="set", description="Đặt hẹn giờ"),
                BotCommand(command="get", description="Lấy danh sách hẹn giờ trong nhóm"),
                BotCommand(command="delete", description="Xóa hẹn giờ theo ID"),
                BotCommand(command="bosses", description="Danh sách tất cả boss"),
                BotCommand(command="all_start", description="Bắt đầu hẹn giờ cho tất cả boss"),
                BotCommand(command="help", description="Mô tả lệnh"),
                BotCommand(command="info", description="Thông tin về bot"),
            ]
            await client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(), 
                lang_code='vi', 
                commands=commands
            ))
            await client(SetBotMenuButtonRequest(user_id='self', button=BotMenuButtonCommands()))
            return True

        if await set_bot_commands():
            backend_logger.success("Các lệnh bot đã được thiết lập thành công")

        @client.on(events.NewMessage(pattern=r'/bosses'))
        async def get_bosses_command(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)
            backend_logger.info(f"Trong chat {chat_id} người dùng {user_id} dùng `{event.message.message}`")
            await get_bosses(chat_id=chat_id, user_id=user_id, event=event)

        @client.on(events.NewMessage(pattern=r'/set\s+(.+?)\s*(\d{1,2}:\d{2})?$'))
        async def set_timer_command(event):
            chat_id = str(event.chat_id)
            boss_name = str(event.pattern_match.group(1)).title()
            kill_time_str = event.pattern_match.group(2)
            user_id = str(event.sender_id)

            backend_logger.info(f"Trong chat {chat_id} người dùng {user_id} dùng `{event.message.message}`")
            await set_timer(
                chat_id=chat_id, 
                boss_name=boss_name, 
                kill_time_str=kill_time_str, 
                user_id=user_id,
                event=event,
            )

        @client.on(events.NewMessage(pattern='/all_start'))
        async def epochs_timers_start_command(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)
            await epochs_timers_start(
                chat_id=chat_id,
                user_id=user_id,
                event=event
            )

        @client.on(events.NewMessage(pattern=r'^/delete(?!_)\s*([\w-]+)$'))
        async def delete_timer_command(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)

            try:
                timer_id = str(event.pattern_match.group(1))
            except ValueError:
                await event.reply("❌ Nhập ID hợp lệ")
                backend_logger.error(
                    f"Trong chat {chat_id} người dùng {user_id} nhập sai lệnh `{event.message.message}`. Lỗi: ID không hợp lệ"
                )
                return

            backend_logger.info(f"Trong chat {chat_id} người dùng {user_id} dùng `{event.message.message}`")
            await delete_timer(
                user_id=user_id,
                chat_id=chat_id,
                timer_id=timer_id,
                event=event,
            )

        @client.on(events.NewMessage(pattern=r'/delete_all_timers'))
        async def delete__all_timers_command(event):
            chat_id = str(event.chat_id)
            user_id = str(event.sender_id)

            backend_logger.info(f"Trong chat {chat_id} người dùng {user_id} dùng `{event.message.message}`")
            await delete_all_timers(chat_id=chat_id, user_id=user_id, event=event)

        @client.on(events.NewMessage(pattern=r'^/get(?!_my)(?:@\w+)?(?:\s+(\d+))?$'))
        async def get_chat_timers_command(event):
            chat_id = str(event.chat_id)
            timer_numbers = event.pattern_match.group(1)
            user_id = str(event.sender_id)

            if timer_numbers is None:
                timer_numbers = 0

            try:
                timer_numbers = int(timer_numbers)
            except ValueError:
                await event.reply("❌ Sau `/get` hãy nhập số lượng boss muốn xem")
                backend_logger.error(
                    f"Trong chat {chat_id} người dùng {user_id} nhập sai `{event.message.message}`. Lỗi: không phải số"
                )
                return

            backend_logger.info(f"Trong chat {chat_id} người dùng {user_id} dùng `{event.message.message}`")
            await get_chat_timers(
                chat_id=chat_id, 
                timer_numbers=timer_numbers, 
                user_id=user_id, 
                event=event
            )

        @client.on(events.NewMessage(pattern=r'^/start(@\w+)?$'))
        async def start_command(event):
            chat_id = str(event.chat_id)
            chat = await event.get_chat()
            participants = await client.get_participants(chat)
            await start_chat(chat_id=chat_id, chat=chat, participants=participants, event=event)

        @client.on(events.NewMessage(pattern=r'^/info(@\w+)?$'))
        async def info_command(event):
            await event.reply(
                "Bot này được tạo ra để hỗ trợ trò chơi Lineage2M. Người tạo: @egopbi (Eeee Gorka)"
            )

        @client.on(events.NewMessage(pattern=r'^/help(@\w+)?$'))
        async def help_command(event):
            help_text = (
                "**Các lệnh có sẵn:**\n\n"
                "/bosses\n- Hiển thị danh sách boss\n\n"
                "-------------------------------------\n"
                "/set <tên_boss> <giờ_phát_sinh>\n- Đặt thời gian hồi sinh cho boss. Định dạng HH:MM. Nếu không có giờ sẽ lấy thời điểm hiện tại\n\n"
                "-------------------------------------\n"
                "/get <số_lượng>\n- Hiển thị <số_lượng> boss sắp xuất hiện\n\n"
                "-------------------------------------\n"
                "/get\n- Hiển thị tất cả các boss đã được đặt\n\n"
                "-------------------------------------\n"
                "/delete <id>\n- Xóa boss theo ID\n\n"
                "-------------------------------------\n"
                "/all_start\n- Bắt đầu tất cả hẹn giờ\n\n"
                "-------------------------------------\n"
                "/info\n- Thông tin về bot\n\n"
                "-------------------------------------\n"
                "/help\n- Hiển thị hướng dẫn"
            )
            await event.reply(help_text)

        await client.run_until_disconnected()
        backend_logger.success("Bot đang hoạt động")

    except Exception as e:
        backend_logger.error(f"Lỗi khi chạy bot: {e}")

    except asyncio.CancelledError:
        backend_logger.info("Tác vụ bot bị hủy. Đang ngắt kết nối...")

    finally:
        if client:
            try:
                await client.disconnect()
                backend_logger.info("Ngắt kết nối bot Telegram thành công")
            except Exception as e:
                backend_logger.error(f"Lỗi khi ngắt kết nối bot: {e}")


async def run_bot():
    loop = asyncio.get_running_loop()

    for s in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, lambda s=s: loop.create_task(shutdown(s.name)))

    await init_db()

    while True:
        try:
            await main()
        except ConnectionError:
            backend_logger.error("Lỗi kết nối. Thử lại sau 30 giây...")
            await asyncio.sleep(30)
        else:
            backend_logger.info("Main kết thúc bình thường. Thoát vòng lặp.")
            break


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        backend_logger.info("Bot dừng bằng KeyboardInterrupt")
        sys.exit(0)
    except Exception as e:
        backend_logger.error(f"Lỗi khởi động: {str(e)}")
        sys.exit(1)
