from db import ad_exists, add_ad
import requests
import random
import re
from bs4 import BeautifulSoup

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())

async def get_random_cars(
    min_price=500,
    max_price=3000,
    count=1,
    max_photos=10,
    max_pages=20,
    base_url: str | None = None
):
    headers = {"User-Agent": "Mozilla/5.0"}

    if base_url:
        urls = [base_url]
    else:
        urls = [
            f"https://cars.av.by/filter?price_usd[min]={min_price}&price_usd[max]={max_price}&page={random.randint(1, 10)}"
            for _ in range(max_pages)
        ]

    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=10)
        except requests.RequestException:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.find_all("div", class_="listing-item")
        if not items:
            continue

        random.shuffle(items)
        results = []

        for random_item in items:
            if len(results) >= count:
                break

            title_tag = random_item.find("a", class_="listing-item__link")
            link = "https://cars.av.by" + title_tag["href"] if title_tag else ""
            if not link or await ad_exists(link):
                continue

            title = title_tag.text.strip() if title_tag else "Без названия"

            price_tag = random_item.find("div", class_="listing-item__price-secondary")
            price_text = price_tag.text.strip().replace("≈", "").replace(" ", "") if price_tag else "—"

            location_tag = random_item.find("div", class_="listing-item__location")
            location_text = location_tag.text.strip() if location_tag else "Неизвестно"

            # --- параметры из card__params ---
            params_block = random_item.find("div", class_="listing-item__params")
            params_text = params_block.get_text(", ", strip=True) if params_block else ""
            params_text = clean_text(params_text)
            parts = [p.strip() for p in params_text.split(",") if p.strip()]

            year = next((p for p in parts if re.match(r"\d{4}", p)), "—").replace("г.", "").strip()
            mileage = next((p for p in parts if "км" in p), "—")
            transmission = next((p for p in parts if any(t in p.lower() for t in ["механика", "автомат", "вариатор", "робот"])), "—")

            # тип двигателя и объём
            engine_info = "—"
            engine_type = next((p for p in parts if any(x in p.lower() for x in ["бензин", "дизель", "электро", "гибрид", "газ"])), "")
            engine_volume = next((p for p in parts if "л" in p and not "км" in p), "")
            if engine_type or engine_volume:
                engine_info = f"{engine_type}, {engine_volume}".strip(", ")

            # --- вытаскиваем описание из объявления ---
            adv_soup = None
            try:
                adv_resp = requests.get(link, headers=headers, timeout=10)
                adv_soup = BeautifulSoup(adv_resp.text, "html.parser")
            except requests.RequestException:
                pass

            description = "Нет описания"
            if adv_soup:
                comment_block = adv_soup.find("div", class_="card__comment")
                if comment_block:
                    # Берём весь текст блока, а не только первый <p>
                    description = clean_text(comment_block.get_text(" ", strip=True))

            # --- привод из card__description ---
            drive = "—"
            if adv_soup:
                desc_block = adv_soup.find("div", class_="card__description")
                if desc_block:
                    desc_text = clean_text(desc_block.get_text(" ", strip=True))
                    drive = next((p for p in desc_text.split(",") if "привод" in p.lower()), "—").strip()

            # --- фото ---
            photos = []
            if adv_soup:
                gallery = adv_soup.select(".gallery__stage .gallery__frame img")
                for img in gallery:
                    url_img = img.get("data-src") or img.get("src")
                    if url_img and not url_img.startswith("data:image"):
                        photos.append(url_img)
                    if len(photos) >= max_photos:
                        break

            formatted_message = (
                f"🚗 {title}  📅 {year}\n"
                f"🛣 {mileage}  |⛽️ {engine_info}\n"
                f"📦 {transmission.title()} |⚙️ {drive}\n"
                f"📍 {location_text}\n"
                f"💰 {price_text}\n\n"
                f"{description}\n\n"
            )

            results.append({
                "title": title,
                "price": price_text,
                "location": location_text,
                "params": params_text,
                "description": description,
                "link": link,
                "photos": photos,
                "drive": drive,
                "engine_info": engine_info,
                "message": formatted_message
            })

            await add_ad(link)

        if results:
            return results

    return []


def clean_text(text: str) -> str:
    """Очищает текст и заменяет неразрывные пробелы, пробелы и запятые в числах."""
    if not text:
        return ""
    # заменяем неразрывные пробелы и узкие пробелы
    text = text.replace("\xa0", " ").replace(" ", " ")
    # заменяем запятые в числах на точки (например, 1,8 → 1.8)
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    # убираем лишние пробелы
    text = re.sub(r"\s+", " ", text)
    # убираем двойные запятые
    text = re.sub(r"(,\s*){2,}", ", ", text)
    return text.strip(",. \n\t")

