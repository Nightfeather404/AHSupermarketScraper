import collections
import random
import re
import urllib.parse
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup
from fpdf import FPDF

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

            load_more_element = BeautifulSoup(await task, "html.parser").find(attrs={"data-testhook": "load-more"})
            span_element = load_more_element.find_previous_sibling("span", class_="typography_root__Om3Wh")

            max_pagination = 1
            if span_element:
                text = span_element.text
                numbers = re.findall(r'\d+', text)
                if len(numbers) >= 2:
                    total_results = int(numbers[1])
                    products_per_page = 36
                    max_pagination = (total_results + products_per_page - 1) // products_per_page

            product_category_link = albert_heijn_url + product_categories_link + "?page=" + str(max_pagination)

            task = asyncio.ensure_future(fetch_category_page(session, product_category_link))
            tasks.append(task)
            await asyncio.sleep(random.uniform(3, 5))  # Introduce a delay between requests

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

                if product_content is None:
                    break

                # TODO: get product name
                product_name = product_content.find("h1", class_=re.compile("^product-card-header_title")).text
                product_price = product_content.find(attrs={"data-testhook": "price-amount"}).text
                print("product price: ", product_price)
                # TODO: get product price
                # TODO: get product summary
                # TODO: get product info
                # TODO: get product image src
                # TODO: get product content and weight (e.g: 186 gram in total)
                # TODO: get proteins from nutritional table
                # TODO: extend this function to filter products also within protein range (decimals)
                # TODO: get nutritional table measurement (e.g: per 100 gram or per 100 millimeters)

                calories_data_element = product_content.find('td', string=lambda
                    table_data_text: table_data_text and 'kcal' in table_data_text)
                # check if product page contains nutritional values data
                if calories_data_element is None:
                    break
                text = calories_data_element.text
                calories = re.search(r'\((\d+) kcal\)', text)
                if calories:
                    calorie_value_of_product = int(calories.group(1))
                    if calorie_value_of_product <= max_calories:
                        product_info = ProductInfo(link=albert_heijn_url + str(product_card.find("a")["href"]),
                                                   calories=str(calorie_value_of_product) + " kcal per 100 Gram")
                        all_products_info.append(product_info)
                        print("\nproduct link: ", product_info.link)
                        print("calories: ", product_info.calories)

    # Sort products by calories from lowest to highest
    sorted_products_info = sorted(all_products_info, key=lambda x: int(x.calories.split()[0]))

    return sorted_products_info


async def create_pdf(products_info, max_calories):
    pdf = FPDF()
    pdf.add_page()

    # Set font style and size
    pdf.set_font("Arial", size=12)

    # Add content to the PDF
    for product_info in products_info:
        link = product_info.link
        calories = product_info.calories

        # Write the product link and calories to the PDF
        pdf.cell(0, 10, f"Product Link: {link}", ln=True)
        pdf.cell(0, 10, f"Calories: {calories}", ln=True)
        pdf.cell(0, 10, "", ln=True)  # Add empty line between entries

    # Save the PDF
    pdf.output(f"products_info_within_calorie_range_of_{max_calories}.pdf")
    print("PDF created!")


async def get_sorted_products_info_json(sorted_products_info):
    sorted_products_info_json = []
    for product_info in sorted_products_info:
        product_info_json = {
            'link': product_info.link,
            'calories': product_info.calories
        }
        sorted_products_info_json.append(product_info_json)

    return json.dumps(sorted_products_info_json)


async def save_json_to_file(filename, data):
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    products_info = loop.run_until_complete(get_products_info_within_calorie_range(250, 5))
    sorted_products_info_json = loop.run_until_complete(get_sorted_products_info_json(products_info))
    loop.run_until_complete(save_json_to_file("sorted_products_info.json", sorted_products_info_json))
    loop.run_until_complete(create_pdf(products_info, 250))
    loop.close()

