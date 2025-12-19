import os
import time
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# -------------------------------
log_buffer = []
# 从环境变量解析多个URL
site_urls_env = os.environ.get("SITE_URLS", "")
site_urls = []
for item in site_urls_env.split(","):
    site_urls.append(item.strip())

# 当前 Job 的分组信息
GROUP_INDEX = int(os.environ.get("GROUP_INDEX", 1))
TOTAL_GROUPS = int(os.environ.get("TOTAL_GROUPS", 4))

# 按组分配 URL
grouped_urls = [url for i, url in enumerate(site_urls) if i % TOTAL_GROUPS == GROUP_INDEX - 1]

# 获取触发事件
GITHUB_EVENT_SCHEDULE = os.environ.get("GITHUB_EVENT_SCHEDULE", "") or "手动"

fail_msgs = [
    "Invalid credentials.",
    "Not connected to server.",
    "Error with the login: login size should be between 2 and 50 (currently: 1)"
]
success_texts = [
    "远岛日记",
    "午夜随想",
    "Logan的旅行笔记",
    "Ray的阅览室",
    "Starry serenade",
    "服务正常",
    "Hello Snippets",
    "Welcome to nginx!"
]


def log(msg):
    print(msg)
    log_buffer.append(msg)


# Telegram 推送函数
def send_tg_log():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ Telegram 未配置，跳过推送")
        return

    utc_now = datetime.utcnow()
    beijing_now = utc_now + timedelta(hours=8)
    now_str = "北京时间: " + beijing_now.strftime("%Y-%m-%d %H:%M:%S")

    final_msg = f"📌 网站保活执行日志\n⏰ {GITHUB_EVENT_SCHEDULE} 触发\n🕒 {now_str}\n\n" + "\n".join(log_buffer)

    for i in range(0, len(final_msg), 3900):
        chunk = final_msg[i:i + 3900]
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/sendMessage",
                params={"chat_id": chat_id, "text": chunk},
                timeout=10
            )
            if resp.status_code == 200:
                print(f"✅ Telegram 推送成功 [{i // 3900 + 1}]")
            else:
                print(f"⚠️ Telegram 推送失败 [{i // 3900 + 1}]: HTTP {resp.status_code}, 响应: {resp.text}")
        except Exception as e:
            print(f"⚠️ Telegram 推送异常 [{i // 3900 + 1}]: {e}")


def visit_site(playwright, site_url):
    try:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(site_url)
        page.wait_for_load_state("networkidle")
        time.sleep(5)

        # 检查是否存在任意一个成功的标识
        success_found = False
        for success_text in success_texts:
            if page.query_selector(f"text={success_text}"):
                success_found = True
                log(f"✅ 网址 {site_url} 访问成功, 找到了文本 '{success_text}'")
                break

        if not success_found:  # 如果没有找到成功标识
            failed_msg = None
            for msg in fail_msgs:
                if page.query_selector(f"text={msg}"):
                    failed_msg = msg
                    break
            if failed_msg:
                log(f"❌ 网址 {site_url} 访问失败: {failed_msg}")
            else:
                # 获取页面内容，可能包含更详细的错误信息
                page_content = page.content()
                log(f"❌ 网址 {site_url} 访问失败: 未知错误")
                print(f"❌ 网址 {site_url} 页面内容:\n{page_content}")

        context.close()
        browser.close()

    except Exception as e:
        log(f"❌ 网址 {site_url} 访问异常: {e}")


def run():
    log(f"🚀 开始访问 分组{GROUP_INDEX} 的网址")
    with sync_playwright() as playwright:
        for site_url in grouped_urls:
            visit_site(playwright, site_url)
            time.sleep(5)


if __name__ == "__main__":
    run()
    send_tg_log()  # 发送tg日志
