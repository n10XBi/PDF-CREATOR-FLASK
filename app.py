from flask import Flask, render_template, request, send_file, jsonify
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
from io import BytesIO
from PIL import Image
import time
import warnings
import os
import bleach
import requests
import tempfile
import logging
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

# Abaikan peringatan tertentu
warnings.filterwarnings("ignore", category=UserWarning)

app = Flask(__name__)

class PDF(FPDF):
    def __init__(self, header, chapter_title, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.header_text = header
        self.chapter_title_text = chapter_title

    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, self.header_text, 0, 1, 'C')

    def chapter_title(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, self.chapter_title_text, 0, 1, 'L')

    def chapter_body(self, body):
        self.set_font('Amiri', '', 12)
        reshaped_text = arabic_reshaper.reshape(body)
        bidi_text = get_display(reshaped_text)
        self.multi_cell(0, 10, bidi_text)
        self.ln()

    def add_arabic_text(self, text, images):
        self.add_page()
        self.chapter_title()

        parts = text.split("{{image}}")
        if len(parts) - 1 > len(images):
            raise ValueError("More placeholders than images provided")

        for i, part in enumerate(parts):
            self.chapter_body(part)
            if i < len(images):
                self.add_image(images[i])

    def add_image(self, image_path):
        try:
            self.image(image_path, x=10, y=None, w=100)
            self.ln(10)
        except RuntimeError as e:
            raise ValueError(f"Failed to add image: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        header = bleach.clean(request.form['header'])
        chapter_title = bleach.clean(request.form['chapter_title'])
        title = bleach.clean(request.form['title'])
        text = bleach.clean(request.form['text'])
        filename = bleach.clean(request.form['filename'])

        uploaded_files = request.files.getlist("images")
        image_paths = []

        for file in uploaded_files:
            if file and file.filename != '':
                sanitized_filename = bleach.clean(file.filename)
                image_path = os.path.join('static', sanitized_filename)
                file.save(image_path)
                image_paths.append(image_path)

        pdf = PDF(header, chapter_title)
        font_path = os.path.join('static', 'Amiri-Regular.ttf')
        if not os.path.exists(font_path):
            return f"Font file not found at {font_path}. Please make sure 'Amiri-Regular.ttf' is in the 'static' folder."

        try:
            pdf.add_font('Amiri', '', font_path, uni=True)
        except Exception as e:
            return f"Failed to add font: {str(e)}"

        try:
            pdf.add_arabic_text(text, image_paths)
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Failed to add Arabic text: {str(e)}"

        try:
            pdf_file = f"{filename}_{time.strftime('%d-%m-%Y_%H-%M-%S')}.pdf"
            pdf.output(pdf_file)
        except Exception as e:
            return f"Failed to save PDF: {str(e)}"

        try:
            return send_file(pdf_file, as_attachment=True)
        except Exception as e:
            return f"Failed to send PDF file: {str(e)}"
    
    return render_template('index.html')

@app.route('/api/create_pdf', methods=['GET'])
def create_pdf():
    try:
        header = request.args.get('header')
        chapter_title = request.args.get('chapter_title')
        text = request.args.get('text')
        filename = request.args.get('filename') + '.pdf'
        image_urls = request.args.getlist('image_urls')

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # Register font Amiri
        pdfmetrics.registerFont(TTFont('Amiri', 'static/Amiri-Regular.ttf'))
        c.setFont('Amiri', 16)

        margin = 50
        padding = 10
        line_height = 15
        header_footer_space = 100
        current_height = height - margin

        def new_page():
            nonlocal current_height
            c.showPage()
            current_height = height - margin
            c.setFont('Amiri', 16)
            c.drawString(margin, height - margin, header)
            c.setFont('Amiri', 14)
            c.drawString(margin, height - margin - 50, chapter_title)
            current_height -= header_footer_space

        c.setFont('Amiri', 16)
        c.drawString(margin, height - margin, header)

        c.setFont('Amiri', 14)
        c.drawString(margin, height - margin - 50, chapter_title)
        current_height -= header_footer_space

        c.setFont('Amiri', 12)
        paragraphs = text.split("{{image}}")

        for i, paragraph in enumerate(paragraphs):
            lines = paragraph.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                words = line.split(" ")
                line_buffer = ""
                for word in words:
                    if c.stringWidth(line_buffer + word) < (width - 2 * margin):
                        line_buffer += word + " "
                    else:
                        if current_height - line_height < margin:
                            new_page()
                        c.drawString(margin, current_height, line_buffer)
                        current_height -= line_height + padding
                        line_buffer = word + " "
                if line_buffer:
                    if current_height - line_height < margin:
                        new_page()
                    c.drawString(margin, current_height, line_buffer)
                    current_height -= line_height + padding

            if i < len(image_urls):
                image_url = image_urls[i]
                response = requests.get(image_url)
                if response.status_code == 200:
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                    temp_file.write(response.content)
                    temp_file.close()

                    with Image.open(temp_file.name) as img:
                        img_width, img_height = img.size

                    max_width = width - 2 * margin
                    max_height = height - 2 * margin

                    if img_width > max_width or img_height > max_height:
                        if img_width / img_height > max_width / max_height:
                            img_width = max_width
                            img_height = img_width * img.height / img.width
                        else:
                            img_height = max_height
                            img_width = img_height * img.width / img.height

                    if current_height - img_height < margin:
                        new_page()

                    c.drawImage(temp_file.name, margin, current_height - img_height, width=img_width, height=img_height)
                    current_height -= img_height + 10 + padding

                    os.unlink(temp_file.name)
                else:
                    logging.error(f"Failed to fetch image from {image_url}")

        c.save()
        buffer.seek(0)

        with open(filename, 'wb') as f:
            f.write(buffer.getvalue())

        return send_file(filename, as_attachment=True)

    except Exception as e:
        logging.error(f"Error creating PDF: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
