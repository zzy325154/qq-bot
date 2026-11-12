"""Windows 桌面通知。失败就静默，不影响机器人。"""

import logging
import subprocess

logger = logging.getLogger(__name__)

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$nodes = $template.GetElementsByTagName('text')
$nodes.Item(0).AppendChild($template.CreateTextNode('__TITLE__')) > $null
$nodes.Item(1).AppendChild($template.CreateTextNode('__BODY__')) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('QQ Bot').Show($toast)
"""


def _quote(text: str) -> str:
    return str(text).replace("'", "''")[:120]


def toast(title: str, body: str) -> bool:
    script = SCRIPT.replace("__TITLE__", _quote(title)).replace("__BODY__", _quote(body))
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("桌面通知失败: %s", exc)
        return False
