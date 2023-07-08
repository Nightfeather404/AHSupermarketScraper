import collections
import random
import re
import urllib.parse
import asyncio
import aiohttp
from bs4 import BeautifulSoup

albert_heijn_url = "https://www.ah.nl"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
}
ProductInfo = collections.namedtuple('ProductInfo', ['link', 'calories'])


async def fetch_product_categories(session):
    url = albert_heijn_url + "/producten"
    async with session.get(url) as response:
        content = await response.text()
        soup = BeautifulSoup(content, "html.parser")
        products_content = soup.find(id="start-of-content")
        product_categories = products_content.find_all("div", class_=re.compile("^product-category-overview_category"))
        product_categories_links = [product_category.findNext("a")["href"] for product_category in product_categories]
        return product_categories_links


async def fetch_category_page(session, category_link):
    url = urllib.parse.urljoin(albert_heijn_url, category_link)
    async with session.get(url) as response:
        return await response.text()


async def fetch_product_page(session, product_link):
    url = urllib.parse.urljoin(albert_heijn_url, product_link)
    async with session.get(url) as response:
        return await response.text()


async def get_products_info_within_calorie_range(max_calories=300, rate_limit=5):
    all_products_info = []
    connector = aiohttp.TCPConnector(limit=rate_limit, limit_per_host=rate_limit, ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        product_categories_links = await fetch_product_categories(session)
        tasks = []

        for i, product_categories_link in enumerate(product_categories_links):
            task = asyncio.ensure_future(fetch_category_page(session, product_categories_link))
            tasks.append(task)
            await asyncio.sleep(random.uniform(3, 5)) # Introduce a delay between requests

            product_category_page = await task
            product_category_content = BeautifulSoup(product_category_page, "html.parser").find(id="start-of-content")
            product_cards = product_category_content.find_all(attrs={"data-testhook": "product-card"})

            for product_card in product_cards:
                product_link = product_card.find("a")["href"]
                task = asyncio.ensure_future(fetch_product_page(session, product_link))
                tasks.append(task)
                await asyncio.sleep(random.uniform(3, 5))  # Introduce a delay between requests

                product_page = await task
                product_content = BeautifulSoup(product_page, "html.parser").find(id="start-of-content")
                calories_data_element = product_content.find('td', string=lambda table_data_text: table_data_text and 'kcal' in table_data_text)
                # check if product page contains nutritional values data
                if calories_data_element is None:
                    break
                text = calories_data_element.text
                calories = re.search(r'\((\d+) kcal\)', text)
                if calories:
                    calorie_value_of_product = int(calories.group(1))
                    if calorie_value_of_product <= max_calories:
                        product_info = ProductInfo(link=product_link,
                                                   calories=str(calorie_value_of_product) + " kcal per 100 Gram")
                        all_products_info.append(product_info)
                        print("\nproduct link: ", product_info.link)
                        print("calories: ", product_info.calories)

    return all_products_info


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    products_info = loop.run_until_complete(get_products_info_within_calorie_range(250, 5))
    print("products info: ", products_info)
    loop.close()