def parse_single_car(url, max_photos=10):
    import re
    import requests
    from bs4 import BeautifulSoup

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # 🏷 Заголовок
    title_block = soup.find("h1")
    title = clean_text2(title_block.text) if title_block else "Без названия"
    title = re.sub(r"(?i)^Продажа\s+", "", title).strip()
    title = re.sub(r",?\s*\d{4}\s*г.*$", "", title)
    title = re.sub(r"\s+в\s+[A-ЯЁA-Z][а-яёa-z]+.*$", "", title)
    title = title.strip(",. ")

    # 🧩 Основные параметры (год, трансмиссия, объём, топливо, пробег)
    params_block = soup.find("div", class_="card__params")
    params_text = clean_text2(params_block.get_text(" ", strip=True)) if params_block else ""

    year = gearbox = engine = fuel = mileage = "—"

    # Извлекаем объём двигателя до разделения
    m = re.search(r"(\d+[.,]?\d*)\s*л", params_text.lower())
    if m:
        engine = m.group(1).replace(",", ".") + " л"

    # Теперь разбиваем остальные параметры по запятым
    parts = [p.strip() for p in params_text.split(",") if p.strip()]
    for p in parts:
        p_low = p.lower()

        if re.search(r"\d{4}\s*г", p_low):
            year = p.replace("г.", "").replace("г", "").strip()

        elif any(x in p_low for x in ["механика", "автомат", "вариатор", "робот"]):
            gearbox = p

        elif any(x in p_low for x in ["бензин", "дизель", "газ", "электро", "гибрид"]):
            fuel = p

        elif "км" in p_low:
            mileage = p

    # 🚗 Кузов, привод, цвет
    desc_block = soup.find("div", class_="card__description")
    desc_text = clean_text2(desc_block.get_text(", ", strip=True)) if desc_block else "—"
    drive = next((p.strip() for p in desc_text.split(",") if "привод" in p.lower()), "—")

    # ⚙️ Модификация
    mod_block = soup.find("div", class_="card__modification")
    mod_text = clean_text2(mod_block.get_text(" ", strip=True)) if mod_block else "—"
    if "Все параметры" in mod_text:
        mod_text = mod_text.replace("Все параметры", "").strip(",. ")

    # 📍 Локация
    loc_block = soup.find("div", class_="card__location")
    location = clean_text2(loc_block.text) if loc_block else "Неизвестно"

    # 💰 Цена
    price_block = soup.find("div", class_="card__price-secondary")
    price = price_block.text.strip().replace("≈", "").replace(" ", "") if price_block else "—"

    # 📝 Описание
    comment_block = soup.find("div", class_="card__comment")
    if comment_block:
        # добавляем разделитель " " между строками
        description = clean_text2(comment_block.get_text(" ", strip=True))
        description = re.sub(r"(?i)^Описание", "", description).strip()
    else:
        description = "Нет описания"

    MAX_TG_CAPTION = 900
    if len(description) > MAX_TG_CAPTION:
        description = description[:MAX_TG_CAPTION - 3].rsplit(" ", 1)[0] + "..."

    # 🖼 Фото
    photos = []
    gallery = soup.select(".gallery__stage .gallery__frame img")
    for img in gallery:
        src = img.get("data-src") or img.get("src")
        if src and not src.startswith("data:image"):
            photos.append(src)
        if len(photos) >= max_photos:
            break

    # ❗️ Удаляем последнее фото, если оно дублирует предпоследнее
    if len(photos) > 1 and photos[-1] == photos[-2]:
        photos.pop()


    # 🛠 Объединяем тип и объём двигателя
    engine_info = "—"
    if fuel != "—" or engine != "—":
        engine_info = f"{fuel}, {engine}".strip(", ")

    return {
        "title": title,
        "year": year,
        "mileage": mileage,
        "gearbox": gearbox,
        "drive": drive,
        "engine_info": engine_info,
        "location": location,
        "price": price,
        "description": description,
        "photos": photos,
        "link": url,
    }


def clean_text2(text: str) -> str:
    """Убирает мусорные пробелы, неразрывные пробелы и двойные запятые"""
    import re
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace(" ", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(,\s*){2,}", ", ", text)
    return text.strip(",. \n\t")




