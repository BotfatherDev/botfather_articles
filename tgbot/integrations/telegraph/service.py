import secrets
from io import BytesIO
from typing import Optional

import aiohttp
from aiogram.types import PhotoSize

from tgbot.integrations.telegraph.abstract import FileUploader
from tgbot.integrations.telegraph.config import BASE_TELEGRAPH_API_LINK
from tgbot.integrations.telegraph.exceptions import TelegraphAPIError
from tgbot.integrations.telegraph.types import UploadedFile


class TelegraphService(FileUploader):
    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    async def upload_photo(self, photo: PhotoSize) -> UploadedFile:
        form = aiohttp.FormData(quote_fields=False)
        downloaded_photo = await photo.download(destination_file=BytesIO())
        form.add_field(secrets.token_urlsafe(8), downloaded_photo)

        session = await self.get_session()
        response = await session.post(
            BASE_TELEGRAPH_API_LINK.format(endpoint="upload"),
            data=form
        )
        if not response.ok:
            raise TelegraphAPIError(
                "Something went wrong, response from telegraph is not successful. "
                f"Response: {response}"
            )
        json_response = await response.json()
        return [UploadedFile.parse_obj(obj) for obj in json_response][0]

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            new_session = aiohttp.ClientSession()
            self._session = new_session
        return self._session

    async def close(self) -> None:
        if self._session is None:
            return None
        await self._session.close()
