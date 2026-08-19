import os
import re
import uuid
import asyncio
import logging
import aiofiles
import aiohttp
import random
from typing import List, Optional
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import event_message_type, EventMessageType
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

logger = logging.getLogger(__name__)

file_lock = asyncio.Lock()


class ImageManager:
    def __init__(self, config: AstrBotConfig):
        self.config = config
        data_path = Path(get_astrbot_data_path())
        self.imgs_folder = str(data_path / "plugin_data" / "astrbot_plugin_lolicon" / "imgs")
        self.supported_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
        self.max_file_size = 20 * 1024 * 1024

        self._download_task = None
        self._refill_running = False
        self.download_lock = asyncio.Lock()

        self._init_folder()

    @property
    def cache_size(self) -> int:
        return int(self.config.get("cache_size", 10))

    @property
    def refill_threshold(self) -> int:
        return int(self.config.get("refill_threshold", 5))

    @property
    def refill_interval(self) -> int:
        return int(self.config.get("refill_interval", 300))

    def _init_folder(self):
        os.makedirs(self.imgs_folder, exist_ok=True)

    async def get_image_list(self):
        async with file_lock:
            try:
                files = await asyncio.to_thread(os.listdir, self.imgs_folder)
                return [f for f in files if os.path.splitext(f)[1].lower() in self.supported_extensions]
            except Exception as e:
                logger.error(f"Error getting image list: {e}")
                return []

    async def get_image_count(self):
        return len(await self.get_image_list())

    async def get_random_image(self):
        images = await self.get_image_list()
        return random.choice(images) if images else None

    async def delete_image(self, filename):
        async with file_lock:
            try:
                path = os.path.join(self.imgs_folder, filename)
                if os.path.exists(path):
                    await asyncio.to_thread(os.remove, path)
                return True
            except Exception as e:
                logger.error(f"Delete image failed: {e}")
                return False

    async def validate_image(self, path):
        try:
            if not os.path.exists(path):
                return False
            size = os.path.getsize(path)
            if size == 0 or size > self.max_file_size:
                return False
            ext = os.path.splitext(path)[1].lower()
            return ext in self.supported_extensions
        except Exception:
            return False

    async def generate_and_save_image(self, url, filename):
        async with self.download_lock:
            try:
                path = os.path.join(self.imgs_folder, filename)
                if os.path.exists(path):
                    return filename
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=45)
                ) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            return None
                        content = await response.read()
                        if not content or len(content) > self.max_file_size:
                            return None
                        async with aiofiles.open(path, "wb") as f:
                            await f.write(content)
                        logger.info(f"Saved image: {filename}")
                        return filename
            except Exception as e:
                logger.error(f"Save image failed: {e}")
                return None

    async def download_one(self):
        source = self.config.get("data_source", "lolicon")
        if source == "nyan":
            return await self._download_one_nyan()
        return await self._download_one_lolicon()

    async def _download_one_lolicon(self):
        results = await fetch_setu_lolicon(
            r18=int(self.config.get("r18", 0)),
            tags=[[], []],
            exclude_ai=self.config.get("exclude_ai", True),
            aspect_ratio=self.config.get("aspect_ratio", "gt1") or None,
            num=1
        )
        if not results:
            return None
        item = results[0]
        filename = f"{item['pid']}_p{item['p']}.{item['ext']}"
        original_url = item["urls"].get("original")
        if not original_url:
            return None
        return await self.generate_and_save_image(original_url, filename)

    async def _download_one_nyan(self):
        url = "https://sex.nyan.run/api/v2/img"
        params = {"r18": "true" if int(self.config.get("r18", 0)) == 1 else "false"}
        async with self.download_lock:
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as session:
                    async with session.get(url, params=params) as response:
                        if response.status != 200:
                            return None
                        content = await response.read()
                        if not content or len(content) < 100 or len(content) > self.max_file_size:
                            return None
                        content_type = response.headers.get('Content-Type', '')
                        ext = self._ext_from_content_type(content_type) or self._ext_from_magic(content)
                        filename = f"{uuid.uuid4().hex[:12]}{ext}"
                        path = os.path.join(self.imgs_folder, filename)
                        async with aiofiles.open(path, 'wb') as f:
                            await f.write(content)
                        if os.path.exists(path) and os.path.getsize(path) > 0:
                            logger.info(f"Saved image (nyan): {filename}")
                            return filename
                        return None
            except Exception as e:
                logger.error(f"nyan download failed: {e}")
                return None

    @staticmethod
    def _ext_from_content_type(ct: str) -> str:
        ct = ct.lower()
        if 'jpeg' in ct or 'jpg' in ct:
            return '.jpg'
        if 'png' in ct:
            return '.png'
        if 'webp' in ct:
            return '.webp'
        if 'gif' in ct:
            return '.gif'
        return ''

    @staticmethod
    def _ext_from_magic(content: bytes) -> str:
        if content.startswith(b'\xff\xd8\xff'):
            return '.jpg'
        if content.startswith(b'\x89PNG\r\n\x1a\n'):
            return '.png'
        if content.startswith(b'GIF87a') or content.startswith(b'GIF89a'):
            return '.gif'
        if content.startswith(b'RIFF') and content[8:12] == b'WEBP':
            return '.webp'
        return '.jpg'

    async def check_and_refill_cache(self):
        if self._refill_running:
            return
        self._refill_running = True
        try:
            current = await self.get_image_count()
            if current >= self.cache_size:
                return
            need = self.cache_size - current
            logger.info(f"Cache refill: current={current}, need={need}")
            success = 0
            for _ in range(need):
                try:
                    if await self.download_one():
                        success += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Refill item failed: {e}")
            logger.info(f"Cache refill complete: {success}/{need}")
        finally:
            self._refill_running = False

    async def start_background_cache_task(self):
        if self._download_task and not self._download_task.done():
            return
        self._download_task = asyncio.create_task(self._background_cache())

    async def _background_cache(self):
        while True:
            try:
                current = await self.get_image_count()
                if current < self.refill_threshold:
                    await self.check_and_refill_cache()
                await asyncio.sleep(self.refill_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Background cache error: {e}")
                await asyncio.sleep(60)


async def fetch_setu_lolicon(
    r18: int = 0,
    num: int = 1,
    tags: Optional[List[List[str]]] = None,
    size: List[str] = None,
    uid: List[int] = None,
    keyword: str = None,
    proxy: str = None,
    exclude_ai: bool = None,
    aspect_ratio: str = None
):
    url = "https://api.lolicon.app/setu/v2"
    params = {
        "r18": r18,
        "num": max(1, min(20, num)),
        "excludeAI": exclude_ai,
    }
    if tags:
        params["tag"] = tags
    if size:
        params["size"] = size
    if uid:
        params["uid"] = uid[:20]
    if keyword:
        params["keyword"] = keyword
    if proxy:
        params["proxy"] = proxy
    if aspect_ratio:
        params["aspectRatio"] = aspect_ratio

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            async with session.post(url, json=params) as response:
                data = await response.json()
                if data.get("error"):
                    logger.warning(f"API Error: {data['error']}")
                    return None
                return data.get("data", [])
    except Exception as e:
        logger.error(f"fetch_setu error: {e}")
        return None


def match_trigger(text: str, mode: str, words: list) -> bool:
    """根据匹配模式判断是否触发"""
    text = text.lower()
    if mode == "regex":
        return any(re.search(w, text) for w in words)
    if mode == "exact":
        return any(text.strip() == w.lower() for w in words)
    return any(w.lower() in text for w in words)


@register(
    "astrbot_plugin_lolicon",
    "hello七七",
    "我要涩涩",
    "2.0",
    "https://github.com/ttq7/astrbot_plugin_Lolicon"
)
class LoliconPlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.image_manager = ImageManager(config)
        asyncio.create_task(self._delayed_start_cache())

    def _msg(self, key: str) -> str:
        """根据 reply_style 返回对应文案"""
        style = self.config.get("reply_style", "plain")
        playful = {
            "cache_empty": "不准涩涩",
            "sent": "色批给你好了",
            "send_fail": "信号不好没有找到涩涩",
            "error": "处理请求时发生错误，请联系管理员",
        }
        plain = {
            "cache_empty": "库存为空，正在补货，请稍后再试",
            "sent": "给你涩图~",
            "send_fail": "图片发送失败",
            "error": "处理请求时发生错误",
        }
        table = playful if style == "playful" else plain
        return table.get(key, plain.get(key, ""))

    async def _delayed_start_cache(self):
        await asyncio.sleep(5)
        await self.image_manager.check_and_refill_cache()
        await self.image_manager.start_background_cache_task()

    @event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        try:
            text = event.message_str
            mode = self.config.get("match_mode", "contains")
            words = self.config.get("trigger_words", ["色图", "涩图", "瑟图"])
            if match_trigger(text, mode, words):
                return await self.handle_image_request(event)
        except Exception as e:
            logger.error(f"Message handler error: {e}")
            return event.plain_result(f"插件异常: {e}")

    async def handle_image_request(self, event):
        filename = None
        result = None
        try:
            filename = await self.image_manager.get_random_image()

            if not filename:
                asyncio.create_task(self.image_manager.check_and_refill_cache())
                return event.plain_result(self._msg("cache_empty"))

            image_path = os.path.join(self.image_manager.imgs_folder, filename)

            if not await self.image_manager.validate_image(image_path):
                await self.image_manager.delete_image(filename)
                asyncio.create_task(self.image_manager.check_and_refill_cache())
                return event.plain_result(self._msg("cache_empty"))

            await event.send(event.make_result().file_image(image_path))

            await asyncio.sleep(3)

            current = await self.image_manager.get_image_count()
            if current < self.image_manager.refill_threshold:
                asyncio.create_task(self.image_manager.check_and_refill_cache())

            name_without_ext = os.path.splitext(filename)[0]
            pure_id = name_without_ext.split('_')[0]
            result = event.plain_result(f"{self._msg('sent')} {pure_id}")

        except Exception as e:
            logger.error(f"send image error: {e}")
            if filename:
                name_without_ext = os.path.splitext(filename)[0]
                pure_id = name_without_ext.split('_')[0]
                result = event.plain_result(f"{self._msg('send_fail')} {pure_id}")
            else:
                result = event.plain_result(self._msg("send_fail"))
        finally:
            if filename:
                await self.image_manager.delete_image(filename)

        if result:
            return result

    async def terminate(self):
        try:
            if self.image_manager._download_task:
                self.image_manager._download_task.cancel()
            files = await self.image_manager.get_image_list()
            if files:
                await asyncio.gather(
                    *(self.image_manager.delete_image(f) for f in files)
                )
            logger.info("Plugin terminated, cleaned up %d images", len(files))
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
