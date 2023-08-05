import collections
import random
import re
import urllib.parse
import asyncio
import aiohttp
import json
from bs4 import BeautifulSoup

albert_heijn_url = "https://www.ah.nl"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
}
ProductInfo = collections.namedtuple('ProductInfo', ['name', 'price', 'imageSrc', 'link', 'summary', 'description',
                                                     'measuredContent', 'calories', 'protein'])


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


async def get_products_info_within_calorie_range(min_proteins=None, max_calories=300, rate_limit=5):
    all_products_info = []
    connector = aiohttp.TCPConnector(limit=rate_limit, limit_per_host=rate_limit, ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        product_categories_links = await fetch_product_categories(session)
        tasks = []

        for i, product_categories_link in enumerate(product_categories_links):
            task = asyncio.ensure_future(fetch_category_page(session, product_categories_link))
            tasks.append(task)

            load_more_element = BeautifulSoup(await task, "html.parser").find(attrs={"data-testhook": "load-more"})
            span_element = None

            if load_more_element:
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
            await asyncio.sleep(random.uniform(5, 10))  # Introduce a delay between requests

            product_category_page = await task
            product_category_content = BeautifulSoup(product_category_page, "html.parser").find(id="start-of-content")
            product_cards = product_category_content.find_all(attrs={"data-testhook": "product-card"})

            for product_card in product_cards:
                product_link = product_card.find("a")["href"]
                task = asyncio.ensure_future(fetch_product_page(session, product_link))
                tasks.append(task)
                await asyncio.sleep(random.uniform(5, 10))  # Introduce a delay between requests

                product_page = await task
                product_content = BeautifulSoup(product_page, "html.parser").find(id="start-of-content")

                if product_content is None:
                    break

                # Extract product information
                product_name_element = product_content.find("h1", class_=re.compile("^product-card-header_title"))
                product_name = product_name_element.text if product_name_element else None

                product_price_element = product_content.find(attrs={"data-testhook": "price-amount"})
                product_price = product_price_element.text if product_price_element else None

                product_summary_element = product_content.find(attrs={"data-testhook": "product-summary"})
                product_summary = product_summary_element.text if product_summary_element else None

                product_info_description_element = product_content.find(
                    attrs={"data-testhook": "product-info-description"})
                product_info_description = product_info_description_element.text if product_info_description_element else None

                product_image_src_element = product_content.find(attrs={"data-testhook": "product-image"})
                product_image_src = product_image_src_element["src"] if product_image_src_element else None

                product_info_content_element = product_content.find("h4", class_=re.compile(
                    "^product-info-contents_subHeading"))
                product_info_content = product_info_content_element.find_next_sibling(
                    "p").text if product_info_content_element else None

                # Extract nutritional information
                nutritional_table = product_content.find("table", class_=re.compile("^product-info-nutrition_table"))
                if nutritional_table:
                    calories_data_element = nutritional_table.find('td', string=lambda
                        table_data_text: table_data_text and 'kcal' in table_data_text)
                    protein_data_element = nutritional_table.find('td', string='Eiwitten')
                else:
                    calories_data_element = None
                    protein_data_element = None

                # check if product page contains nutritional data (calories and proteins)
                if calories_data_element and protein_data_element is None:
                    break

                calories_data_element_text = calories_data_element.text if calories_data_element else None
                protein_data_element_text = protein_data_element.find_next_sibling(
                    'td').text if protein_data_element else None

                # Extract calories and proteins
                calories = re.search(r'(\d+)\s*kcal',
                                     calories_data_element_text) if calories_data_element_text else None
                proteins = re.search(r'\d+(\.\d+)?', protein_data_element_text) if protein_data_element_text else None

                if calories is not None:
                    calorie_value_of_product = int(calories.group(1))
                else:
                    calorie_value_of_product = 0
                if proteins is not None:
                    proteins_value_of_product = float(proteins.group())
                else:
                    proteins_value_of_product = 0.0

                # Handle cases where calories and proteins are not available
                if calorie_value_of_product == 0:
                    calories_message = "Calories data could not be retrieved."
                else:
                    calories_message = str(calorie_value_of_product) + " kcal per 100 Gram"

                if proteins_value_of_product in [None, 0]:
                    proteins_message = "Protein data could not be retrieved."
                else:
                    proteins_message = str(proteins_value_of_product) + " g"

                # Filter based on calorie range and protein content (if provided)
                if calorie_value_of_product <= max_calories:
                    if min_proteins is None or proteins_value_of_product >= min_proteins:
                        product_info = ProductInfo(
                            name=product_name,
                            price=product_price,
                            imageSrc=product_image_src,
                            link=albert_heijn_url + str(product_card.find("a")["href"]),
                            summary=product_summary,
                            description=product_info_description,
                            measuredContent=product_info_content,
                            calories=calories_message,
                            protein=proteins_message)
                        all_products_info.append(product_info)
                        print("product_info: ", product_info)

    # Sort products by calories and proteins from lowest to highest
    sorted_products_info = sorted(all_products_info, key=lambda x: (int(x.calories.split()[0]),
                                                                    float(x.protein.split()[0])
                                                                    if x.protein else float('inf')))
    return sorted_products_info


async def get_sorted_products_info_json(sorted_products_info):
    sorted_products_info_json = []
    for product_info in sorted_products_info:
        product_info_json = {
            'name': product_info.name,
            'price': product_info.price,
            'imageSrc': product_info.imageSrc,
            'link': product_info.link,
            'summary': product_info.summary,
            'description': product_info.description,
            'measuredContent': product_info.measuredContent,
            'calories': product_info.calories,
            'protein': product_info.protein
        }
        sorted_products_info_json.append(product_info_json)

    return json.dumps(sorted_products_info_json)


async def save_json_to_file(filename, data):
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    products_info = loop.run_until_complete(get_products_info_within_calorie_range(min_proteins=5,
                                                                                   max_calories=250,
                                                                                   rate_limit=5))
    sorted_products_info_json = loop.run_until_complete(get_sorted_products_info_json(products_info))
    loop.run_until_complete(save_json_to_file("../static/sorted_products_info.json", sorted_products_info_json))
    loop.close()
