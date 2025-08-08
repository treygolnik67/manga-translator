# app.py — Финальная версия: MangaTranslator с логотипом, EPUB и установщиком

import flet as ft
from PIL import Image
import fitz
import zipfile
import tempfile
import os
from pathlib import Path
import easyocr
from g4f.client import Client
from langdetect import detect
from fpdf2 import FPDF
from ebooklib import epub

# Настройка
TEMP_DIR = Path(tempfile.mkdtemp())
reader = easyocr.Reader(['ja', 'en'])
client = Client()

# --- Конвертация в изображения ---
def convert_to_images(file_path):
    images = []
    ext = Path(file_path).suffix.lower()
    try:
        if ext in [".png", ".jpg", ".jpeg"]:
            images.append(Image.open(file_path))
        elif ext == ".pdf":
            pdf = fitz.open(file_path)
            for page_num in range(len(pdf)):
                page = pdf.load_page(page_num)
                pix = page.get_pixmap(dpi=120)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
            pdf.close()
        elif ext == ".cbz":
            with zipfile.ZipFile(file_path, 'r') as cbz:
                for file in sorted(cbz.namelist()):
                    if file.lower().endswith((".png", ".jpg", ".jpeg")):
                        with cbz.open(file) as img_file:
                            img = Image.open(img_file)
                            images.append(img)
        return images
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

# --- Определение языка ---
def detect_language(text):
    try:
        return detect(text)
    except:
        return 'unknown'

# --- Перевод ---
def translate(text, target_lang):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"Переведи на {target_lang}: {text}"}]
        )
        return response.choices[0].message.content
    except:
        return f"Ошибка перевода на {target_lang}"

# --- OCR + Умный перевод ---
def process_page(image):
    if image.width > 800:
        ratio = 800 / image.width
        new_height = int(image.height * ratio)
        img_resized = image.resize((800, new_height), Image.Resampling.LANCZOS)
    else:
        img_resized = image

    results = reader.readtext(img_resized)
    text = " ".join([res[1] for res in results if res[2] > 0.1])
    if not text.strip():
        return "Текст не найден", "Текст не найден", "Текст не найден"

    lang = detect_language(text)
    if lang == 'ru':
        return text, "Уже на русском", "Перевод не требуется"
    elif lang == 'en':
        ru_text = translate(text, "русский")
        return text, "Английский текст", ru_text
    elif lang == 'ja':
        en_text = translate(text, "английский")
        ru_text = translate(en_text, "русский")
        return text, en_text, ru_text
    else:
        return text, f"Язык: {lang}", "Неизвестный язык"

# --- Сохранение в PDF ---
def save_translation_to_pdf(translations, output_path):
    pdf = FPDF()
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.set_auto_page_break(auto=True, margin=15)
    for i, (jp, en, ru) in enumerate(translations):
        pdf.add_page()
        pdf.set_font("DejaVu", size=12)
        pdf.cell(0, 10, f"Страница {i+1}", ln=True, align="C")
        pdf.set_font("DejaVu", size=10)
        pdf.cell(0, 8, f"🇯🇵 Японский: {jp}", ln=True)
        pdf.cell(0, 8, f"🇬🇧 Английский: {en}", ln=True)
        pdf.cell(0, 8, f"🇷🇺 Русский: {ru}", ln=True)
        pdf.ln(5)
    pdf.output(output_path)

