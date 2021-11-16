from aiogram import types, Dispatcher

from tgbot.integrations.telegraph import FileUploader


async def handle_photo_upload(m: types.Message, file_uploader: FileUploader):
    photo = m.photo[-1]
    await m.bot.send_chat_action(m.chat.id, 'upload_photo')
    uploaded_photo = await file_uploader.upload_photo(photo)
    await m.answer(text=uploaded_photo.link)


def register_photo_handlers(dp: Dispatcher):
    dp.register_message_handler(
        handle_photo_upload,
        content_types=types.ContentTypes.PHOTO
    )
