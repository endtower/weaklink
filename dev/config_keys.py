"""管理服务与 Core 共用的部署配置键、默认值和接入点标签。"""

from urllib.parse import urlparse

DEFAULT_COMMON_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
DEFAULT_COMMON_MODEL = "DeepSeek-V4.1-Flash"
DEFAULT_EMBEDDING_MODEL = "doubao-embedding-vision"
DEFAULT_ONEBOT_ENABLED = True

PROVIDER_LABELS = {
    "ark.cn-beijing.volces.com": "火山方舟",
    "amr-link.open-design.ai": "open-design中转",
    "opencode.ai": "opencode",
    "api.commandcode.ai": "commandcode",
    "open.bigmodel.cn": "智谱GLM",
    "croissant.521911.xyz": "croissant",
    "api.deepseek.com": "DeepSeek官方",
}


def resolve_provider_label(base_url: str) -> str:
    """把接入点归类为提供商标签，未知接入点显示其主机名。"""
    url = (base_url or "").strip()
    for host, label in PROVIDER_LABELS.items():
        if host in url:
            return label
    if not url:
        return "未知接入点"
    return urlparse(url).hostname or url

CONFIG_OVERRIDE_KEYS = (
    "MASTER_ID", "MASTER_NAME", "ASSISTANT_QQ", "ASSISTANT_NAME", "ASSISTANT_NICK_NAME",
    "WEB_ENABLED", "WEB_WS_HOST", "WEB_WS_PORT", "WEB_WS_PATH", "WEB_ACCESS_TOKEN",
    "ONEBOT_ENABLED", "ONEBOT_WS_HOST", "ONEBOT_WS_PORT", "ONEBOT_WS_PATH",
    "ONEBOT_ACCESS_TOKEN",
    "INGRESS_API_PORT",
    "BRIDGE_ENABLED", "BRIDGE_CONNECTION_ID", "BRIDGE_BASE_URL", "BRIDGE_TOKEN",
    "BRIDGE_TUNNEL_ENABLED", "BRIDGE_TUNNEL_PI_HOST", "BRIDGE_TUNNEL_PI_USER",
    "BRIDGE_TUNNEL_KEY_PATH", "BRIDGE_TUNNEL_REMOTE_PORT",
    "MAIN_HOST", "MAIN_PORT",
    "OPENCODE_API_KEY", "OPENCODE_BASE_URL", "FLASH_API_KEY", "FLASH_BASE_URL",
    "CONVERSATION_API_KEY", "CONVERSATION_BASE_URL",
    "PERSONA_API_KEY", "PERSONA_BASE_URL",
    "VISION_API_KEY", "VISION_BASE_URL",
    "VECTOR_API_KEY", "VECTOR_BASE_URL",
    "LLM_FLASH", "LLM_CONVERSATION", "LLM_PERSONA", "LLM_PRO", "LLM_VISION",
    "LLM_EMBEDDING",
)
