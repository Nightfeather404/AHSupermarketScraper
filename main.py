import random
import time
import re
import urllib.parse
import asyncio
import aiohttp
import proxygrab
import async_timeout
from proxyscrape import create_collector
from bs4 import BeautifulSoup

albert_heijn_url = "https://www.ah.nl"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
}


async def fetch_product_categories(session):
    url = albert_heijn_url + "/producten"
    async with session.get(url) as response:
        content = await response.text()
        soup = BeautifulSoup(content, "html.parser")
        products_content = soup.find(id="start-of-content")
        product_categories = products_content.find_all("div", class_=re.compile("^product-category-overview_category"))
        product_categories_links = [product_category.findNext("a")["href"] for product_category in product_categories]
        return product_categories_links


async def fetch_category_page(session, category_link, proxy):
    url = urllib.parse.urljoin(albert_heijn_url, category_link)
    async with session.get(url, proxy=proxy) as response:
        return await response.text()


async def fetch_product_page(session, product_link, proxy):
    url = urllib.parse.urljoin(albert_heijn_url, product_link)
    async with session.get(url, proxy=proxy) as response:
        return await response.text()


async def get_random_proxy():
    collector = create_collector('my-collector', 'http')
    while True:
        proxy = collector.get_proxy()
        proxy_str = f"{proxy.host}:{proxy.port}"
        print(proxy_str)
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=5)  # Set a timeout of 5 seconds
                async with session.get("https://www.google.com", proxy=f"http://{proxy_str}",
                                       timeout=timeout) as response:
                    if response.status == 200:
                        print('Success!')
                        return f"http://{proxy_str}"
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass


async def get_product_links(max_calories=300, rate_limit=5, sleep_time=1.0):
    all_product_links = []
    connector = aiohttp.TCPConnector(limit=rate_limit, limit_per_host=rate_limit, ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        product_categories_links = await fetch_product_categories(session)
        tasks = []
        for i, product_categories_link in enumerate(product_categories_links):
            proxy = await get_random_proxy()
            task = asyncio.ensure_future(fetch_category_page(session, product_categories_link, proxy))
            tasks.append(task)

        category_pages = await asyncio.gather(*tasks)

        start_time = time.time()

        load_more_element = BeautifulSoup(category_pages[0], "html.parser").find(attrs={"data-testhook": "load-more"})
        span_element = load_more_element.find_previous_sibling("span", class_="typography_root__Om3Wh")

        max_pagination = 1
        if span_element:
            text = span_element.text
            numbers = re.findall(r'\d+', text)
            if len(numbers) >= 2:
                total_results = int(numbers[1])
                products_per_page = 36
                max_pagination = (total_results + products_per_page - 1) // products_per_page

        tasks = []
        for i, product_categories_link in enumerate(product_categories_links):
            product_category_link = albert_heijn_url + product_categories_link + "?page=" + str(max_pagination)
            proxy = await get_random_proxy()
            task = asyncio.ensure_future(fetch_category_page(session, product_category_link, proxy))
            tasks.append(task)

        product_category_pages = await asyncio.gather(*tasks)

        tasks = []
        for i, category_page in enumerate(product_category_pages):
            product_category_content = BeautifulSoup(category_page, "html.parser").find(id="start-of-content")
            product_cards = product_category_content.find_all(attrs={"data-testhook": "product-card"})

            for product_card in product_cards:
                product_link = product_card.find("a")["href"]
                proxy = await get_random_proxy()
                task = asyncio.ensure_future(fetch_product_page(session, product_link, proxy))
                tasks.append(task)
                await asyncio.sleep(sleep_time)  # Introduce a delay between requests

        product_pages = await asyncio.gather(*tasks)

        for product_page, product_link in zip(product_pages, all_product_links):
            product_content = BeautifulSoup(product_page, "html.parser").find(id="start-of-content")
            calories_table_data_element = product_content \
                .find('td', string=lambda table_data_text: table_data_text and 'kcal' in table_data_text)
            text = calories_table_data_element.text
            calories = re.search(r'\((\d+) kcal\)', text)
            if calories:
                calorie_value_of_product = int(calories.group(1))
                if calorie_value_of_product <= max_calories:
                    all_product_links.append(product_link)
                    print("product link: ", product_link)

        end_time = time.time()

    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time} seconds")

    return all_product_links


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    product_links = loop.run_until_complete(get_product_links(250, 5, 0.1))
    print("product links: ", product_links)
    loop.close()
