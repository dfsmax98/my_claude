"""声纹识别平台服务层。"""

from .config import load_platform_config

__all__ = ["VoiceprintPlatformService", "load_platform_config"]


def __getattr__(name):
    if name == "VoiceprintPlatformService":
        from .service import VoiceprintPlatformService

        return VoiceprintPlatformService
    raise AttributeError(name)
