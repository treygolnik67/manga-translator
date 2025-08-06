# app.py — Умный переводчик манги (оптимизирован для Render)

import streamlit as st
from PIL import Image
import fitz  # PyMuPDF
import zipfile
import tempfile
from pathlib import Path
import easyocr
from g4f.client import Client

# Настройка
TEMP_DIR = Path(tempfile.mkdtemp())
reader = easyocr.Reader(['ja'])  # Только японский — меньше памяти

# --- Функция: конвертация файла в изображения ---
def convert_to_images(uploaded_file):
    file_ext = uploaded_file.name.lower().split('.')[-1]
    image_list = []
    temp_path = TEMP_DIR / uploaded_file.name

    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    try:
        if file_ext in ["png", "jpg", "jpeg"]:
            image_list.append(Image.open(temp_path))
        elif file_ext == "pdf":
            st.info("📄 Конвертирую PDF в изображения...")
            pdf_document = fitz.open(temp_path)
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(dpi=120)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                image_list.append(img)
            pdf_document.close()
        elif file_ext == "cbz":
            st.info("📦 Распаковываю CBZ...")
            with zipfile.ZipFile(temp_path, 'r') as cbz:
                for file in sorted(cbz.namelist()):
                    if file.lower().endswith((".png", ".jpg", ".jpeg")):
                        with cbz.open(file) as img_file:
                            img = Image.open(img_file)
                            image_list.append(img)
        else:
            st.error(f"❌ Формат .{file_ext} не поддерживается.")
            return None
    except Exception as e:
        st.error(f"❌ Ошибка при обработке: {e}")
        return None
    return image_list

# --- Функция: перевод с английского на русский ---
def translate_en_to_ru(text):
    client = Client()
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Переведи на русский: {text}"}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка перевода: {e}"

# --- Функция: OCR + перевод (на уменьшенном изображении) ---
def ocr_and_translate(image):
    # Уменьшаем изображение для экономии памяти
    max_width = 800
    if image.width > max_width:
        ratio = max_width / image.width
        new_size = (int(image.width * ratio), int(image.height * ratio))
        img_resized = image.resize(new_size, Image.Resampling.LANCZOS)
    else:
        img_resized = image

    # OCR на уменьшенном изображении
    results = reader.readtext(img_resized)
    jp_text = " ".join([res[1] for res in results if res[2] > 0.1])
    
    if not jp_text.strip():
        return "Текст не найден", "Текст не найден", "Текст не найден"

    # Перевод JP → EN → RU
    client = Client()
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Переведи на английский: {jp_text}"}]
        )
        en_text = response.choices[0].message.content
    except Exception:
        en_text = "Не удалось перевести на английский"

    ru_text = translate_en_to_ru(en_text)

    return jp_text, en_text, ru_text

# --- Интерфейс ---
st.set_page_config(page_title="MangaTranslator", layout="centered")
st.title("🌐 MangaTranslator")
st.markdown("Загрузите главу — мы распознаем и переведём текст!")

uploaded_file = st.file_uploader(
    "Загрузите главу (PDF, CBZ, JPG, PNG)",
    type=["pdf", "cbz", "png", "jpg", "jpeg"]
)

if uploaded_file:
    # Показываем размер файла
    file_size = uploaded_file.size
    size_mb = file_size / (1024 * 1024)
    st.write(f"📄 Размер файла: **{size_mb:.2f} МБ**")

    # Предупреждение, если файл большой
    if size_mb > 10:
        st.warning("⚠️ Файл больше 10 МБ — может не хватить памяти на бесплатном сервере.")
        st.info("""
        💡 **Советы:**
        - Уменьшите разрешение изображений
        - Сохраните PDF с меньшим качеством
        - Разбейте главу на части
        """)
    else:
        st.success("✅ Файл в пределах нормы — можно обрабатывать.")

    # Ограничиваем размер
    if file_size > 10 * 1024 * 1024:  # 10 МБ
        st.error("❌ Файл слишком большой. Максимум — 10 МБ.")
        st.stop()

    # Конвертация
    with st.spinner("🔄 Конвертирую файл..."):
        images = convert_to_images(uploaded_file)

    if images:
        st.success(f"✅ Загружено {len(images)} страниц")

        # Выбор страницы
        if len(images) == 1:
            st.write("📄 Страница: 1")
            page = 1
        else:
            page = st.slider("Выберите страницу", 1, len(images), 1)

        # Показываем оригинал
        original_image = images[page - 1]
        st.image(original_image, caption=f"Страница {page}", use_container_width=True)

        if st.button("🔍 Распознать и перевести"):
            with st.spinner("🧠 Распознаём и переводим..."):
                jp, en, ru = ocr_and_translate(original_image)

            st.subheader("🇯🇵 Японский текст:")
            st.write(jp)
            st.subheader("🇬🇧 Английский перевод:")
            st.write(en)
            st.subheader("🇷🇺 Русский перевод:")
            st.write(ru)
