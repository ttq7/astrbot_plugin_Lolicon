import os
import asyncio
import logging
import aiofiles
import aiohttp  
from typing import List, Optional
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.api.message_components import *

logger = logging.getLogger(__name__)

file_lock = asyncio.Lock()

class ImageManager:
    """图片管理类"""
    def __init__(self):
        self.imgs_folder = "imgs"
        self.supported_extensions = {'.png', '.jpg', '.jpeg', '.webp'}
        self._init_folder()

    def _init_folder(self):
        """初始化图片文件夹"""
        if not os.path.exists(self.imgs_folder):
            os.makedirs(self.imgs_folder)
            logger.info("Created images folder")

    async def get_image_list(self):
        """获取有效图片列表"""
        async with file_lock:
            try:
                files = await asyncio.to_thread(os.listdir, self.imgs_folder)
                return [f for f in files if os.path.splitext(f)[1].lower() in self.supported_extensions]
            except Exception as e:
                logger.error(f"Error getting image list: {str(e)}")
                return []

    async def delete_image(self, filename: str):
        """安全删除图片文件"""
        async with file_lock:
            file_path = os.path.join(self.imgs_folder, filename)
            try:
                if os.path.exists(file_path):
                    await asyncio.to_thread(os.remove, file_path)
                    logger.info(f"Deleted image: {filename}")
                    return True
                logger.warning(f"Attempted to delete non-existent file: {filename}")
                return False
            except Exception as e:
                logger.error(f"Error deleting image {filename}: {str(e)}")
                return False

    async def generate_and_save_image(self, url, filename):
        async with file_lock:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                    async with session.get(url) as response:
                        content = await response.read()  # 异步读取响应内容
                        file_path = os.path.join(self.imgs_folder, filename)
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(content)  # 异步写入文件
                        logger.info(f"Successfully saved image: {filename}")
                        return True
            except aiohttp.ClientError as e:
                logger.error(f"HTTP Error saving {filename}: {str(e)}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error saving {filename}: {str(e)}")
                return False

image_manager = ImageManager()

async def fetch_setu(
        r18: int = 0,
        num: int = 1,
        tags: Optional[List[List[str]]] = None,
        size: List[str] = None,
        uid: List[int] = None,
        keyword: str = None,
        proxy: str = None,
        exclude_ai: bool = None,
        aspect_ratio: str = None
) -> Optional[List[dict]]:
    url = "https://api.lolicon.app/setu/v2"
    params = {
        "r18": r18,
        "num": max(1, min(20, num)),
        "excludeAI": exclude_ai,
    }

    if tags: params["tag"] = tags
    if size: params["size"] = size
    if uid: params["uid"] = uid[:20]
    if keyword: params["keyword"] = keyword
    if proxy: params["proxy"] = proxy
    if aspect_ratio: params["aspectRatio"] = aspect_ratio

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=params) as response:
                data = await response.json() 

                if data.get("error"):
                    logger.warning(f"API Error: {data['error']}")
                    return None

                return data.get("data", [])

    except aiohttp.ClientError as e:
        logger.error(f"HTTP Request Failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")
        return None

@register("astrbot_plugin_lolicon", "hello七七", "我要涩涩", "1.2", "https://github.com/ttq7/astrbot_plugin_Lolicon")
class ArknightsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.image_manager = image_manager

    @event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> MessageEventResult:
        """处理所有消息事件"""
        try:
            text = event.message_str.lower()
            if any(keyword in text for keyword in ["我要色色", "我要色图", "我要涩涩"]):
                await event.send(event.plain_result("咳咳大胆"))
                return await self.handle_image_request(event)
        except Exception as e:
            logger.error(f"Message handler error: {str(e)}")
            return event.plain_result(f"插件异常: {str(e)}")

    async def handle_image_request(self, event: AstrMessageEvent) -> MessageEventResult:
        """异步处理图片请求全流程"""
        try:

            results = await fetch_setu(
                tags=[[], []],
                exclude_ai=True,
                aspect_ratio="gt1",
                num=1
            )
            if not results:
                return event.plain_result("不准涩涩")

            item = results[0]
            original_url = item['urls'].get("original")
            if not original_url:
                return event.plain_result("没有找到涩涩")

            filename = f"{item['pid']}_p{item['p']}.{item['ext']}"

            save_success = await self.image_manager.generate_and_save_image(original_url, filename)
            if not save_success:
                return event.plain_result("你怎么这么自私")

            image_path = os.path.join(self.image_manager.imgs_folder, filename)
            message_chain = event.make_result().file_image(image_path)
            
            # 异步发送图片
            try:
                await event.send(message_chain)
                logger.info(f"Image sent: {filename}")
                
                # 延迟删除（避免发送过程中文件被删除）
                await asyncio.sleep(1)
                delete_success = await self.image_manager.delete_image(filename)
                return event.plain_result("色批给你好了") if delete_success \
                    else event.plain_result("完了涩涩没有打扫干净")

            except Exception as e:
                logger.warning(f"Send failed for {filename}: {str(e)}")
                await self.image_manager.delete_image(filename)  
                return event.plain_result("信号不好没有找到涩涩")

        except Exception as e:
            logger.error(f"Request handling failed: {str(e)}")
            return event.plain_result("处理请求时发生错误，请联系管理员")

    async def terminate(self):
 
        try:
            image_files = await self.image_manager.get_image_list()
            if image_files:
                await asyncio.gather(*(self.image_manager.delete_image(f) for f in image_files))
            logger.info("Plugin terminated, cleaned up %d images", len(image_files))
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")
    


