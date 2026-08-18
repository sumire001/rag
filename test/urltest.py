import requests
from bs4 import BeautifulSoup
from urllib.parse import quote


def get_baike_info(keyword):
    # 1. 构造 URL
    url = f'https://baike.baidu.com/item/{quote(keyword)}'

    # 2. 构造请求头 (伪装成浏览器)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://baike.baidu.com/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    try:
        # 3. 发送请求获取 HTML
        response = requests.get(url, headers=headers, timeout=10)

        # 检查状态码
        if response.status_code != 200:
            return f"请求失败，状态码: {response.status_code}"

        # 4. 解析 HTML
        soup = BeautifulSoup(response.text, 'lxml')

        # --- 提取摘要 ---
        # 摘要通常在 class="lemma-summary" 的 div 中
        summary_div = soup.find('div', class_='lemma-summary')
        summary = summary_div.get_text(strip=True) if summary_div else "未找到摘要"

        # --- 提取基本信息栏 (Key-Value) ---
        basic_info = {}
        # 基本信息通常在 class="basic-info" 或 "summary-info" 中
        # 注意：百度百科改版频繁，类名可能会变，这里用比较通用的选择器
        info_items = soup.select('.basic-info .name, .summary-info .name')
        info_values = soup.select('.basic-info .value, .summary-info .value')

        for name, value in zip(info_items, info_values):
            key = name.get_text(strip=True).replace('\xa0', '')  # 去除空格
            val = value.get_text(strip=True)
            basic_info[key] = val

        return {
            "keyword": keyword,
            "summary": summary,
            "basic_info": basic_info
        }

    except Exception as e:
        return f"发生错误: {str(e)}"


# 测试运行
if __name__ == '__main__':
    result = get_baike_info("深度学习")

    if isinstance(result, dict):
        print(f"【词条】: {result['keyword']}")
        print(f"【摘要】: {result['summary'][:100]}...")  # 只打印前100字
        print(f"【基本信息】:")
        for k, v in result['basic_info'].items():
            print(f"  {k}: {v}")
    else:
        print(result)