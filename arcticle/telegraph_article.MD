![](https://telegra.ph/file/b761c26d98a7b56b59160.png)

В этой статье мы с вами напишем бота, который будет загружать картинку пользователя на telegra.ph (
на котором вы, собственно, сейчас и читаете эту статью) и возвращать прямую ссылку на фото. Это
может быть полезно, например, для создания скрытых
c [preview](https://telegram.org/blog/link-preview), ссылок на фото или добавления thumb_url
к [InlineQueryResultArticle](https://core.telegram.org/bots/api#inlinequeryresultarticle).

## Результат работы

![Результат работы](https://telegra.ph/file/071825eeb0f329b588774.png)

Как мы видим, после того, как мы отправляем боту картинку, бот генерирует и возвращает нам ссылку на
эту самую картинку на telegra.ph, которая имеет удобный предпросмотр.

В нашем хендлере обработка будет ну уж очень лаконичная🙃:

```python
async def handle_photo_upload(messsage: types.Message, file_uploader: FileUploader):
    photo = messsage.photo[-1]
    await messsage.bot.send_chat_action(messsage.chat.id, 'upload_photo')
    uploaded_photo = await file_uploader.upload_photos(photo)
    await messsage.answer(text=uploaded_photo.link)
```

# Реализация собственного модуля для работы с Telegraph API

## Полезность абстракций

При реализации сервиса для работы с телеграфом мы будем использовать его в хендлере через
абстракцию, важно знать чем они полезны и что они нам приносят.

* Мы абстрагируемся от реальной реализации класса и всего что связано с этим сервисом собственной
  абстракцией, которая поможет нам легко изменить сервис для загрузки файлов, если вам по каким-то
  причинам не подошёл телеграф, к примеру на популярный среди разработчиков `AWS S3`, просто
  унаследовав абстрактный класс и имлементировав все нужные методы.
* Следуя документации `aiohttp` и рекомендациями её разработчика следует использовать единственный
  экземпляр `aiohttp.ClientSession`. С помощью функций данная рекомендация не может быть корректно
  реализована.

Итак, теперь давайте кратко обсудим как мы можем написать такую обвертку и шаг за шагом попробуем
написать что-то подобное своё😎

## Реализация абстракции для загрузки фотографий

Начнем с написания собственной абстракции, в новом шаблоне мы можем написать данную обвертку и
поместить её в папку `integrations`, которой в шаблоне нет, однако мы же всегда можем её создать😉.
Давайте создадим абстрактный класс и там напишем 2 абстрактных метода:

```python
import abc

from aiogram.types import PhotoSize

from tgbot.integrations.telegraph.types import UploadedFile


class FileUploader(abc.ABC):

  async def upload_photo(self, photo: PhotoSize) -> UploadedFile:
    raise NotImplementedError

  async def close(self) -> None:
    raise NotImplementedError
```

Выглядит достаточно красиво и лаконично, метод `upload_photo` принимает фотографию и загружает её на
какой-то сервис(в нашем случае телеграф).

## Модели нашей обвертки

Далее, стоило бы понять, что это за странный класс `UploadedFile`, в нашем случае, это `pydantic`
модель, которая валидирует ответ от телеграфа и конструирует нам ссылку к загруженной фотографии.

### Небольшое отступление про библиотеку `pydantic`

[Pydantic](https://pydantic-docs.helpmanual.io/), в общем и целом, помогает нам распарсить `json`,
поддерживает древовидные структуры, валидацию по аннотациям аттрибутов а также кастомные валидаторы
и многое другое. В нашем случае мы задеклалировали 1 аттрибут `link`, который должен быть строкой, в
ином случае pydantic пробросит ошибку валидации `ValidationError`.

Что же такое `alias` и зачем он нужен?

Alias - это "псевдоним для поля", то есть к примеру API отдает нам ответ `{src: "some_data"}`, и мы
не хотим чтобы имя аттрибута модели было `src`, потому что оно кажется нам каким-то странным и
абстрактным, поэтому мы передаем в конструктор `Field` параметр `alias`, чтобы дать понять pydantic,
что мы хотим ячейку json с именем `src` распарсить как аттрибут `link`.

Валидатор `link_validator` в нашем случае просто формирует ссылку.

```python
from pydantic import Field, BaseModel, validator

from tgbot.integrations.telegraph.config import BASE_TELEGRAPH_API_LINK


class UploadedFile(BaseModel):
  link: str = Field(..., alias="src")

  @validator("link")
  def link_validator(cls, value: str):
    return BASE_TELEGRAPH_API_LINK.format(endpoint=value)
```

## Реализация клиента для работы с телеграфом

```python
import secrets
from io import BytesIO
from typing import Optional

import aiohttp
from aiogram.types import PhotoSize

from tgbot.integrations.telegraph.abstract import FileUploader
from tgbot.integrations.telegraph.config import BASE_TELEGRAPH_API_LINK
from tgbot.integrations.telegraph.exceptions import TelegraphAPIError
from tgbot.integrations.telegraph.types import UploadedFile


class Telegraph(FileUploader):
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
    return UploadedFile.parse_obj(json_response)

  async def get_session(self) -> aiohttp.ClientSession:
    if self._session is None:
      new_session = aiohttp.ClientSession()
      self._session = new_session
    return self._session

  async def close(self) -> None:
    if self._session is None:
      return None
    await self._session.close()
```

Давайте разберемся с этой реализаций поподробнее. Сразу же может возникнуть вопрос, почему мы сразу
же не инициализируем сессию прямо в конструкторе? Мы это делаем не из-за того, что нам просто так
захотелось, а потому что сессия `aiohttp.ClientSession` должна быть создана в корутине, то есть в
функции с приставкой `async`, иначе мы получим кучу ошибок и проблем в дальнейшем, поэтому мы
реализовываем метод `get_session`, который будет создавать новую сессию, если она ещё не создана.

Теперь рассмотрим метод `upload_photo`, он получает объект `PhotoSize`, который мы импортировали из
aiogram и в самом методе скачивает эту фотографию и добавляет её в некую форму, чтобы отправить
запрос к API. Так же мы видим проверку `if not response.ok`, если что-то пошло не так и телеграф
вернул нам статус код, который не равен 200 и последующий парсинг `json` ответа. Давайте поместим нашу
реализацию в модуль `integrations/telegraph/client.py`.

# Подключение обвертки в новый шаблон

Теперь давайте подключим ранее написанную обвертку к нашему боту и воспользуемся новым шаблоном. Для
интеграций давайте создадим новый middleware и назовем его `IntegrationMiddleware`, в котором вы
можете создавать и передавать в хендлеры не только телеграф клиент, а так же классы для работы с
различными сервисами, CRM, платежными системами и другим, а реализации помещать в
пакет `integrations`.

```python
from typing import Dict, Any

from aiogram.dispatcher.middlewares import LifetimeControllerMiddleware
from aiogram.types.base import TelegramObject

from tgbot.integrations.telegraph.abstract import FileUploader


class IntegrationMiddleware(LifetimeControllerMiddleware):
  skip_patterns = ["error", "update"]

  def __init__(self, uploader: FileUploader):
    super().__init__()
    self._uploader = uploader

  async def pre_process(self, obj: TelegramObject, data: Dict[Any, Any], *args: Any):
    data["file_uploader"] = self._uploader
```

Так же теперь нам нужно создать объект `TelegraphService` и передать его в конструктор `IntegrationMiddleware`:

```python
file_uploader = TelegraphService()
dp.middleware.setup(IntegrationMiddleware(file_uploader))
```

Однако, это ещё не всё😁 Нам потребуется закрывать сессию с помощью того самого метода `close`, который
есть у `TelegraphClient`, но в мидлвари не самое подходящее место, так как сессию бы желательно не
закрывать после каждого апдейта. Решением будет передать `FileUploader` не только в конструктор
middleware, а так же в объект бота, чтобы далее можно было получить его в функции `on_shutdown`

```python
from aiogram import Bot, Dispatcher
from tgbot.integrations.telegraph.abstract import FileUploader
from tgbot.integrations.telegraph.service import TelegraphService


async def on_shutdown(dp: Dispatcher):
    file_uploader: FileUploader = dp.bot["file_uploader"]
    await file_uploader.close()


async def main():
    # Реализация запуска бота пропущена для простоты

    bot = Bot(token=config.tg_bot.token)
    dp = dp = Dispatcher(bot)
    file_uploader = TelegraphService()
    bot["file_uploader"] = file_uploader

    try:
        await dp.start_polling()
    finally:
        await dp.storage.close()
        await dp.storage.wait_closed()
        await bot.session.close()
        # Здесь можно почистить ресурсы и закрыть
        await on_shutdown(dp)


```

# Заключение

Получение прямой ссылки на изображение, отправленное пользователем — частая задача, решение которой
не кажется таким уж интуитивным. Такие ссылки могут использоваться для миниатюры в статье инлайн
ответа, для того, чтобы спрятать невидимую ссылку с картинкой в сообщении или просто отправить
картинку в чат без права на отправку фото 🌚.

В этой статье мы разобрались, как можно реализовать отправку изображения пользователя на telegra.ph,
и получение прямой ссылки на него.

Код данной статьи вы можете найти в нашем ![github репозитории](https://github.com/GLEF1X/botfather_articles).

В статье за основу взята новая структура для написания телеграм ботов на базе aiogram.
