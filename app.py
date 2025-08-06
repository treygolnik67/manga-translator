# app.py — Полный код сайта-переводчика манги

import streamlit as st
from PIL import Image
import fitz  # PyMuPDF
import zipfile
import os
import tempfile
from pathlib import Path
import easyocr
from transformers import pipeline
from g4f.client import Client

# Настройка
TEMP_DIR = Path(tempfile.mkdtemp())
reader = easyocr.Reader(['ja', 'en'])  # Японский + английский
translator_en_ru = pipeline("translation_en_to_ru", model="Helsinki-NLP/opus-mt-en-ru")

# --- Функция: конвертация файла в изображения ---
def convert_to_images(uploaded_file):
    file_ext = Path(uploaded_file.name).suffix.lower()
    image_list = []
    temp_path = TEMP_DIR / uploaded_file.name

    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    try:
        if file_ext in [".png", ".jpg", ".jpeg"]:
            image_list.append(Image.open(temp_path))
        elif file_ext == ".pdf":
            st.info("Конвертирую PDF в изображения...")
            pdf_document = fitz.open(temp_path)
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                image_list.append(img)
            pdf_document.close()
        elif file_ext == ".cbz":
            st.info("Распаковываю CBZ...")
            with zipfile.ZipFile(temp_path, 'r') as cbz:
                for file in sorted(cbz.namelist()):
                    if file.lower().endswith((".png", ".jpg", ".jpeg")):
                        with cbz.open(file) as img_file:
                            img = Image.open(img_file)
                            image_list.append(img)
        else:
            st.error(f"Формат {file_ext} не поддерживается.")
            return None
    except Exception as e:
        st.error(f"Ошибка: {e}")
        return None
    return image_list

# --- Функция: OCR + перевод ---
def ocr_and_translate(image):
    results = reader.readtext(image)
    jp_text = " ".join([res[1] for res in results if res[2] > 0.1])
    if not jp_text.strip():
        return "Текст не найден", "Текст не найден", "Текст не найден"

    client = Client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Переведи на английский: {jp_text}"}]
    )
    en_text = response.choices[0].message.content

    ru_text = translator_en_ru(en_text)[0]['translation_text']

    return jp_text, en_text, ru_text

# --- Интерфейс ---
st.title("🌐 MangaTranslator — Переводчик манги")

uploaded_file = st.file_uploader(
    "Загрузите главу (PDF, CBZ, JPG, PNG)",
    type=["pdf", "cbz", "png", "jpg", "jpeg"]
)

if uploaded_file:
    with st.spinner("Конвертирую файл..."):
        images = convert_to_images(uploaded_file)

    if images:
        st.success(f"✅ Загружено {len(images)} страниц")
        page = st.slider("Выберите страницу", 1, len(images), 1)
        img = images[page - 1]
        st.image(img, caption=f"Страница {page}", use_column_width=True)

        if st.button("Распознать и перевести"):
            with st.spinner("Распознаём и переводим..."):
                jp, en, ru = ocr_and_translate(img)

            st.subheader("🇯🇵 Японский текст:")
            st.write(jp)
            st.subheader("🇬🇧 Английский перевод:")
            st.write(en)
            st.subheader("🇷🇺 Русский перевод:")
            st.write(ru)