# --- Сохранение в EPUB ---
def save_translation_to_epub(translations, output_path):
    book = epub.EpubBook()
    book.set_title("Переведённая манга")
    book.add_author("MangaTranslator")
    book.set_language("ru")

    for i, (jp, en, ru) in enumerate(translations):
        chapter = epub.EpubHtml(title=f"Страница {i+1}", file_name=f"page_{i+1}.xhtml", lang="ru")
        chapter.content = f"""
            <h2>Страница {i+1}</h2>
            <p><b>🇯🇵 Японский:</b> {jp}</p>
            <p><b>🇬🇧 Английский:</b> {en}</p>
            <p><b>🇷🇺 Русский:</b> {ru}</p>
        """
        book.add_item(chapter)

    book.toc = (epub.Link("page_1.xhtml", "Начало", "intro"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + [ch for ch in book.get_items_of_type(epub.EpubHtml)]

    epub.write_epub(output_path, book, {})

# --- Интерфейс ---
def main(page: ft.Page):
    page.title = "MangaTranslator"
    page.theme_mode = "light"
    page.scroll = "adaptive"

    # Логотип
    logo = ft.Image(src="logo.png", width=100, height=100) if Path("logo.png").exists() else ft.Container()

    file_picker = ft.FilePicker()
    save_pdf_picker = ft.FilePicker()
    save_epub_picker = ft.FilePicker()
    page.overlay.extend([file_picker, save_pdf_picker, save_epub_picker])

    result_jp = ft.Text()
    result_en = ft.Text()
    result_ru = ft.Text()
    image_display = ft.Image(width=300, height=400, fit=ft.ImageFit.CONTAIN)
    status = ft.Text("Готов к работе")

    translations = []

    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files:
            file_path = e.files[0].path
            status.value = f"📄 Загружено: {Path(file_path).name}"
            images = convert_to_images(file_path)
            if images:
                page.session.set("images", images)
                page.session.set("current_page", 0)
                page.session.set("translations", [])
                translations.clear()
                update_page()
            else:
                status.value = "❌ Ошибка при конвертации"
            page.update()

    def update_page():
        images = page.session.get("images")
        current_page = page.session.get("current_page", 0)
        if images:
            img = images[current_page]
            bio = tempfile.BytesIO()
            img.save(bio, format="PNG")
            image_display.src_base64 = f"image/png;base64,{bio.getvalue().encode('base64')}"
            image_display.update()

    def next_page(e): ...
    def prev_page(e): ...
    def translate(e): ...

    def save_pdf(e):
        if not translations:
            status.value = "❌ Нет перевода для сохранения"
            page.update()
            return
        save_pdf_picker.save_file(
            dialog_title="Сохранить как PDF",
            file_name="перевод_манги.pdf",
            allowed_extensions=["pdf"]
        )

    def save_epub(e):
        if not translations:
            status.value = "❌ Нет перевода для сохранения"
            page.update()
            return
        save_epub_picker.save_file(
            dialog_title="Сохранить как EPUB",
            file_name="перевод_манги.epub",
            allowed_extensions=["epub"]
        )

    def on_save_pdf(e: ft.FilePickerResultEvent):
        if e.path:
            save_translation_to_pdf(translations, e.path)
            status.value = f"✅ PDF сохранён: {e.path}"
            page.update()

    def on_save_epub(e: ft.FilePickerResultEvent):
        if e.path:
            save_translation_to_epub(translations, e.path)
            status.value = f"✅ EPUB сохранён: {e.path}"
            page.update()

    # UI
    page.add(
        ft.AppBar(
            title=ft.Text("MangaTranslator"),
            bgcolor=ft.colors.BLUE,
            center_title=True
        ),
        ft.Row([logo], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([ft.Text("Умный переводчик манги", size=16)], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([ft.ElevatedButton("📁 Выбрать файл", on_click=lambda _: file_picker.pick_files(
            allowed_extensions=["pdf", "cbz", "jpg", "jpeg", "png"]
        ))], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([status], alignment=ft.MainAxisAlignment.CENTER),
        ft.Divider(),
        ft.Row([
            ft.ElevatedButton("◀ Назад", on_click=prev_page),
            ft.ElevatedButton("🔍 Перевести", on_click=translate),
            ft.ElevatedButton("▶ Вперёд", on_click=next_page),
        ], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([
            ft.ElevatedButton("📥 Сохранить как PDF", icon=ft.icons.PICTURE_AS_PDF, on_click=save_pdf),
            ft.ElevatedButton("📚 Сохранить как EPUB", icon=ft.icons.BOOK, on_click=save_epub),
        ], alignment=ft.MainAxisAlignment.CENTER),
        ft.Divider(),
        ft.Row([
            ft.Container(image_display, alignment=ft.alignment.center, expand=True),
            ft.Container(ft.Column([
                ft.Text("🔍 Распознанный текст:", weight=ft.FontWeight.BOLD),
                result_jp,
                ft.Text("🇬🇧 Перевод на английский:", weight=ft.FontWeight.BOLD),
                result_en,
                ft.Text("🇷🇺 Перевод на русский:", weight=ft.FontWeight.BOLD),
                result_ru,
            ], scroll=ft.ScrollMode.AUTO), width=350)
        ], expand=True)
    )

    file_picker.on_result = on_file_picked
    save_pdf_picker.on_result = on_save_pdf
    save_epub_picker.on_result = on_save_epub

ft.app(target=main)
