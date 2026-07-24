# bot/workers.py
import os
import asyncio
import datetime
import time
from aiogram import types
from aiogram.types import FSInputFile
from config import (
    bot, pyro_app, db, video_queue, DB_CHANNEL_ID, CHANNEL_ID,
    TUTORIAL_LINK, REQUEST_LINK, clear_app_cache, logger
)
from helpers import generate_collage

is_processing = False

async def video_queue_worker():
    global is_processing, video_queue
    while True:
        chat_id, message_id, aiogram_file_id, file_type = await video_queue.get()
        is_processing = True
        downloaded_file = None
        collage_path = None
        try:
            admin_id = chat_id
            status_msg = await bot.send_message(admin_id, "⏳ <b>Processing Video...</b> (Downloading)")
            pyro_msg = await pyro_app.get_messages(chat_id, message_id)
            
            total_vids = await db.movies.count_documents({})
            serial_no = total_vids + 1
            auto_title = f"New Viral Video {serial_no:04d}"
            
            video_name = f"temp_video_{serial_no}_{int(time.time())}.mp4"
            collage_path = os.path.abspath(f"collage_{serial_no}_{int(time.time())}.jpg")
            
            downloaded_file = await pyro_app.download_media(pyro_msg, file_name=video_name)
            if not downloaded_file:
                await bot.edit_message_text("❌ ফাইল ডাউনলোড করতে সমস্যা হয়েছে।", chat_id=admin_id, message_id=status_msg.message_id)
                continue
                
            await bot.edit_message_text("📸 <b>Generating Screenshots...</b>", chat_id=admin_id, message_id=status_msg.message_id, parse_mode="HTML")
            success = await generate_collage(downloaded_file, collage_path)
            
            if not success:
                await bot.edit_message_text("❌ <b>Screenshot তৈরি করতে সমস্যা হয়েছে!</b>", chat_id=admin_id, message_id=status_msg.message_id, parse_mode="HTML")
                continue
                
            db_file_id = None
            db_photo_id = None
            photo_id = None
            
            if DB_CHANNEL_ID:
                try:
                    copied_vid = await bot.copy_message(chat_id=DB_CHANNEL_ID, from_chat_id=chat_id, message_id=message_id)
                    db_file_id = copied_vid.message_id
                    
                    copied_photo = await bot.send_photo(DB_CHANNEL_ID, FSInputFile(collage_path))
                    db_photo_id = copied_photo.message_id
                    photo_id = copied_photo.photo[-1].file_id
                except Exception: pass
            
            photo_msg = await bot.send_photo(admin_id, photo=FSInputFile(collage_path), caption=f"✅ <b>{auto_title}</b> Successfully Uploaded!")
            if not photo_id: photo_id = photo_msg.photo[-1].file_id
            
            await db.movies.insert_one({
                "title": auto_title, "quality": "HD", "photo_id": photo_id, 
                "file_id": aiogram_file_id, "file_type": file_type,
                "db_file_id": db_file_id, "db_photo_id": db_photo_id,
                "categories": ["Auto Upload"], 
                "clicks": 0, "created_at": datetime.datetime.utcnow()
            })
            clear_app_cache() 
            await bot.delete_message(chat_id=admin_id, message_id=status_msg.message_id)

            if CHANNEL_ID:
                try:
                    bot_info = await bot.get_me()
                    kb = [
                        [types.InlineKeyboardButton(text="📥 Download & Watch 🎬", url=f"https://t.me/{bot_info.username}?start=new")],
                        [types.InlineKeyboardButton(text="কিভাবে ডাউনলোড করবেন ❓", url=TUTORIAL_LINK)],
                        [types.InlineKeyboardButton(text="♻️ MOVIE REQUEST ♻️", url=REQUEST_LINK)]
                    ]
                    markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
                    caption = (f"🔥 <b>নতুন এক্সক্লুসিভ ভাইরাল ভিডিও!</b>\n\n📌 <b>টাইটেল:</b> {auto_title}\n🏷 <b>কোয়ালিটি:</b> HD (Original)\n\n👇 <i>বট থেকে ভিডিওটি পেতে নিচের বাটনে ক্লিক করুন।</i>")
                    await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=markup)
                except Exception: pass
        except Exception as e:
            await bot.send_message(chat_id, f"⚠️ Error: {str(e)}")
        finally:
            if downloaded_file and os.path.exists(downloaded_file): os.remove(downloaded_file)
            if collage_path and os.path.exists(collage_path): os.remove(collage_path)
            video_queue.task_done()
            is_processing = False

async def auto_delete_worker():
    while True:
        try:
            now = datetime.datetime.utcnow()
            expired_msgs = db.auto_delete.find({"delete_at": {"$lte": now}})
            async for msg in expired_msgs:
                try: 
                    await bot.delete_message(chat_id=msg["chat_id"], message_id=msg["message_id"])
                except Exception: pass
                await db.auto_delete.delete_one({"_id": msg["_id"]})
                
            await db.ads.delete_many({"expires_at": {"$lte": now}})
        except Exception: pass
        await asyncio.sleep(60)
