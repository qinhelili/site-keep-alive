import os
import asyncio
import re
import requests
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# --- 配置与变量 ---
log_buffer = []
site_urls_env = os.environ.get("SITE_URLS", "")
site_urls = [item.strip() for item in site_urls_env.split(",") if item.strip()]

GROUP_INDEX = int(os.environ.get("GROUP_INDEX", 1))
TOTAL_GROUPS = int(os.environ.get("TOTAL_GROUPS", 4))
grouped_urls = [url for i, url in enumerate(site_urls) if i % TOTAL_GROUPS == GROUP_INDEX - 1]

GITHUB_EVENT_SCHEDULE = os.environ.get("GITHUB_EVENT_SCHEDULE", "") or "手动"

# 并发数控制 (建议 3-5, GitHub Actions 环境内存有限)
MAX_CONCURRENT_TASKS = 3

fail_msgs = ["Invalid credentials.", "Not connected to server.", "Error with the login"]
success_texts = [
    "Elena's Blog", "Carter's Blog", "Camille's Blog", "Adrien's Blog",
    "陈安的博客", "李岩的博客", "Logan的博客", "Ray的博客",
    "Starry serenade", "服务正常", "Hello Snippets", "Welcome to nginx!"
]

# 预编译正则，提升匹配速度
SUCCESS_REGEX = re.compile("|".join(map(re.escape, success_texts)), re.IGNORECASE)
FAIL_REGEX = re.compile("|".join(map(re.escape, fail_msgs)), re.IGNORECASE)


def log(msg):
    print(msg)
    log_buffer.append(msg)


async def handle_visit(url, context, sem):
    """单个 URL 的访问逻辑"""
    async with sem:  # 限制并发
        page = await context.new_page()
        try:
            # 优化点：使用 domcontentloaded 替代 networkidle，速度提升 50% 以上
            # 如果网站主要是静态内容，domcontentloaded 足够了
            await page.goto(url, timeout=20000, wait_until="networkidle")

            # 这里的等待时间根据需要缩短
            await asyncio.sleep(2)

            # 获取页面文本内容进行一次性正则匹配，比循环调用 get_by_text 块
            content = await page.content()

            # 1. 检查成功标识
            success_match = SUCCESS_REGEX.search(content)
            if success_match:
                # success_match.group() 就能拿到具体匹配到的那个词
                log(f"✅ {url} 访问成功 (命中: '{success_match.group()}')")
                return  # 成功了就直接结束当前任务

            # 2. 检查失败标识
            fail_match = FAIL_REGEX.search(content)
            if fail_match:
                log(f"❌ {url} 访问失败 (匹配到错误: '{fail_match.group()}')")
            else:
                # 3. 既没成功也没失败
                log(f"⚠️ {url} 未知状态 (未匹配到任何标识词)")

        except Exception as e:
            log(f"❌ {url} 异常: {type(e).__name__}")
        finally:
            await page.close()


async def visit_site():
    sem = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 优化点：减小 Viewport 尺寸可以减少渲染开销
        context = await browser.new_context(viewport={'width': 800, 'height': 600})

        # 按照要求：一直保留一个空白页
        blank_page = await context.new_page()

        log(f"🚀 开始并发访问 分组{GROUP_INDEX}，共 {len(grouped_urls)} 个网址")

        # 1. 计算中值, 把网址列表平分为两批
        mid = len(grouped_urls) // 2
        batch1_urls = grouped_urls[:mid]
        batch2_urls = grouped_urls[mid:]

        log(f"🚀 开始执行第一批任务 (共 {len(batch1_urls)} 个)")
        if batch1_urls:
            tasks1 = [handle_visit(url, context, sem) for url in batch1_urls]
            # 并发执行
            await asyncio.gather(*tasks1)

        # 可以在两批之间加一个短暂停顿, 让第一批的资源彻底释放
        log("⏳ 第一批完成, 等待 5 秒后开始第二批...")
        await asyncio.sleep(5)

        log(f"🚀 开始执行第二批任务 (共 {len(batch2_urls)} 个)")
        if batch2_urls:
            tasks2 = [handle_visit(url, context, sem) for url in batch2_urls]
            # 并发执行
            await asyncio.gather(*tasks2)

        await asyncio.sleep(5)
        await blank_page.close()
        await context.close()
        await browser.close()


def send_tg_log():
    # ... (保持原有的 requests 代码不变)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return

    beijing_now = datetime.utcnow() + timedelta(hours=8)
    now_str = beijing_now.strftime("%Y-%m-%d %H:%M:%S")
    final_msg = f"📌 网站保活日志\n⏰ {GITHUB_EVENT_SCHEDULE}\n🕒 {now_str}\n\n" + "\n".join(log_buffer)

    for i in range(0, len(final_msg), 3900):
        try:
            requests.get(f"https://api.telegram.org/bot{token}/sendMessage",
                         params={"chat_id": chat_id, "text": final_msg[i:i + 3900]}, timeout=10)
        except:
            pass


async def main():
    await visit_site()
    send_tg_log()

if __name__ == "__main__":
    asyncio.run(main())
