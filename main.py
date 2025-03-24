import os
import asyncio
import logging
import aiofiles
import requests
from typing import List, Optional
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.api.message_components import *

logger = logging.getLogger(__name__)

# 全局锁防止并发文件操作
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
        """生成并保存图片"""
        async with file_lock:
            try:
                response = requests.get(url, timeout=15)
                response.raise_for_status()
                file_path = os.path.join(self.imgs_folder, filename)
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(response.content)
                logger.info(f"Successfully saved image: {filename}")
                return True
            except Exception as e:
                logger.error(f"Error generating and saving image {filename}: {str(e)}")
                return False

image_manager = ImageManager()

def fetch_setu(
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
    """
    获取随机色图

    :param r18: 0-非R18, 1-R18, 2-混合
    :param num: 获取数量(1-20)
    :param tags: 二维标签列表，如[["萝莉", "少女"], ["白丝", "黑丝"]]
    :param size: 图片尺寸列表，如["original", "regular"]
    :param uid: 作者UID列表
    :param keyword: 关键词搜索
    :param proxy: 自定义反代地址
    :param exclude_ai: 排除AI作品
    :param aspect_ratio: 长宽比筛选
    :return: 色图数据列表
    """
    url = "https://api.lolicon.app/setu/v2"
    params = {
        "r18": r18,
        "num": max(1, min(20, num)),
        "excludeAI": exclude_ai,
    }

    if tags is not None:
        params["tag"] = tags
    if size is not None:
        params["size"] = size
    if uid is not None:
        params["uid"] = uid[:20]  # 最多20个UID
    if keyword:
        params["keyword"] = keyword
    if proxy:
        params["proxy"] = proxy
    if aspect_ratio:
        params["aspectRatio"] = aspect_ratio

    try:
        response = requests.post(url, json=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if error := data.get("error"):
            print(f"API Error: {error}")
            return None

        return data.get("data", [])

    except Exception as e:
        print(f"Request Failed: {str(e)}")
        return None

@register("astrbot_plugin_setu", "hello七七", "我要涩涩", "1.1", "https://github.com/yourname/astrbot_plugin_setu")
class ArknightsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.image_manager = image_manager

    @event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> MessageEventResult:
        """处理所有消息事件"""
        try:
            text = event.message_str.lower()
            if "我要色色" in text or "我要色图" in text or "我要涩涩" in text:
                # 发送正在寻找图片的提示
                await event.send(event.plain_result("咳咳咳大胆"))
                return await self.handle_image_request(event)
        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
            return event.plain_result(f"插件内部错误: {str(e)}")

    async def handle_image_request(self, event: AstrMessageEvent) -> MessageEventResult:
        """处理图片请求"""
        try:
            # 获取图片数据
            results = fetch_setu(
                tags=[[], []],
                exclude_ai=True,
                aspect_ratio="gt1",
                num=1
            )
            if not results:
                return event.plain_result("")

            item = results[0]
            if url := item['urls'].get("original"):
                filename = f"{item['pid']}_p{item['p']}.{item['ext']}"
                # 生成并保存图片
                success = await self.image_manager.generate_and_save_image(url, filename)
                if not success:
                    return event.plain_result("不准涩涩")

                image_path = os.path.join(self.image_manager.imgs_folder, filename)
                # 发送图片
                result = event.make_result().file_image(image_path)
                try:
                    await event.send(result)
                    # 发送成功后删除文件
                    delete_success = await self.image_manager.delete_image(filename)
                    if delete_success:
                        logger.info(f"Successfully sent and deleted {filename}")
                        return event.plain_result("老色批给你好了")
                    else:
                        return event.plain_result("图片发送成功，但清理失败")
                except Exception as e:
                    logger.warning(f"Image sending failed for {filename}: {str(e)}")
                    return event.plain_result("你怎么怎么自私，啊呸")
            else:
                return event.plain_result("滚滚滚，没有")

        except Exception as e:
            logger.error(f"Error handling image request: {str(e)}")
            return event.plain_result(f"处理图片请求失败: {str(e)}")

    # 可选：插件卸载时清理剩余图片
    async def terminate(self):
        """插件卸载时清理图片"""
        try:
            image_files = await self.image_manager.get_image_list()
            for file in image_files:
                await self.image_manager.delete_image(file)
            logger.info("Plugin terminated, cleaned up remaining images")
        except Exception as e:
            logger.error(f"Error cleaning up on termination: {str(e)}")